"""Adapter for the explainable mastery rule implementation."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
from types import ModuleType


def _load_rules() -> ModuleType:
    path = Path(__file__).resolve().parents[2] / "StudyCompanion-Hector" / "database" / "backend" / "algorithms" / "mastery_rules.py"
    spec = importlib.util.spec_from_file_location("studycompanion_hector_mastery_rules", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load mastery rules: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_RULES = _load_rules()
calculate_mastery_update = _RULES.calculate_mastery_update
