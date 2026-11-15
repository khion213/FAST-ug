"""Paths and persistent user settings."""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ASSETS_DIR = PROJECT_ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
MODELS_DIR = PROJECT_ROOT / "models"


def default_data_dir() -> Path:
    if sys.platform.startswith("win"):
        base = Path(os.environ.get("APPDATA", Path.home()))
    else:
        base = Path.home()
    return base / "FAST-ug"


DEFAULTS: Dict[str, Any] = {
    "data_dir": str(default_data_dir()),
    "camera": {"source": 0, "width": 1280, "height": 720, "simulate": False, "scenario": "healthy"},
    "mission": {
        "name": "Artemis analogue",
        "vehicle": "Habitat module",
        "start_utc": "2026-11-01T00:00:00",
    },
    "email": {
        "host": "smtp.gmail.com",
        "port": 465,
        "security": "SSL",          # SSL | STARTTLS | NONE
        "username": "",
        "password": "",
        "sender": "",
        "flight_surgeon": "",
        "cc": "",
    },
    "exam": {
        "baseline_window": 10,       # daily checks used for the rolling baseline
        "min_personal_sessions": 3,  # below this, reference priors are blended in
        "watch_z": 2.0,
        "alert_z": 3.0,
    },
    "active_crew_id": "",
}


def _deep_merge(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    out = copy.deepcopy(base)
    for k, v in extra.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Settings:
    """JSON-backed settings stored next to the user data."""

    def __init__(self, path: Path = None):
        self.path = path or (default_data_dir() / "settings.json")
        self.data: Dict[str, Any] = copy.deepcopy(DEFAULTS)
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as fh:
                    self.data = _deep_merge(DEFAULTS, json.load(fh))
        except (OSError, ValueError):
            self.data = copy.deepcopy(DEFAULTS)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.data, fh, indent=2)
        tmp.replace(self.path)

    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self.data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    @property
    def data_dir(self) -> Path:
        p = Path(self.get("data_dir") or default_data_dir())
        p.mkdir(parents=True, exist_ok=True)
        return p
