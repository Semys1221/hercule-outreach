"""Auto-discover scraper presets from *_config.py modules."""

from __future__ import annotations

import importlib
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

_LIB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CONFIGS_DIR = os.path.join(_LIB_DIR, "configs")
_CACHE: dict[str, PresetMeta] | None = None


@dataclass(frozen=True)
class PresetMeta:
    preset_id: str
    label: str
    module_name: str
    config_path: str
    loader: Callable[[], dict[str, Any]]
    niche_group: str = ""
    niche_group_label: str = ""
    subniche_label: str = ""


def _ensure_lib_on_path() -> None:
    for path in (_LIB_DIR, _CONFIGS_DIR):
        if path not in sys.path:
            sys.path.insert(0, path)


def _expected_module_name(preset_id: str) -> str:
    return f"{preset_id}_config"


def _iter_config_files() -> list[tuple[str, str]]:
    """Return (filename, absolute path) for presets under configs/ only."""
    found: list[tuple[str, str]] = []
    if not os.path.isdir(_CONFIGS_DIR):
        return found
    for filename in sorted(os.listdir(_CONFIGS_DIR)):
        if not filename.endswith("_config.py") or filename.startswith("._"):
            continue
        found.append((filename, os.path.join(_CONFIGS_DIR, filename)))
    return found


def _load_preset_file(filename: str, config_path: str) -> PresetMeta:
    module_name = filename[:-3]
    module = importlib.import_module(module_name)
    preset_id = getattr(module, "PRESET_ID", None)
    label = getattr(module, "PRESET_LABEL", None)
    config = getattr(module, "CONFIG", None)

    if not isinstance(preset_id, str) or not preset_id.strip():
        raise ValueError(f"{filename}: missing PRESET_ID")
    if not isinstance(label, str) or not label.strip():
        raise ValueError(f"{filename}: missing PRESET_LABEL")
    if not isinstance(config, dict):
        raise ValueError(f"{filename}: missing CONFIG dict")

    preset_id = preset_id.strip()
    if _expected_module_name(preset_id) != module_name:
        raise ValueError(
            f"{filename}: PRESET_ID {preset_id!r} must match file "
            f"{_expected_module_name(preset_id)}.py"
        )

    niche_group = str(getattr(module, "NICHE_GROUP", "") or "").strip()
    niche_group_label = str(getattr(module, "NICHE_GROUP_LABEL", "") or "").strip()
    subniche_label = str(getattr(module, "SUBNICHE_LABEL", "") or "").strip()
    if isinstance(config, dict):
        if not niche_group:
            niche_group = str(config.get("NICHE_GROUP") or "").strip()
        if not niche_group_label:
            niche_group_label = str(config.get("NICHE_GROUP_LABEL") or "").strip()
        if not subniche_label:
            subniche_label = str(config.get("SUBNICHE_LABEL") or "").strip()
    if not niche_group:
        niche_group = preset_id
    if not niche_group_label:
        niche_group_label = label.strip()
    if not subniche_label:
        subniche_label = label.strip()

    return PresetMeta(
        preset_id=preset_id,
        label=label.strip(),
        module_name=module_name,
        config_path=config_path,
        loader=lambda m=module: dict(m.CONFIG),
        niche_group=niche_group,
        niche_group_label=niche_group_label,
        subniche_label=subniche_label,
    )


def discover_presets(*, use_cache: bool = True) -> dict[str, PresetMeta]:
    global _CACHE
    if use_cache and _CACHE is not None:
        return dict(_CACHE)

    _ensure_lib_on_path()
    found: dict[str, PresetMeta] = {}

    for filename, config_path in _iter_config_files():
        meta = _load_preset_file(filename, config_path)
        if meta.preset_id in found:
            raise ValueError(f"Duplicate PRESET_ID {meta.preset_id!r}")
        found[meta.preset_id] = meta

    if use_cache:
        _CACHE = dict(found)
    return found


def invalidate_preset_cache() -> None:
    global _CACHE
    _CACHE = None


def preset_config_path(preset_id: str) -> str:
    """Path for a preset config file (always under configs/)."""
    return os.path.join(_CONFIGS_DIR, f"{preset_id}_config.py")


def configs_dir() -> str:
    return _CONFIGS_DIR


def is_configs_preset(preset_id: str) -> bool:
    path = preset_config_path(preset_id)
    return os.path.dirname(os.path.abspath(path)) == os.path.abspath(_CONFIGS_DIR)


def _uuid(value: Any) -> str:
    return str(value or "").strip()


def list_niche_groups(*, use_cache: bool = True) -> dict[str, list[PresetMeta]]:
    """Group presets by niche_group; standalone presets form single-item groups."""
    presets = discover_presets(use_cache=use_cache)
    groups: dict[str, list[PresetMeta]] = {}
    for meta in presets.values():
        groups.setdefault(meta.niche_group, []).append(meta)
    for group_id in groups:
        groups[group_id].sort(key=lambda m: m.label)
    return dict(sorted(groups.items(), key=lambda item: item[1][0].niche_group_label))


def presets_in_group(group_id: str, *, use_cache: bool = True) -> list[str]:
    groups = list_niche_groups(use_cache=use_cache)
    return [meta.preset_id for meta in groups.get(group_id, [])]


def all_dedup_list_ids(preset_id: str, *, use_cache: bool = True) -> list[str]:
    """List IDs for dedup — own preset only (flat presets, no niche groups)."""
    presets = discover_presets(use_cache=use_cache)
    meta = presets.get(preset_id)
    if meta is None:
        return []
    list_id = _uuid(meta.loader().get("INSTANTLY_LIST_ID"))
    return [list_id] if list_id else []


def all_dedup_campaign_ids(preset_id: str, *, use_cache: bool = True) -> list[str]:
    """Campaign IDs for dedup — primary + INSTANTLY_DEDUP_CAMPAIGN_IDS from preset config."""
    presets = discover_presets(use_cache=use_cache)
    meta = presets.get(preset_id)
    if meta is None:
        return []
    config = meta.loader()
    seen: set[str] = set()
    ordered: list[str] = []
    primary = _uuid(config.get("INSTANTLY_CAMPAIGN_ID"))
    if primary:
        seen.add(primary)
        ordered.append(primary)
    dedup_ids = config.get("INSTANTLY_DEDUP_CAMPAIGN_IDS") or []
    if isinstance(dedup_ids, list):
        for raw in dedup_ids:
            cid = _uuid(raw)
            if cid and cid not in seen:
                seen.add(cid)
                ordered.append(cid)
    return ordered
