"""SSH read for VPS scrape artifacts; n8n webhook trigger for launches."""

from __future__ import annotations

import json
import os
import shlex
import time
from dataclasses import dataclass
from typing import Any

import config_loader  # noqa: F401 — loads repo .env via outreach_root()

from repo_paths import outreach_root

_SSH_CONNECT_TIMEOUT = 10
_SSH_BACKOFF_SECONDS = 45
_ssh_backoff_until: float = 0.0
_ssh_last_error: str = ""


@dataclass
class VpsConfig:
    host: str
    user: str
    password: str
    key_path: str
    repo_root: str
    data_root: str
    service_name: str

    @classmethod
    def from_env(cls) -> VpsConfig | None:
        host = os.getenv("VPS_HOST", "").strip()
        user = os.getenv("VPS_USER", "").strip()
        if not host or not user:
            return None
        return cls(
            host=host,
            user=user,
            password=os.getenv("VPS_SSH_PASSWORD", "").strip(),
            key_path=os.path.expanduser(os.getenv("VPS_SSH_KEY", "").strip()),
            repo_root=os.getenv("VPS_REPO_ROOT", "/root/hercule-outreach").strip(),
            data_root=os.getenv("HERCULE_DATA_ROOT", "/var/lib/hercule").strip(),
            service_name=os.getenv("VPS_SCRAPER_SERVICE", "hercule-scraper").strip(),
        )


def vps_configured() -> bool:
    return VpsConfig.from_env() is not None


def n8n_scrape_webhook_configured() -> bool:
    return bool(os.getenv("N8N_SCRAPE_WEBHOOK_URL", "").strip())


def resolve_scrape_default_preset_id() -> str:
    """Preset used when the UI/webhook omits preset_id (n8n heal --preset)."""
    for key in ("SCRAPE_DEFAULT_PRESET", "N8N_DEFAULT_PRESET"):
        value = os.getenv(key, "").strip()
        if value:
            return value
    return "_adhoc"


def resolve_scrape_tracking_preset_id() -> str:
    """Preset directory to read for Suivi en cours (heartbeat overrides default)."""
    default = resolve_scrape_default_preset_id()
    if not vps_configured():
        return default
    _, _, _, heartbeat, _ = load_panel_state(default, max_log_lines=1, max_cron_lines=1)
    hb_preset = str((heartbeat or {}).get("preset") or "").strip()
    return hb_preset or default


def vps_ssh_key_configured(cfg: VpsConfig | None = None) -> bool:
    cfg = cfg or VpsConfig.from_env()
    if not cfg or not cfg.key_path:
        return False
    return os.path.isfile(cfg.key_path)


def vps_ssh_auth_hint(cfg: VpsConfig | None = None) -> str:
    cfg = cfg or VpsConfig.from_env()
    if not cfg:
        return "Définissez `VPS_HOST` et `VPS_USER` dans le `.env` du repo."
    env_path = str(outreach_root() / ".env")
    if not os.path.isfile(env_path):
        env_path = "repo/.env"
    if cfg.password:
        return ""
    if cfg.key_path and not os.path.isfile(cfg.key_path):
        return f"`VPS_SSH_KEY` introuvable ({cfg.key_path})."
    if cfg.key_path:
        return ""
    return (
        f"`VPS_SSH_PASSWORD` absent ou non chargé — vérifiez {env_path} "
        "(guillemets fermés si le mot de passe contient `'` ou `@`), "
        "ou définissez `VPS_SSH_KEY` vers une clé privée."
    )


def format_vps_connection_warning(detail: str, cfg: VpsConfig | None = None) -> str:
    base = detail or "vérifiez VPS_HOST, le réseau et l'authentification SSH"
    hint = vps_ssh_auth_hint(cfg)
    if hint and hint not in base and (
        "Authentication failed" in base
        or "VPS_SSH_PASSWORD" in base
        or "VPS_SSH_KEY" in base
    ):
        return f"{base}. {hint}"
    return base


def _ssh_in_backoff() -> bool:
    return time.monotonic() < _ssh_backoff_until


def _mark_ssh_failure(message: str) -> None:
    global _ssh_backoff_until, _ssh_last_error
    _ssh_backoff_until = time.monotonic() + _SSH_BACKOFF_SECONDS
    _ssh_last_error = message


def _clear_ssh_failure() -> None:
    global _ssh_backoff_until, _ssh_last_error
    _ssh_backoff_until = 0.0
    _ssh_last_error = ""


