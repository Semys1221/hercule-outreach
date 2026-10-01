#!/usr/bin/env python3
"""Relaunch VPS scrape workers: sync geo config, reset geo state, restart systemd."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[2]
load_dotenv(REPO / ".env")
sys.path.insert(0, str(REPO / "app" / "(legacy)" / "streamlit_scraper"))

from bootstrap.vps_control import VpsConfig, _connect_ssh, _ssh_exec, worker_status  # noqa: E402

SYNC_PATHS = (
    "scraper/commune_passes.py",
    "scraper/core_logic.py",
    "scraper/main.py",
    "scraper/configs/_bases/common.py",
    "scraper/configs/cabinets_expertise_comptable_fresh_geo_config.py",
    "scraper/configs/cabinets_conseiller_financier_config.py",
    "shared/mev_export.py",
)

COMPTABLE_PRESET = "cabinets_expertise_comptable_fresh_geo"
COMPTABLE_SERVICE = "hercule-scraper-comptable-fresh-geo"
DEPRECATED_COMPTABLE_SERVICE = "hercule-scraper-comptable-vol"


def sync_repo_files(cfg: VpsConfig) -> tuple[bool, list[str]]:
    uploaded: list[str] = []
    try:
        client = _connect_ssh(cfg)
        sftp = client.open_sftp()
        try:
            for rel in SYNC_PATHS:
                local = REPO / rel
                remote = f"{cfg.repo_root}/{rel}"
                sftp.put(str(local), remote)
                uploaded.append(rel)
        finally:
            sftp.close()
            client.close()
    except Exception as exc:
        print(json.dumps({"sync": {"ok": False, "error": str(exc), "uploaded": uploaded}}))
        return False, uploaded
    return True, uploaded


def disable_deprecated_comptable_vol(cfg: VpsConfig) -> tuple[bool, str]:
    cmd = (
        f"systemctl stop {DEPRECATED_COMPTABLE_SERVICE} 2>/dev/null; "
        f"systemctl disable {DEPRECATED_COMPTABLE_SERVICE} 2>/dev/null; "
        f"systemctl stop {DEPRECATED_COMPTABLE_SERVICE}-heal.timer 2>/dev/null; "
        f"systemctl disable {DEPRECATED_COMPTABLE_SERVICE}-heal.timer 2>/dev/null; "
        "echo disabled"
    )
    code, out, err = _ssh_exec(cfg, cmd, timeout=60)
    return code == 0, (out or err or "disabled").strip()


def patch_comptable_systemd_tuning(cfg: VpsConfig) -> tuple[bool, str]:
    """Per-service Outscraper tuning — avoids fleet-wide .env override side effects."""
    unit = f"/etc/systemd/system/{COMPTABLE_SERVICE}.service"
    script = f"""
import re, pathlib
path = pathlib.Path("{unit}")
text = path.read_text(encoding="utf-8")
extras = {{
    "OUTSCRAPER_CONCURRENCY": "16",
    "OUTSCRAPER_POLL_INITIAL_S": "10",
}}
for key, val in extras.items():
    line = f"Environment={{key}}={{val}}"
    if re.search(rf"^Environment={{re.escape(key)}}=", text, re.M):
        text = re.sub(rf"^Environment={{re.escape(key)}}=.*$", line, text, flags=re.M)
    else:
        text = text.replace("[Service]\\n", f"[Service]\\n{{line}}\\n", 1)
path.write_text(text, encoding="utf-8")
print("patched")
"""
    import base64

    encoded = base64.b64encode(script.encode()).decode()
    cmd = f"echo {encoded} | base64 -d | python3"
    code, out, err = _ssh_exec(cfg, cmd, timeout=30)
    if code != 0:
        return False, err or out
    reload = _ssh_exec(cfg, "systemctl daemon-reload", timeout=30)
    return reload[0] == 0, (out or "patched").strip()


def relaunch_comptable_fresh_geo(cfg: VpsConfig) -> tuple[bool, str]:
    script = f"""
