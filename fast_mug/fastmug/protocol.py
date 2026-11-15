"""Exam protocols and the controller that runs them in real time."""
from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np
from PySide6.QtCore import QObject, QTimer, Signal

from . import __version__
from . import overlay
from . import signals as S
from .scoring import score_session
from .storage import Store, utc_now_iso
from .vision import FrameResult, SimState

READING_LINES = ("You know how.", "Down to earth.", "I got home from work.",
                 "Near the table in the dining room.",
                 "They heard him speak on the radio last night.")


@dataclass
class Step:
    key: str
    title: str
    instruction: str
    duration: float                 # recorded seconds (after the lead-in)
    stage: str = "camera"          # camera | fixation | saccade | pursuit | reading
    needs: str = "face"            # face | hand_R | hand_L | hands
    live: str = "openness"         # which signal the live trace shows
    lead_in: float = 1.5
    snapshot: str = ""             # caption of a saved still, empty for none
    group: str = ""

    @property
    def total(self) -> float:
        return self.lead_in + self.duration


def _steps(kind: str) -> List[Step]:
    align = Step("align", "Get in position",
                 "Sit about an arm's length from the camera with your whole face in the frame "
                 "and good light on it.", 3.0, needs="face", live="openness", lead_in=0.0,
                 group="Setup")
    observe = Step("observe", "Relaxed fixation",
                   "Look at the cross and breathe normally. Blink as you usually would.",
                   20.0, stage="fixation", live="openness", lead_in=1.0, group="Alertness")
    saccade = Step("saccade", "Look at the dot",
                   "Keep your head still. When a dot appears, look at it as fast as you can.",
                   0.0, stage="saccade", live="gaze", lead_in=1.0, group="Alertness")
    face = [
        Step("face_neutral", "Relaxed face", "Relax your face and look into the camera.",
             3.0, live="mouth_tilt", lead_in=1.0, snapshot="Relaxed face", group="Face"),
        Step("face_smile", "Smile", "Smile widely and show your teeth. Hold it.",
             3.5, live="smile", lead_in=1.2, snapshot="Smile", group="Face"),
        Step("face_brows", "Raise your eyebrows", "Raise your eyebrows as high as you can. Hold it.",
             3.5, live="brows", lead_in=1.2, group="Face"),
        Step("face_eyes", "Close your eyes tightly", "Squeeze both eyes shut. Hold until the tone.",
             3.5, live="openness", lead_in=1.2, snapshot="Forced eye closure", group="Face"),
    ]
    speech = [
        Step("ddk", "Say pa-ta-ka", "Repeat pa-ta-ka as fast and as clearly as you can.",
             8.0, live="mouth", lead_in=1.5, group="Speech"),
        Step("reading", "Read aloud", "Read these lines aloud at your normal pace.",
             8.0, stage="reading", live="mouth", lead_in=1.0, group="Speech"),
    ]
    hands = [
        Step("tap_R", "Right hand tapping",
             "Raise your right hand beside your face. Tap your thumb and index finger "
             "together, as fast and as wide as you can.", 8.0, needs="hand_R", live="pinch_R",
             lead_in=2.5, snapshot="Right hand tapping", group="Hands"),
        Step("tap_L", "Left hand tapping",
             "Now your left hand. Tap thumb and index finger, fast and wide.", 8.0,
             needs="hand_L", live="pinch_L", lead_in=2.5, snapshot="Left hand tapping", group="Hands"),
        Step("ram", "Turn both hands",
             "Raise both hands, palms toward the camera. Turn them over and back as fast "
             "as you can.", 8.0, needs="hands", live="roll", lead_in=2.5, group="Hands"),
    ]
    pursuit = Step("pursuit", "Follow the dot",
                   "Keep your head still and follow the moving dot with your eyes.",
                   8.0, stage="pursuit", live="gaze", lead_in=1.0, group="Eye movements")
    if kind == "daily":
        return [align, observe, saccade] + face + speech + hands + [pursuit]
    return [align] + face + speech + hands + [pursuit]


PROTOCOL_TITLES = {"daily": "Daily check", "neuro": "Neuro exam"}
PURSUIT_HZ = 0.25
PURSUIT_AMP = 0.8          # fraction of the half-width of the stage