def _connect_ssh(cfg: VpsConfig):
    import paramiko

    preflight = vps_ssh_auth_hint(cfg)
    if preflight and not vps_ssh_key_configured(cfg):
        raise paramiko.AuthenticationException(preflight)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    use_key = vps_ssh_key_configured(cfg)
    connect_kwargs: dict[str, Any] = {
        "hostname": cfg.host,
        "username": cfg.user,
        "timeout": _SSH_CONNECT_TIMEOUT,
        "allow_agent": not cfg.password,
        "look_for_keys": not cfg.password and not use_key,
    }
    if cfg.password:
        connect_kwargs["password"] = cfg.password
    if use_key:
        connect_kwargs["key_filename"] = cfg.key_path
    client.connect(**connect_kwargs)
    return client


def _ssh_exec(cfg: VpsConfig, command: str, *, timeout: int = 120) -> tuple[int, str, str]:
    if _ssh_in_backoff():
        return 1, "", _ssh_last_error or "SSH unavailable (retrying shortly)"

    try:
        import paramiko  # noqa: F401
    except ImportError:
        return 1, "", "paramiko not installed"

    try:
        client = _connect_ssh(cfg)
        try:
            _, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            code = stdout.channel.recv_exit_status()
            _clear_ssh_failure()
            return code, out, err
        finally:
            client.close()
    except Exception as exc:
        message = f"SSH failed: {exc}"
        _mark_ssh_failure(message)
        return 1, "", message


def _ssh_fetch_files(
    cfg: VpsConfig,
    remote_paths: list[str],
    *,
    timeout: int = 60,
) -> dict[str, str]:
    empty = {path: "" for path in remote_paths}
    if not remote_paths:
        return empty
    if _ssh_in_backoff():
        return empty

    try:
        import paramiko  # noqa: F401
    except ImportError:
        _mark_ssh_failure("paramiko not installed")
        return empty

    try:
        client = _connect_ssh(cfg)
        try:
            results = dict(empty)
            for path in remote_paths:
                _, stdout, stderr = client.exec_command(
                    f"cat {shlex.quote(path)}",
                    timeout=timeout,
                )
                out = stdout.read().decode("utf-8", errors="replace")
                err = stderr.read().decode("utf-8", errors="replace")
                code = stdout.channel.recv_exit_status()
                if code == 0:
                    results[path] = out
                elif err.strip():
                    results[path] = ""
            _clear_ssh_failure()
            return results
        finally:
            client.close()
    except Exception as exc:
        _mark_ssh_failure(f"SSH failed: {exc}")
        return empty


def worker_status(cfg: VpsConfig | None = None) -> dict[str, Any]:
    cfg = cfg or VpsConfig.from_env()
    if not cfg:
        return {"configured": False, "active": False, "reachable": True, "detail": "VPS not configured"}
    if _ssh_in_backoff():
        return {
            "configured": True,
            "active": False,
            "reachable": False,
            "detail": _ssh_last_error or "SSH unavailable (retrying shortly)",
            "host": cfg.host,
            "service": cfg.service_name,
        }
    cmd = f"systemctl is-active {shlex.quote(cfg.service_name)}"
    code, out, err = _ssh_exec(cfg, cmd, timeout=30)
    active = out.strip() == "active"
    reachable = code == 0 or bool(out.strip())
    detail = out.strip() or err.strip() or f"exit {code}"
    return {
        "configured": True,
        "active": active,
        "reachable": reachable,
        "detail": detail,
        "host": cfg.host,
        "service": cfg.service_name,
    }


def stop_worker(*, cfg: VpsConfig | None = None) -> tuple[bool, str]:
    cfg = cfg or VpsConfig.from_env()
    if not cfg:
        return False, "VPS not configured — cannot stop worker."
    cmd = f"systemctl stop {shlex.quote(cfg.service_name)}"
    code, out, err = _ssh_exec(cfg, cmd, timeout=60)
    if code == 0:
        return True, "Worker stopped on VPS."
    return False, err.strip() or out.strip() or f"systemctl failed ({code})"