import json, os
from config_loader import load_config
from commune_passes import initial_geo_state

preset = '{COMPTABLE_PRESET}'
data_root = os.environ['HERCULE_DATA_ROOT']
path = f'{{data_root}}/streamlit_scraper/output/{{preset}}/scrape_state.json'
config = load_config(preset)
geo_phase, query_pass, skip_places = initial_geo_state(config)
with open(path, encoding='utf-8') as f:
    state = json.load(f)
before = {{k: state.get(k) for k in ('geo_reload_exhausted','reload_round','query_pass','geo_phase','instantly_pushed','status')}}
blocked = bool(state.get('geo_reload_exhausted')) or str(state.get('status') or '') in ('geo_idle', 'blocked')
state.pop('geo_reload_exhausted', None)
state['last_completed_batch_index'] = -1
state['last_submitted_batch_index'] = -1
state['inflight_tasks'] = []
state['status'] = 'incomplete'
if blocked:
    state['reload_round'] = 0
    state['reload_round_pushed_start'] = int(state.get('instantly_pushed', 0) or 0)
    state['geo_phase'] = geo_phase
    state['query_pass'] = query_pass
    state['skip_places'] = skip_places
else:
    state.setdefault('reload_round', 0)
    state.setdefault('geo_phase', geo_phase)
    state.setdefault('query_pass', query_pass)
    state.setdefault('skip_places', skip_places)
with open(path, 'w', encoding='utf-8') as f:
    json.dump(state, f, indent=2)
print(json.dumps({{'before': before, 'after': {{'geo_reload_exhausted': state.get('geo_reload_exhausted'), 'reload_round': state.get('reload_round'), 'query_pass': state.get('query_pass'), 'geo_phase': state.get('geo_phase')}}}}))
"""
    import base64

    repo = cfg.repo_root
    encoded = base64.b64encode(script.encode()).decode()
    cmd = (
        f"cd {repo}/scraper && "
        f"export HERCULE_DATA_ROOT={cfg.data_root} PYTHONPATH={repo} && "
        f"echo {encoded} | base64 -d | {repo}/.venv/bin/python"
    )
    code, out, err = _ssh_exec(cfg, cmd, timeout=120)
    if code != 0:
        return False, err or out or f"exit {code}"
    restart = _ssh_exec(cfg, f"systemctl restart {COMPTABLE_SERVICE}", timeout=60)
    return restart[0] == 0, out.strip() or "restarted"


def relaunch_conseiller(cfg: VpsConfig) -> tuple[bool, str]:
    script = """
import json, os
from config_loader import load_config
from commune_passes import initial_geo_state

preset = 'cabinets_conseiller_financier'
data_root = os.environ['HERCULE_DATA_ROOT']
out_dir = f'{data_root}/streamlit_scraper/output/{preset}'
removed = []
for pattern in ('workspace_emails.json', 'workspace_emails.json.tmp'):
    path = os.path.join(out_dir, pattern)
    if os.path.isfile(path):
        os.remove(path)
        removed.append(path)
config = load_config(preset)
geo_phase, query_pass, skip_places = initial_geo_state(config)
path = f'{out_dir}/scrape_state.json'
with open(path, encoding='utf-8') as f:
    state = json.load(f)
before = {k: state.get(k) for k in ('geo_reload_exhausted','reload_round','query_pass','geo_phase','status','continuous_zero_streak')}
state.pop('geo_reload_exhausted', None)
state['reload_round'] = 0
state['reload_round_pushed_start'] = int(state.get('instantly_pushed', 0) or 0)
state['geo_phase'] = geo_phase
state['query_pass'] = query_pass
state['skip_places'] = skip_places
state['last_completed_batch_index'] = -1
state['last_submitted_batch_index'] = -1
state['inflight_tasks'] = []
state['continuous_zero_streak'] = 0
state['status'] = 'incomplete'
with open(path, 'w', encoding='utf-8') as f:
    json.dump(state, f, indent=2)