def saccade_schedule(n: int = 8, seed: Optional[int] = None) -> List[Tuple[float, float, float]]:
    """(fixation start, target onset, target end) in step seconds, plus x position."""
    rng = random.Random(seed)
    sides = [-1, 1] * (n // 2)
    rng.shuffle(sides)
    t = 0.0
    out = []
    for s in sides:
        fix = rng.uniform(0.9, 1.5)
        onset = t + fix
        end = onset + 1.0
        out.append((onset, end, 0.72 * s))
        t = end
    return out


class ExamController(QObject):
    step_changed = Signal(int, object)          # index, Step
    progress = Signal(float, float, float, bool)  # step fraction, seconds left, total fraction, recording
    stimulus = Signal(object)                   # dict for the stage
    live_sample = Signal(float, float)          # t, value
    notice = Signal(str)                        # "" clears
    need_hands = Signal(bool)
    finished = Signal(object)                   # session dict
    aborted = Signal(str)

    def __init__(self, store: Store, settings, parent=None, clock: Optional[Callable[[], float]] = None,
                 use_timer: bool = True):
        super().__init__(parent)
        self._clock = clock or time.monotonic
        self._use_timer = use_timer
        self.store = store
        self.settings = settings
        self.sim: Optional[SimState] = None
        self._timer = QTimer(self)
        self._timer.setInterval(15)
        self._timer.timeout.connect(self._tick)
        self.running = False
        self.steps: List[Step] = []
        self._reset()

    # ------------------------------------------------------------------ API
    def _reset(self):
        self.idx = -1
        self.kind = ""
        self.member: Dict = {}
        self.self_report: Dict = {}
        self._rec: Dict[str, Tuple[List[float], Dict[str, List[float]]]] = {}
        self._snaps: Dict[str, Tuple[np.ndarray, Optional[np.ndarray], Dict]] = {}
        self._sacc_plan: List[Tuple[float, float, float]] = []
        self._sacc_onsets: List[Tuple[float, int]] = []
        self._sacc_shown = -1
        self._align_acc = 0.0
        self._last_face_t = 0.0
        self._last_hand_t: Dict[str, float] = {"R": 0.0, "L": 0.0}
        self._last_tick = 0.0
        self._started_utc = ""
        self._t_start = 0.0
        self._fps: List[float] = []
        self._simulated = False

    def start(self, kind: str, member: Dict, self_report: Optional[Dict] = None) -> None:
        self._reset()
        self.kind = kind
        self.member = dict(member)
        self.self_report = dict(self_report or {})
        self.steps = _steps(kind)
        sched = saccade_schedule(8)
        self._sacc_plan = sched
        for st in self.steps:
            if st.key == "saccade":
                st.duration = sched[-1][1] + 0.4
        self._started_utc = utc_now_iso()
        self._t_start = self._clock()
        self.running = True
        self._enter(0)
        self._last_tick = self._clock()
        if self._use_timer:
            self._timer.start()

    def abort(self, reason: str = "Exam stopped.") -> None:
        if not self.running:
            return
        self.running = False
        self._timer.stop()
        self.need_hands.emit(False)
        if self.sim:
            self.sim.step_key = ""
            self.sim.gaze_target = 0.0
        self.aborted.emit(reason)

    @property
    def total_duration(self) -> float:
        return sum(s.total for s in self.steps)

    # ------------------------------------------------------------- frames
    def on_frame(self, res: FrameResult) -> None:
        if not self.running or self.idx < 0:
            return
        self._simulated = self._simulated or res.simulated
        if res.fps:
            self._fps.append(res.fps)
        if res.face is not None:
            self._last_face_t = res.t
        for side in res.hands:
            self._last_hand_t[side] = res.t
        step = self.steps[self.idx]
        t_rel = res.t - self._step_t0 - step.lead_in
        feats = S.frame_features(res.face, res.hands)
        self._emit_live(step, t_rel, feats)
        if t_rel < 0 or step.key == "align":
            return
        ts, fd = self._rec.setdefault(step.key, ([], {}))
        ts.append(t_rel)
        for k, v in feats.items():
            fd.setdefault(k, []).append(v)
        if step.snapshot and step.key not in self._snaps and t_rel >= 0.7 * step.duration:
            ok = res.face is not None
            if step.needs.startswith("hand"):
                ok = bool(res.hands)
            if ok:
                self._snaps[step.key] = (res.frame.copy(),
                                         None if res.face is None else res.face.copy(),
                                         {k: v.copy() for k, v in res.hands.items()})

    def _emit_live(self, step: Step, t_rel: float, f: Dict[str, float]) -> None:
        v = float("nan")
        live = step.live
        if live == "openness":
            v = np.nanmean([f["ear_r"], f["ear_l"]]) / 0.3
        elif live == "gaze":
            v = np.nanmean([f["gaze_r"], f["gaze_l"]]) - 0.5
        elif live == "mouth":
            v = f["mouth_ap"]
        elif live == "mouth_tilt":
            v = f["cl_y"] - f["cr_y"]
        elif live == "smile":
            v = -0.5 * (f["cr_y"] + f["cl_y"])
        elif live == "brows":
            v = -0.5 * (f["brow_r"] + f["brow_l"])
        elif live == "pinch_R":
            v = f["pinch_R"]
        elif live == "pinch_L":
            v = f["pinch_L"]
        elif live == "roll":
            v = np.nanmean([f["roll_R"], -f["roll_L"]]) if np.isfinite(f["roll_R"]) or np.isfinite(f["roll_L"]) else float("nan")
        if np.isfinite(v):
            self.live_sample.emit(float(t_rel), float(v))

    # --------------------------------------------------------------- clock
    def _enter(self, idx: int) -> None:
        self.idx = idx
        step = self.steps[idx]
        self._step_t0 = self._clock()
        self._sacc_shown = -1
        self.need_hands.emit(step.needs.startswith("hand"))
        if self.sim:
            self.sim.step_key = step.key
            self.sim.step_t0 = self._step_t0 + step.lead_in
            self.sim.gaze_target = 0.0
        self.step_changed.emit(idx, step)

    def _requirement_met(self, step: Step, now: float) -> bool:
        fresh = 0.35
        if step.needs == "face":
            return now - self._last_face_t < fresh
        if step.needs == "hand_R":
            return now - self._last_hand_t["R"] < fresh
        if step.needs == "hand_L":
            return now - self._last_hand_t["L"] < fresh
        return (now - self._last_hand_t["R"] < fresh) and (now - self._last_hand_t["L"] < fresh)

    def _tick(self) -> None:
        if not self.running:
            return
        now = self._clock()
        dt = now - self._last_tick
        self._last_tick = now
        step = self.steps[self.idx]
        met = self._requirement_met(step, now)
        if step.key == "align":
            if met:
                self._align_acc += dt
                self.notice.emit("")
            else:
                self._align_acc = max(0.0, self._align_acc - dt)
                self.notice.emit("Face not found. Move into the frame and face the light.")
            elapsed = self._align_acc
            if now - self._step_t0 > 45 and not met:
                self.abort("No face was detected for 45 seconds.")
                return
        else:
            elapsed = now - self._step_t0
            rec = elapsed >= step.lead_in
            if rec and not met:
                what = {"face": "Face not visible", "hand_R": "Right hand not visible",
                        "hand_L": "Left hand not visible", "hands": "Both hands must be visible"}
                self.notice.emit(what[step.needs] + ". Keep it inside the frame.")
            else:
                self.notice.emit("")
        self._update_stimulus(step, elapsed - step.lead_in, now)
        total_done = sum(s.total for s in self.steps[: self.idx]) + min(elapsed, step.total)
        frac = min(1.0, elapsed / step.total) if step.total > 0 else 1.0
        self.progress.emit(frac, max(0.0, step.total - elapsed), total_done / self.total_duration,
                           elapsed >= step.lead_in and step.key != "align")
        if elapsed >= step.total:
            if self.idx + 1 < len(self.steps):
                self._enter(self.idx + 1)
            else:
                self._finish()

    def _update_stimulus(self, step: Step, e: float, now: float) -> None:
        stim: Dict = {"kind": step.stage}
        target = 0.0
        if step.stage == "fixation":
            stim.update(x=0.0, y=0.0)
        elif step.stage == "saccade":
            stim.update(kind="saccade", x=0.0, y=0.0, show=False)
            for i, (onset, end, x) in enumerate(self._sacc_plan):
                if onset <= e < end:
                    stim.update(x=x, show=True)
                    target = 1.0 if x < 0 else -1.0     # screen-left is the subject's left
                    if self._sacc_shown != i:
                        self._sacc_shown = i
                        self._sacc_onsets.append((e, int(target)))
                    break
        elif step.stage == "pursuit":
            if e < 0:
                x = 0.0
            else:
                x = PURSUIT_AMP * math.sin(2 * math.pi * PURSUIT_HZ * e)
            stim.update(x=x, y=0.0)
            target = -x / PURSUIT_AMP
        elif step.stage == "reading":
            stim.update(lines=READING_LINES)
        if self.sim:
            self.sim.gaze_target = target
        self.stimulus.emit(stim)

    # -------------------------------------------------------------- finish
    def _traces(self) -> Dict[str, S.Trace]:
        return {k: S.Trace(ts, fd) for k, (ts, fd) in self._rec.items()}

    def compute_metrics(self, tr: Dict[str, S.Trace]) -> Tuple[Dict[str, float], Dict]:
        empty = S.Trace([], {})
        m: Dict[str, float] = {}
        extra: Dict = {}
        if "observe" in tr:
            m.update(S.alertness_metrics(tr["observe"]))
        if "saccade" in tr:
            sm, rows = S.saccade_metrics(tr["saccade"], self._sacc_onsets)
            m.update(sm)
            extra["saccade_trials"] = rows
        m.update(S.face_metrics(tr.get("face_neutral", empty), tr.get("face_smile", empty),
                                tr.get("face_brows", empty), tr.get("face_eyes", empty)))
        m.update(S.speech_metrics(tr.get("ddk", empty), tr.get("reading", empty)))
        m.update(S.tapping_metrics(tr.get("tap_R", empty), "R"))
        m.update(S.tapping_metrics(tr.get("tap_L", empty), "L"))
        m.update(S.ram_metrics(tr.get("ram", empty)))
        m.update(S.symmetry_pairs(m))
        if "pursuit" in tr:
            p = tr["pursuit"]
            target = -np.sin(2 * math.pi * PURSUIT_HZ * p.t)
            m.update(S.pursuit_metrics(p, target))
        clean = {k: float(v) for k, v in m.items() if v is not None and np.isfinite(v)}
        extra["weaker_side"] = S.weaker_side(clean)
        return clean, extra

    def _finish(self) -> None:
        self.running = False
        self._timer.stop()
        self.need_hands.emit(False)
        if self.sim:
            self.sim.step_key = ""
            self.sim.gaze_target = 0.0
        try:
            session = self._build_session()
        except Exception as exc:  # noqa: BLE001
            self.aborted.emit("Could not compute results: %s" % exc)
            return
        self.finished.emit(session)

    def _build_session(self) -> Dict:
        tr = self._traces()
        metrics, extra = self.compute_metrics(tr)
        cid = self.member.get("id", "unknown")
        folder = self.store.new_session_dir(cid)
        window = int(self.settings.get("exam.baseline_window", 10))
        history = self.store.history(cid, window)
        verdict = score_session(metrics, history, self.settings.get("exam", {}), self.self_report)
        expected = {"daily": 18, "neuro": 14}.get(self.kind, 10)
        valid = len([k for k, v in verdict["metrics"].items() if v["status"] != "na"]) >= 0.6 * expected
        snaps = self._save_snapshots(folder)
        session = {
            "id": folder.name,
            "type": self.kind,
            "type_title": PROTOCOL_TITLES.get(self.kind, self.kind),
            "crew_id": cid,
            "crew": self.member,
            "started_utc": self._started_utc,
            "ended_utc": utc_now_iso(),
            "duration_s": round(self._clock() - self._t_start, 1),
            "raw_metrics": metrics,
            "verdict": verdict,
            "weaker_side": extra.get("weaker_side"),
            "saccade_trials": extra.get("saccade_trials", []),
            "self_report": self.self_report,
            "snapshots": snaps,
            "valid": bool(valid),
            "simulated": self._simulated,
            "camera_fps": round(float(np.median(self._fps)), 1) if self._fps else None,
            "app_version": __version__,
        }
        arrays: Dict[str, np.ndarray] = {}
        for key, t in tr.items():
            arrays[key + "__t"] = t.t.astype(np.float32)
            for fk, fv in t.f.items():
                arrays["%s__%s" % (key, fk)] = fv.astype(np.float32)
        self.store.save_session(folder, session, arrays)
        return session

    def _save_snapshots(self, folder: Path) -> List[Dict]:
        out = []
        for step in self.steps:
            if step.key not in self._snaps:
                continue
            frame, face, hands = self._snaps[step.key]
            img = overlay.annotate(frame, face, hands)
            img = overlay.crop_to_content(img, face if not hands else None, hands)
            name = "snap_%s.jpg" % step.key
            cv2.imwrite(str(folder / name), img, [cv2.IMWRITE_JPEG_QUALITY, 90])
            out.append({"file": name, "caption": step.snapshot, "step": step.key})
        return out
