"""SSH control for VPS scrape worker (used by Scrape page operations panel)."""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Any

from dotenv import load_dotenv

_SSH_CONNECT_TIMEOUT = 10
_SSH_BACKOFF_SECONDS = 45
_ssh_backoff_until: float = 0.0
_ssh_last_error: str = ""

_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_REPO_ENV = os.path.join(_REPO_ROOT, ".env")
_LOCAL_ENV = os.path.join(os.path.dirname(__file__), "..", ".env")

if os.path.isfile(_REPO_ENV):
    load_dotenv(_REPO_ENV)
if os.path.isfile(_LOCAL_ENV):
    load_dotenv(_LOCAL_ENV, override=True)
load_dotenv()


@dataclass
class VpsConfig:
    host: str
    user: str
    password: str
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
            repo_root=os.getenv("VPS_REPO_ROOT", "/root/hercule-outreach").strip(),
            data_root=os.getenv("HERCULE_DATA_ROOT", "/var/lib/hercule").strip(),
            service_name=os.getenv("VPS_SCRAPER_SERVICE", "hercule-scraper").strip(),
        )


def vps_configured() -> bool:
    return VpsConfig.from_env() is not None


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

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    connect_kwargs: dict[str, Any] = {
        "hostname": cfg.host,
        "username": cfg.user,
        "timeout": _SSH_CONNECT_TIMEOUT,
        "allow_agent": True,
        "look_for_keys": True,
    }
    if cfg.password:
        connect_kwargs["password"] = cfg.password
    client.connect(**connect_kwargs)
    return client



def _ssh_exec(cfg: VpsConfig, command: str, *, timeout: int = 120) -> tuple[int, str, str]:
    if _ssh_in_backoff():
        return 1, "", _ssh_last_error or "SSH unavailable (retrying shortly)"

    try:
        import paramiko  # noqa: F401 — availability check
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
    """Read multiple remote files over one SSH session."""
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


def _remote_env(cfg: VpsConfig) -> str:
    return (
        f"export HERCULE_DATA_ROOT={shlex.quote(cfg.data_root)} "
        f"SCRAPER_PRESET={shlex.quote(os.getenv('SCRAPER_PRESET', ''))} "
        f"PYTHONPATH={shlex.quote(cfg.repo_root)}"
    )


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


def start_worker(preset: str, *, cfg: VpsConfig | None = None) -> tuple[bool, str]:
    cfg = cfg or VpsConfig.from_env()
    if not cfg:
        return _start_local_worker(preset)
    cmd = f"systemctl start {shlex.quote(cfg.service_name)}"
    code, out, err = _ssh_exec(cfg, cmd, timeout=60)
    if code == 0:
        return True, out.strip() or "Worker started on VPS."
    return False, err.strip() or out.strip() or f"systemctl failed ({code})"


def stop_worker(*, cfg: VpsConfig | None = None) -> tuple[bool, str]:
    cfg = cfg or VpsConfig.from_env()
    if not cfg:
        return _stop_local_worker()
    cmd = f"systemctl stop {shlex.quote(cfg.service_name)}"
    code, out, err = _ssh_exec(cfg, cmd, timeout=60)
    if code == 0:
        return True, "Worker stopped on VPS."
    return False, err.strip() or out.strip() or f"systemctl failed ({code})"


def fetch_remote_file(remote_path: str, *, cfg: VpsConfig | None = None) -> str:
    cfg = cfg or VpsConfig.from_env()
    if not cfg:
        if os.path.isfile(remote_path):
            with open(remote_path, encoding="utf-8") as handle:
                return handle.read()
        return ""
    return _ssh_fetch_files(cfg, [remote_path], timeout=60).get(remote_path, "")


def _parse_json_dict(raw: str) -> dict | None:
    import json

    if not raw.strip():
        return None
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None


def _parse_jsonl_events(raw: str, *, max_lines: int) -> list[dict]:
    import json

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
    import json

    from scrape_metrics import cron_events_path, heartbeat_path, load_worker_heartbeat, tail_cron_events

    panel_started = time.monotonic()
    cfg = VpsConfig.from_env()
    if not cfg:
        from core_logic import output_paths
        from scrape_log import tail_scrape_log

        local_paths = output_paths(preset)
        state = None
        state_path = local_paths.scrape_state
        if os.path.isfile(state_path):
            try:
                with open(state_path, encoding="utf-8") as handle:
                    state = json.load(handle)
            except (OSError, json.JSONDecodeError):
                state = None
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
    remote_files = _ssh_fetch_files(
        cfg,
        remote_paths,
        timeout=60,
    )
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


def remote_preset_out_dir(preset: str, cfg: VpsConfig | None = None) -> str:
    cfg = cfg or VpsConfig.from_env()
    data_root = cfg.data_root if cfg else os.getenv("HERCULE_DATA_ROOT", "").strip()
    if data_root:
        return os.path.join(data_root, "streamlit_scraper", "output", preset)
    from core_logic import output_paths

    return output_paths(preset).out_dir


def remote_csv_lead_count(preset: str, *, cfg: VpsConfig | None = None) -> int | None:
    """Return lead row count from remote CSV (header excluded), or None if unavailable."""
    cfg = cfg or VpsConfig.from_env()
    if not cfg:
        return None
    csv_path = os.path.join(remote_preset_out_dir(preset, cfg), "outscraper_leads.csv")
    cmd = (
        f"if [ -f {shlex.quote(csv_path)} ]; then "
        f"expr $(wc -l < {shlex.quote(csv_path)}) - 1; else echo 0; fi"
    )
    code, out, _ = _ssh_exec(cfg, cmd, timeout=30)
    if code != 0:
        return None
    try:
        return max(int(out.strip()), 0)
    except ValueError:
        return None


def tail_scrape_log_local_or_remote(preset: str) -> str:
    _, log_tail, _, _, _ = load_panel_state(preset)
    return log_tail


_LOCAL_WORKER_PID_FILE = os.path.join(_REPO_ROOT, ".scraper_worker.pid")


def _start_local_worker(preset: str) -> tuple[bool, str]:
    scraper_dir = os.path.join(_REPO_ROOT, "scraper")
    log_path = os.path.join(scraper_dir, "output", preset, "worker.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.path.pathsep.join([_REPO_ROOT, scraper_dir])
    env["SCRAPER_PRESET"] = preset
    cmd = [
        sys.executable,
        "main.py",
        "worker-loop",
        "--preset",
        preset,
        "--push-instantly",
    ]
    with open(log_path, "a", encoding="utf-8") as log_handle:
        proc = subprocess.Popen(
            cmd,
            cwd=scraper_dir,
            env=env,
            stdout=log_handle,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    with open(_LOCAL_WORKER_PID_FILE, "w", encoding="utf-8") as handle:
        handle.write(str(proc.pid))
    return True, f"Local worker started (pid {proc.pid})."


def _stop_local_worker() -> tuple[bool, str]:
    if not os.path.isfile(_LOCAL_WORKER_PID_FILE):
        return False, "No local worker pid file."
    try:
        with open(_LOCAL_WORKER_PID_FILE, encoding="utf-8") as handle:
            pid = int(handle.read().strip())
        os.kill(pid, 15)
        os.remove(_LOCAL_WORKER_PID_FILE)
        return True, f"Local worker stopped (pid {pid})."
    except (OSError, ValueError) as exc:
        return False, str(exc)