print(json.dumps({'removed': removed, 'before': before, 'after': {'query_pass': state.get('query_pass'), 'geo_phase': state.get('geo_phase'), 'reload_round': state.get('reload_round')}}))
"""
    import base64

    repo = cfg.repo_root
    encoded = base64.b64encode(script.encode()).decode()
    cmd = (
        f"cd {repo}/scraper && "
        f"export HERCULE_DATA_ROOT={cfg.data_root} PYTHONPATH={repo} && "
        f"echo {encoded} | base64 -d | {repo}/.venv/bin/python"
    )
    code, out, err = _ssh_exec(cfg, cmd, timeout=120)
    if code != 0:
        return False, err or out or f"exit {code}"
    restart = _ssh_exec(cfg, "systemctl restart hercule-scraper-conseiller-financier", timeout=60)
    return restart[0] == 0, out.strip() or "restarted"


def sample_comptable_speed(cfg: VpsConfig, *, minutes: float = 10.0) -> dict[str, object]:
    preset = COMPTABLE_PRESET
    data_root = cfg.data_root
    state_path = f"{data_root}/streamlit_scraper/output/{preset}/scrape_state.json"
    cmd_start = f"python3 -c \"import json; d=json.load(open('{state_path}')); print(d.get('instantly_pushed',0), d.get('leads_saved',0))\""
    _, start_out, _ = _ssh_exec(cfg, cmd_start, timeout=15)
    parts = start_out.strip().split()
    pushed_start = int(parts[0]) if parts else 0
    saved_start = int(parts[1]) if len(parts) > 1 else 0
    time.sleep(max(minutes * 60.0, 60.0))
    _, end_out, _ = _ssh_exec(cfg, cmd_start, timeout=15)
    parts = end_out.strip().split()
    pushed_end = int(parts[0]) if parts else 0
    saved_end = int(parts[1]) if len(parts) > 1 else 0
    elapsed_s = minutes * 60.0
    pushed_delta = pushed_end - pushed_start
    saved_delta = saved_end - saved_start
    pushed_per_hour = pushed_delta / (elapsed_s / 3600.0) if elapsed_s > 0 else 0.0
    saved_per_hour = saved_delta / (elapsed_s / 3600.0) if elapsed_s > 0 else 0.0
    tail_cmd = f"tail -n 8 {data_root}/streamlit_scraper/output/{preset}/scrape.log"
    _, log_tail, _ = _ssh_exec(cfg, tail_cmd, timeout=15)
    return {
        "preset": preset,
        "sample_minutes": minutes,
        "pushed_start": pushed_start,
        "pushed_end": pushed_end,
        "pushed_delta": pushed_delta,
        "pushed_per_hour": round(pushed_per_hour, 1),
        "saved_delta": saved_delta,
        "saved_per_hour": round(saved_per_hour, 1),
        "log_tail": log_tail,
    }


def main() -> int:
    cfg = VpsConfig.from_env()
    if not cfg:
        print("VPS not configured")
        return 1

    results: dict[str, object] = {}
    ok_sync, uploaded = sync_repo_files(cfg)
    results["sync"] = {"ok": ok_sync, "uploaded": uploaded}
    if not ok_sync:
        print(json.dumps(results, indent=2))
        return 1

    ok_disable, msg_disable = disable_deprecated_comptable_vol(cfg)
    results["deprecated_vol_disabled"] = msg_disable

    ok_tune, msg_tune = patch_comptable_systemd_tuning(cfg)
    results["comptable_systemd_tuning"] = {"ok": ok_tune, "detail": msg_tune}

    ok1, msg1 = relaunch_comptable_fresh_geo(cfg)
    results["comptable_fresh_geo"] = msg1

    print("Sampling comptable speed (10 min)...", flush=True)
    results["speed_sample"] = sample_comptable_speed(cfg, minutes=10.0)

    print(json.dumps(results, indent=2, default=str))
    return 0 if ok1 and ok_disable else 1


if __name__ == "__main__":
    raise SystemExit(main())
