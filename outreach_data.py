"""Persistent data paths for scraper/clean (VPS HERCULE_DATA_ROOT or local repo folders)."""

from __future__ import annotations

import os

_REPO_ROOT = os.path.dirname(os.path.abspath(__file__))

_LOCAL_APP_DIRS = {
    "streamlit_scraper": "scraper",
    "streamlit_clean": "clean",
}


def hercule_data_root() -> str:
    return os.environ.get("HERCULE_DATA_ROOT", "").strip()


def app_data_dir(app_name: str) -> str:
    root = hercule_data_root()
    if root:
        base = os.path.join(root, app_name)
    else:
        folder = _LOCAL_APP_DIRS.get(app_name, app_name)
        base = os.path.join(_REPO_ROOT, folder)
    os.makedirs(base, exist_ok=True)
    return base


def scraper_output_base() -> str:
    return os.path.join(app_data_dir("streamlit_scraper"), "output")


def default_sirene_path() -> str:
    data_dir = os.path.join(app_data_dir("streamlit_scraper"), "data")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "sirene.db")


def clean_data_dir() -> str:
    data_dir = os.path.join(app_data_dir("streamlit_clean"), "data")
    os.makedirs(data_dir, exist_ok=True)
    return data_dir
