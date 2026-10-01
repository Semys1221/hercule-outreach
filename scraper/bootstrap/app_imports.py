"""Load satellite Streamlit app modules without clobbering shared names in sys.modules."""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

_CONFLICTING_NAMES = (
    "config",
    "supabase_repo",
    "onboarding",
    "pipeline",
    "prompt_store",
)


def load_app_module(app_dir: Path | str, module_name: str) -> ModuleType:
    """Import ``module_name`` from a satellite app dir (reply agent, subsequence, …)."""
    app_path = Path(app_dir).resolve()
    module_path = app_path / f"{module_name}.py"
    if not module_path.is_file():
        raise ImportError(f"Cannot find {module_path}")

    saved_path = sys.path[:]
    saved_modules = {
        name: sys.modules[name] for name in _CONFLICTING_NAMES if name in sys.modules
    }
    for name in saved_modules:
        del sys.modules[name]

    app_dir_str = str(app_path)
    filtered_path = [p for p in saved_path if os.path.abspath(p) != app_dir_str]
    sys.path = [app_dir_str] + filtered_path

    unique_name = f"{app_path.name}_{module_name}"
    try:
        spec = importlib.util.spec_from_file_location(unique_name, module_path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot load spec for {module_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[unique_name] = module
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path = saved_path
        for name, module in saved_modules.items():
            sys.modules[name] = module
