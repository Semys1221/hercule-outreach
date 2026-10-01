"""Persistent data directory for streamlit_clean artifacts and checkpoints."""

from __future__ import annotations

import os
import sys

_LIB_DIR = os.path.dirname(os.path.abspath(__file__))
_APP_DIR = os.path.dirname(_LIB_DIR)
if _APP_DIR not in sys.path:
    sys.path.insert(0, _APP_DIR)
from outreach_data import clean_data_dir  # noqa: E402


def data_dir() -> str:
    return clean_data_dir()
