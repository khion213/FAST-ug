"""Crew profiles and exam sessions on disk.

<data_dir>/crew.json
<data_dir>/sessions/<crew_id>/<session_id>/session.json
                                          /traces.npz
                                          /snap_*.jpg
                                          /report_*.docx
"""
from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(text: str) -> str:
    s = re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-").lower()
    return s or "crew"


class Store:
    def __init__(self, data_dir: Path):
        self.root = Path(data_dir)
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "sessions").mkdir(exist_ok=True)

    # ---------------------------------------------------------------- crew
    @property
    def crew_file(self) -> Path:
        return self.root / "crew.json"

    def crew(self) -> List[Dict]:
        if not self.crew_file.exists():
            return []
        try:
            with open(self.crew_file, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return []

    def save_crew(self, crew: List[Dict]) -> None:
        with open(self.crew_file, "w", encoding="utf-8") as fh:
            json.dump(crew, fh, indent=2)

    def upsert_member(self, member: Dict) -> Dict:
        crew = self.crew()
        if not member.get("id"):
            base = _slug(member.get("name", "crew"))
            ids = {c["id"] for c in crew}
            cid, k = base, 2
            while cid in ids:
                cid, k = "%s-%d" % (base, k), k + 1
            member["id"] = cid
            member.setdefault("created_utc", utc_now_iso())
            crew.append(member)
        else:
            for i, c in enumerate(crew):
                if c["id"] == member["id"]:
                    crew[i] = {**c, **member}
                    break
            else:
                crew.append(member)
        self.save_crew(crew)
        return member

    def delete_member(self, crew_id: str) -> None:
        self.save_crew([c for c in self.crew() if c["id"] != crew_id])

    def member(self, crew_id: str) -> Optional[Dict]:
        for c in self.crew():
            if c["id"] == crew_id:
                return c
        return None

    # ------------------------------------------------------------ sessions
    def crew_dir(self, crew_id: str) -> Path:
        d = self.root / "sessions" / crew_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def new_session_dir(self, crew_id: str) -> Path:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        d = self.crew_dir(crew_id) / ("%s_%s" % (stamp, uuid.uuid4().hex[:4]))
        d.mkdir(parents=True, exist_ok=True)
        return d

    def save_session(self, folder: Path, session: Dict, traces: Optional[Dict[str, np.ndarray]] = None
                     ) -> Path:
        folder.mkdir(parents=True, exist_ok=True)
        session["folder"] = str(folder)
        if traces:
            np.savez_compressed(folder / "traces.npz", **traces)
            session["traces_file"] = "traces.npz"
        path = folder / "session.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(session, fh, indent=2, default=_json_default)
        return path

    def sessions(self, crew_id: str, kind: Optional[str] = None) -> List[Dict]:
        out: List[Dict] = []
        d = self.root / "sessions" / crew_id
        if not d.exists():
            return out
        for f in sorted(d.glob("*/session.json")):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    s = json.load(fh)
                s["folder"] = str(f.parent)
                if kind is None or s.get("type") == kind:
                    out.append(s)
            except (OSError, ValueError):
                continue
        out.sort(key=lambda s: s.get("started_utc", ""))
        return out

    def load_traces(self, session: Dict) -> Dict[str, np.ndarray]:
        f = Path(session.get("folder", "")) / session.get("traces_file", "traces.npz")
        if not f.exists():
            return {}
        with np.load(f, allow_pickle=False) as z:
            return {k: z[k] for k in z.files}

    def history(self, crew_id: str, window: int, exclude_id: Optional[str] = None) -> Dict[str, List[float]]:
        """Raw metric values from the last `window` daily checks (the baseline pool)."""
        daily = [s for s in self.sessions(crew_id, "daily") if s.get("id") != exclude_id
                 and s.get("valid", True)]
        daily = daily[-window:]
        hist: Dict[str, List[float]] = {}
        for s in daily:
            for k, v in s.get("raw_metrics", {}).items():
                if v is not None:
                    hist.setdefault(k, []).append(float(v))
        return hist


def _json_default(o):
    if isinstance(o, (np.floating,)):
        v = float(o)
        return v if np.isfinite(v) else None
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o))