def trigger_n8n_scrape(
    *,
    keyword: str,
    instantly_list_id: str,
    target_leads: int,
    preset_id: str | None = None,
) -> tuple[bool, str]:
    """POST scrape launch payload to N8N_SCRAPE_WEBHOOK_URL."""
    url = os.getenv("N8N_SCRAPE_WEBHOOK_URL", "").strip()
    if not url:
        return (
            False,
            "Définissez `N8N_SCRAPE_WEBHOOK_URL` dans le `.env` pour lancer un scrape via n8n.",
        )
    try:
        import httpx

        payload: dict[str, Any] = {
            "keyword": keyword.strip(),
            "instantly_list_id": instantly_list_id.strip(),
            "target_leads": int(target_leads),
        }
        if preset_id and preset_id.strip():
            payload["preset_id"] = preset_id.strip()
            payload["preset"] = preset_id.strip()
        with httpx.Client(timeout=30.0) as client:
            response = client.post(url, json=payload)
        if response.status_code >= 400:
            body = response.text.strip()[:500]
            return False, f"n8n webhook HTTP {response.status_code}: {body or 'empty body'}"
        return True, "Scrape déclenché via n8n."
    except Exception as exc:
        return False, f"n8n webhook failed: {exc}"


def fetch_remote_file(remote_path: str, *, cfg: VpsConfig | None = None) -> str:
    cfg = cfg or VpsConfig.from_env()
    if not cfg:
        if os.path.isfile(remote_path):
            with open(remote_path, encoding="utf-8") as handle:
                return handle.read()
        return ""
    return _ssh_fetch_files(cfg, [remote_path], timeout=60).get(remote_path, "")


def _parse_json_dict(raw: str) -> dict | None:
    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_jsonl_events(raw: str, *, max_lines: int) -> list[dict]:
    events: list[dict] = []
    lines = [line for line in raw.splitlines() if line.strip()]
    for line in lines[-max_lines:]:
        try:
            item = json.loads(line)
            if isinstance(item, dict):
                events.append(item)
        except json.JSONDecodeError:
            continue
    return events


def load_panel_state(
    preset: str,
    *,
    max_log_lines: int = 60,
    max_cron_lines: int = 10,
) -> tuple[dict | None, str, str, dict | None, list[dict]]:
    """Return (scrape_state, log_tail, out_dir, heartbeat, cron_events) from VPS or local."""
    from paths import output_paths
    from scrape_log import tail_scrape_log
    from scrape_metrics import cron_events_path, heartbeat_path, load_worker_heartbeat, tail_cron_events

    cfg = VpsConfig.from_env()
    if not cfg:
        local_paths = output_paths(preset)
        state = load_scrape_state_file(local_paths.scrape_state)
        return (
            state,
            tail_scrape_log(local_paths.out_dir, max_lines=max_log_lines),
            local_paths.out_dir,
            load_worker_heartbeat(local_paths.out_dir),
            tail_cron_events(local_paths.out_dir, max_lines=max_cron_lines),
        )

    out_dir = remote_preset_out_dir(preset, cfg)
    state_path = os.path.join(out_dir, "scrape_state.json")
    log_path = os.path.join(out_dir, "scrape.log")
    heartbeat_file = heartbeat_path(out_dir)
    cron_path = cron_events_path(out_dir)
    remote_paths = [state_path, log_path, heartbeat_file, cron_path]
    remote_files = _ssh_fetch_files(cfg, remote_paths, timeout=60)
    state = _parse_json_dict(remote_files.get(state_path, ""))
    log_tail = remote_files.get(log_path, "")
    if log_tail:
        lines = log_tail.splitlines()
        log_tail = "\n".join(lines[-max_log_lines:])
    heartbeat = _parse_json_dict(remote_files.get(heartbeat_file, ""))
    cron_events = _parse_jsonl_events(
        remote_files.get(cron_path, ""),
        max_lines=max_cron_lines,
    )
    return state, log_tail, out_dir, heartbeat, cron_events


def load_scrape_state_file(state_path: str) -> dict | None:
    from scrape_state import load_scrape_state

    return load_scrape_state(state_path)


def remote_preset_out_dir(preset: str, cfg: VpsConfig | None = None) -> str:
    from paths import output_paths

    cfg = cfg or VpsConfig.from_env()
    data_root = cfg.data_root if cfg else os.getenv("HERCULE_DATA_ROOT", "").strip()
    if data_root:
        return os.path.join(data_root, "streamlit_scraper", "output", preset)
    return output_paths(preset).out_dir


def tail_scrape_log_local_or_remote(preset: str) -> str:
    _, log_tail, _, _, _ = load_panel_state(preset)
    return log_tail
