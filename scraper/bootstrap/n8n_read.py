"""Optional read-only n8n API client for scrape execution visibility."""

from __future__ import annotations

import json
import os
import shlex
import urllib.error
import urllib.request
from typing import Any


def _api_key() -> str:
    return os.getenv("N8N_API_KEY", "").strip()


def _via_vps_enabled() -> bool:
    return os.getenv("N8N_VIA_VPS", "1").strip().lower() not in ("0", "false", "no")


def n8n_configured() -> bool:
    if not _api_key():
        return False
    if os.getenv("N8N_BASE_URL", "").strip():
        return True
    if _via_vps_enabled():
        from bootstrap.vps_control import vps_configured

        return vps_configured()
    return False


def _parse_executions_payload(payload: Any, *, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    data = payload.get("data") if isinstance(payload, dict) else payload
    if not isinstance(data, list):
        return [], "n8n: unexpected response"
    rows: list[dict[str, Any]] = []
    for item in data:
        if isinstance(item, dict):
            rows.append(item)
    return rows[:limit], None


def _fetch_http(base: str, api_key: str, *, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    url = f"{base.rstrip('/')}/api/v1/executions?limit={max(limit, 1)}"
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "X-N8N-API-KEY": api_key,
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return [], f"n8n HTTP {exc.code}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        return [], f"n8n: {exc}"
    return _parse_executions_payload(payload, limit=limit)


def _vps_local_n8n_base(cfg: Any) -> str:
    explicit = os.getenv("N8N_VPS_LOCAL_URL", "").strip().rstrip("/")
    if explicit:
        return explicit
    from bootstrap.vps_control import _ssh_exec

    for env_file in (
        os.path.join(cfg.repo_root, ".env"),
        "/root/hercule.dev/.env",
        "/root/hercule-outreach/.env",
    ):
        cmd = f"grep -E '^N8N_(EDITOR_BASE_URL|HOST|PORT)=' {shlex.quote(env_file)} 2>/dev/null || true"
        _, out, _ = _ssh_exec(cfg, cmd, timeout=20)
        editor = host = port = ""
        for line in out.splitlines():
            if line.startswith("N8N_EDITOR_BASE_URL="):
                editor = line.split("=", 1)[1].strip().strip('"').strip("'").rstrip("/")
            elif line.startswith("N8N_HOST="):
                host = line.split("=", 1)[1].strip().strip('"').strip("'")
            elif line.startswith("N8N_PORT="):
                port = line.split("=", 1)[1].strip().strip('"').strip("'")
        if editor:
            return editor
        if host:
            scheme = "https" if port in ("443", "") and host not in ("127.0.0.1", "localhost") else "http"
            if not port:
                port = "5678"
            return f"{scheme}://{host}:{port}".rstrip("/")
    return "http://127.0.0.1:5678"


def _fetch_via_vps_ssh(api_key: str, *, limit: int) -> tuple[list[dict[str, Any]], str | None]:
    from bootstrap.vps_control import VpsConfig, _ssh_exec

    cfg = VpsConfig.from_env()
    if not cfg:
        return [], None

    base = _vps_local_n8n_base(cfg)
    url = f"{base}/api/v1/executions?limit={max(limit, 1)}"
    header = shlex.quote(f"X-N8N-API-KEY: {api_key}")
    cmd = (
        f"curl -sS --max-time 20 -H {header} -H 'Accept: application/json' "
        f"{shlex.quote(url)}"
    )
    code, out, err = _ssh_exec(cfg, cmd, timeout=35)
    if code != 0:
        detail = (err or out).strip() or f"curl exit {code}"
        return [], f"n8n VPS: {detail[:200]}"
    try:
        payload = json.loads(out)
    except json.JSONDecodeError:
        snippet = out.strip()[:120]
        return [], f"n8n VPS: réponse invalide ({snippet})"
    return _parse_executions_payload(payload, limit=limit)


def fetch_recent_executions(*, limit: int = 15) -> tuple[list[dict[str, Any]], str | None]:
    """Return (executions, error_message). Empty list when not configured."""
    api_key = _api_key()
    if not api_key:
        return [], None

    base = os.getenv("N8N_BASE_URL", "").strip().rstrip("/")
    if base:
        return _fetch_http(base, api_key, limit=limit)

    if _via_vps_enabled():
        from bootstrap.vps_control import vps_configured

        if vps_configured():
            return _fetch_via_vps_ssh(api_key, limit=limit)

    return [], None


def executions_to_display_rows(executions: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in executions:
        started = str(item.get("startedAt") or item.get("createdAt") or "")
        stopped = str(item.get("stoppedAt") or "")
        status = str(item.get("status") or item.get("finished") or "")
        workflow = item.get("workflowData") or {}
        name = ""
        if isinstance(workflow, dict):
            name = str(workflow.get("name") or "")
        if not name:
            name = str(item.get("workflowId") or "—")
        out.append(
            {
                "Workflow": name,
                "Début": started[:19].replace("T", " ") if started else "—",
                "Fin": stopped[:19].replace("T", " ") if stopped else "—",
                "Statut n8n": status,
            }
        )
    return out
