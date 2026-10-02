"""Discover scraper presets from scraper/presets.yaml."""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import yaml

_LIB_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PRESETS_PATH = os.path.join(_LIB_DIR, "presets.yaml")
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


def presets_manifest_path() -> str:
    return _PRESETS_PATH


def _load_manifest() -> dict[str, Any]:
    if not os.path.isfile(_PRESETS_PATH):
        return {"presets": {}}
    with open(_PRESETS_PATH, encoding="utf-8") as handle:
        data = yaml.safe_load(handle) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{_PRESETS_PATH}: expected mapping at root")
    return data


def discover_presets(*, use_cache: bool = True) -> dict[str, PresetMeta]:
    global _CACHE
    if use_cache and _CACHE is not None:
        return dict(_CACHE)

    manifest = _load_manifest()
    raw_presets = manifest.get("presets") or {}
    if not isinstance(raw_presets, dict):
        raise ValueError(f"{_PRESETS_PATH}: presets must be a mapping")

    found: dict[str, PresetMeta] = {}
    for preset_id, entry in sorted(raw_presets.items()):
        if not isinstance(entry, dict):
            raise ValueError(f"preset {preset_id!r}: expected mapping")
        label = str(entry.get("label") or preset_id).strip()
        config = entry.get("config")
        if not isinstance(config, dict):
            raise ValueError(f"preset {preset_id!r}: missing config dict")
        niche_group = str(entry.get("niche_group") or preset_id).strip()
        niche_group_label = str(entry.get("niche_group_label") or label).strip()
        subniche_label = str(entry.get("subniche_label") or label).strip()
        cfg_copy = dict(config)

        def _loader(c: dict[str, Any] = cfg_copy) -> dict[str, Any]:
            return dict(c)

        meta = PresetMeta(
            preset_id=preset_id,
            label=label,
            module_name=f"{preset_id}_config",
            config_path=_PRESETS_PATH,
            loader=_loader,
            niche_group=niche_group,
            niche_group_label=niche_group_label,
            subniche_label=subniche_label,
        )
        if preset_id in found:
            raise ValueError(f"Duplicate PRESET_ID {preset_id!r}")
        found[preset_id] = meta

    if use_cache:
        _CACHE = dict(found)
    return found


def invalidate_preset_cache() -> None:
    global _CACHE
    _CACHE = None


def preset_config_path(preset_id: str) -> str:
    return _PRESETS_PATH


def configs_dir() -> str:
    return os.path.dirname(_PRESETS_PATH)


def is_configs_preset(preset_id: str) -> bool:
    return preset_id in discover_presets(use_cache=True)


def _uuid(value: Any) -> str:
    return str(value or "").strip()


def list_niche_groups(*, use_cache: bool = True) -> dict[str, list[PresetMeta]]:
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
    presets = discover_presets(use_cache=use_cache)
    meta = presets.get(preset_id)
    if meta is None:
        return []
    list_id = _uuid(meta.loader().get("INSTANTLY_LIST_ID"))
    return [list_id] if list_id else []


def instantly_list_ids_for_preset(preset_id: str, *, use_cache: bool = True) -> list[str]:
    """Primary Instantly list + INSTANTLY_DEDUP_LIST_IDS for a preset."""
    presets = discover_presets(use_cache=use_cache)
    meta = presets.get(preset_id)
    if meta is None:
        return []
    config = meta.loader()
    seen: set[str] = set()
    ordered: list[str] = []
    for raw in (config.get("INSTANTLY_LIST_ID"), *(config.get("INSTANTLY_DEDUP_LIST_IDS") or [])):
        lid = _uuid(raw)
        if lid and lid not in seen:
            seen.add(lid)
            ordered.append(lid)
    return ordered


def preset_for_instantly_list_id(list_id: str, *, use_cache: bool = True) -> str | None:
    """Map an Instantly list UUID to the scraper preset that owns it."""
    needle = _uuid(list_id).lower()
    if not needle:
        return None
    for preset_id, meta in discover_presets(use_cache=use_cache).items():
        for candidate in instantly_list_ids_for_preset(preset_id, use_cache=use_cache):
            if candidate.lower() == needle:
                return preset_id
    return None


def all_dedup_campaign_ids(preset_id: str, *, use_cache: bool = True) -> list[str]:
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
