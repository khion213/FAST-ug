"""Camera capture, MediaPipe landmark inference and a physiological simulator.

Coordinate conventions
----------------------
* All landmarks are returned in pixel units of the RAW (non-mirrored) frame:
  shape (N, 3) with columns x, y, z (z scaled like x).
* Face: (478, 3) MediaPipe face mesh incl. iris.
* Hands: dict keyed by the subject's anatomical side, "R" or "L", each (21, 3).
  The hand model runs on the mirrored frame because MediaPipe assumes selfie
  (mirrored) input when it labels handedness; coordinates are mapped back.
"""
from __future__ import annotations

import math
import threading
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, Optional, Tuple

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal

from . import landmarks as LM
from .config import MODELS_DIR

FACE_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/face_landmarker/"
                  "face_landmarker/float16/latest/face_landmarker.task")
HAND_MODEL_URL = ("https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                  "hand_landmarker/float16/latest/hand_landmarker.task")
FACE_MODEL_FILE = "face_landmarker.task"
HAND_MODEL_FILE = "hand_landmarker.task"


@dataclass
class FrameResult:
    t: float                                   # time.monotonic() at grab
    frame: np.ndarray                          # raw BGR frame (not mirrored)
    face: Optional[np.ndarray] = None          # (478, 3) px
    hands: Dict[str, np.ndarray] = field(default_factory=dict)
    fps: float = 0.0
    simulated: bool = False

    @property
    def size(self) -> Tuple[int, int]:
        h, w = self.frame.shape[:2]
        return w, h


# --------------------------------------------------------------------------- #
# Model files
# --------------------------------------------------------------------------- #
def model_paths(models_dir: Path = MODELS_DIR) -> Tuple[Path, Path]:
    return models_dir / FACE_MODEL_FILE, models_dir / HAND_MODEL_FILE


def models_present(models_dir: Path = MODELS_DIR) -> bool:
    f, h = model_paths(models_dir)
    return f.exists() and f.stat().st_size > 1000 and h.exists() and h.stat().st_size > 1000


def download_models(progress: Optional[Callable[[str], None]] = None,
                    models_dir: Path = MODELS_DIR) -> None:
    """Fetch the two MediaPipe task files (about 11 MB in total)."""
    models_dir.mkdir(parents=True, exist_ok=True)
    for url, name in ((FACE_MODEL_URL, FACE_MODEL_FILE), (HAND_MODEL_URL, HAND_MODEL_FILE)):
        dest = models_dir / name
        if dest.exists() and dest.stat().st_size > 1000:
            continue
        if progress:
            progress("Downloading " + name)
        tmp = dest.with_suffix(".part")
        req = urllib.request.Request(url, headers={"User-Agent": "FAST-ug/1.0"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as fh:
            while True:
                chunk = resp.read(1 << 16)
                if not chunk:
                    break
                fh.write(chunk)
        tmp.replace(dest)


# --------------------------------------------------------------------------- #
# Landmark engine
# --------------------------------------------------------------------------- #
class LandmarkEngine:
    """Wraps MediaPipe Tasks (preferred) or the legacy Solutions API."""

    def __init__(self, models_dir: Path = MODELS_DIR, infer_width: int = 640):
        self.infer_width = infer_width
        self.backend = "none"
        self._face = None
        self._hands = None
        self._last_ts = 0
        self._mp = None
        try:
            import mediapipe as mp  # noqa: WPS433
            self._mp = mp
        except ImportError as exc:  # pragma: no cover
            raise RuntimeError("MediaPipe is not installed. Run: pip install mediapipe") from exc

        face_path, hand_path = model_paths(models_dir)
        if face_path.exists() and hand_path.exists():
            self._init_tasks(face_path, hand_path)
        elif hasattr(self._mp, "solutions"):
            self._init_solutions()
        else:
            raise RuntimeError("MediaPipe model files are missing. Use 'Download models' in "
                               "Settings, or place face_landmarker.task and hand_landmarker.task "
                               "in: " + str(models_dir))

    def _init_tasks(self, face_path: Path, hand_path: Path) -> None:
        from mediapipe.tasks.python import BaseOptions, vision
        mode = vision.RunningMode.VIDEO
        self._face = vision.FaceLandmarker.create_from_options(vision.FaceLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(face_path)),
            running_mode=mode, num_faces=1,
            min_face_detection_confidence=0.5, min_face_presence_confidence=0.5,
            min_tracking_confidence=0.5))
        self._hands = vision.HandLandmarker.create_from_options(vision.HandLandmarkerOptions(
            base_options=BaseOptions(model_asset_path=str(hand_path)),
            running_mode=mode, num_hands=2,
            min_hand_detection_confidence=0.5, min_hand_presence_confidence=0.5,
            min_tracking_confidence=0.5))
        self.backend = "tasks"

    def _init_solutions(self) -> None:  # pragma: no cover - only on old MediaPipe
        sol = self._mp.solutions
        self._face = sol.face_mesh.FaceMesh(max_num_faces=1, refine_landmarks=True,
                                            min_detection_confidence=0.5, min_tracking_confidence=0.5)
        self._hands = sol.hands.Hands(max_num_hands=2, min_detection_confidence=0.5,
                                      min_tracking_confidence=0.5)
        self.backend = "solutions"

    def close(self) -> None:
        for obj in (self._face, self._hands):
            try:
                if obj is not None:
                    obj.close()
            except Exception:  # noqa: BLE001
                pass

    def _timestamp(self, t: float) -> int:
        ts = int(t * 1000)
        if ts <= self._last_ts:
            ts = self._last_ts + 1
        self._last_ts = ts
        return ts

    def process(self, frame_bgr: np.ndarray, t: float, need_hands: bool
                ) -> Tuple[Optional[np.ndarray], Dict[str, np.ndarray]]:
        h, w = frame_bgr.shape[:2]
        scale = min(1.0, self.infer_width / float(w))
        small = cv2.resize(frame_bgr, (int(w * scale), int(h * scale))) if scale < 1 else frame_bgr
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        rgb_mirror = np.ascontiguousarray(rgb[:, ::-1])
        ts = self._timestamp(t)
        face, hands = None, {}

        if self.backend == "tasks":
            mp = self._mp
            img = mp.Image(image_format=mp.ImageFormat.SRGB, data=np.ascontiguousarray(rgb))
            res = self._face.detect_for_video(img, ts)
            if res.face_landmarks:
                face = np.array([(p.x * w, p.y * h, p.z * w) for p in res.face_landmarks[0]],
                                dtype=np.float32)
            if need_hands:
                img_m = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_mirror)
                hres = self._hands.detect_for_video(img_m, ts)
                for lms, handed in zip(hres.hand_landmarks, hres.handedness):
                    side = "L" if handed[0].category_name.lower().startswith("l") else "R"
                    arr = np.array([((1.0 - p.x) * w, p.y * h, p.z * w) for p in lms], dtype=np.float32)
                    if side not in hands:
                        hands[side] = arr
        elif self.backend == "solutions":  # pragma: no cover
            res = self._face.process(rgb)
            if res.multi_face_landmarks:
                face = np.array([(p.x * w, p.y * h, p.z * w)
                                 for p in res.multi_face_landmarks[0].landmark], dtype=np.float32)
            if need_hands:
                hres = self._hands.process(rgb_mirror)
                if hres.multi_hand_landmarks:
                    for lms, handed in zip(hres.multi_hand_landmarks, hres.multi_handedness):
                        side = "L" if handed.classification[0].label.lower().startswith("l") else "R"
                        arr = np.array([((1.0 - p.x) * w, p.y * h, p.z * w) for p in lms.landmark],
                                       dtype=np.float32)
                        if side not in hands:
                            hands[side] = arr
        if face is not None and face.shape[0] < 478:
            face = None  # iris points are required for gaze
        return face, hands


# --------------------------------------------------------------------------- #
# Workers
# --------------------------------------------------------------------------- #
class _BaseWorker(QThread):
    frame_ready = Signal(object)   # FrameResult
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stop = threading.Event()
        self.need_hands = False

    def stop(self) -> None:
        self._stop.set()
        self.wait(3000)


class CameraWorker(_BaseWorker):
    """Grabs frames from a webcam index or a video file and runs inference."""

    def __init__(self, source, width: int = 1280, height: int = 720, parent=None):
        super().__init__(parent)
        self.source = source
        self.width, self.height = width, height

    def _open(self):
        src = self.source
        if isinstance(src, str) and src.strip().isdigit():
            src = int(src.strip())
        if isinstance(src, int):
            api = cv2.CAP_DSHOW if hasattr(cv2, "CAP_DSHOW") and _is_windows() else cv2.CAP_ANY
            cap = cv2.VideoCapture(src, api)
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            return cap, False
        return cv2.VideoCapture(str(src)), True

    def run(self) -> None:
        try:
            engine = LandmarkEngine()
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
            return
        cap, is_file = self._open()
        if not cap.isOpened():
            self.failed.emit("Camera source '%s' could not be opened. Check Settings > Camera."
                             % self.source)
            engine.close()
            return
        self.status.emit("Camera online")
        file_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        last = time.monotonic()
        fps = 0.0
        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                if is_file:
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                self.failed.emit("The camera stopped sending frames.")
                break
            t = time.monotonic()
            try:
                face, hands = engine.process(frame, t, self.need_hands)
            except Exception as exc:  # noqa: BLE001
                self.failed.emit("Landmark inference failed: %s" % exc)
                break
            dt = t - last
            last = t
            if dt > 0:
                fps = 0.9 * fps + 0.1 * (1.0 / dt) if fps else 1.0 / dt
            self.frame_ready.emit(FrameResult(t=t, frame=frame, face=face, hands=hands, fps=fps))
            if is_file:
                spare = (1.0 / file_fps) - (time.monotonic() - t)
                if spare > 0:
                    time.sleep(spare)
        cap.release()
        engine.close()


def _is_windows() -> bool:
    import sys
    return sys.platform.startswith("win")


# --------------------------------------------------------------------------- #
# Simulator: synthetic landmarks driven by the running exam step
# --------------------------------------------------------------------------- #
class SimState:
    """Shared, read-mostly state the exam controller publishes for the simulator."""

    def __init__(self):
        self.step_key = ""
        self.step_t0 = 0.0
        self.gaze_target = 0.0       # expected gaze, +1 = subject's left, -1 = right
        self.scenario = "healthy"    # healthy | left_weakness | fatigue


class SimulatedWorker(_BaseWorker):
    """Generates plausible face/hand landmarks at 30 fps for testing and demos."""

    W, H = 1280, 720

    def __init__(self, state: SimState, seed: int = 7, parent=None):
        super().__init__(parent)
        self.state = state
        self.rng = np.random.default_rng(seed)
        self._template = _face_template(self.rng)
        self._gaze = 0.0
        self._gaze_target_seen = 0.0
        self._target_change_t = 0.0
        self._next_blink = 2.0
        self._blink_until = -1.0
        self._bg = _sim_background(self.W, self.H)

    def run(self) -> None:
        self.status.emit("Simulated feed, %s" % self.state.scenario.replace("_", " "))
        t0 = time.monotonic()
        period = 1.0 / 30.0
        while not self._stop.is_set():
            t = time.monotonic()
            res = self.synthesize(t, t - t0)
            res.fps = 30.0
            self.frame_ready.emit(res)
            spare = period - (time.monotonic() - t)
            if spare > 0:
                time.sleep(spare)

    # The synthesis is a pure function of time + state, so it is unit-testable.
    def synthesize(self, t: float, since_start: float) -> FrameResult:
        st = self.state
        scen = st.scenario
        weak = scen == "left_weakness"
        tired = scen == "fatigue"
        step = st.step_key
        ts = max(0.0, t - st.step_t0)
        rng = self.rng

        # ---- gaze: first-order response with latency to the target ----
        if abs(st.gaze_target - self._gaze_target_seen) > 1e-6:
            self._gaze_target_seen = st.gaze_target
            self._target_change_t = t
        latency = 0.26 if not tired else 0.36
        if weak:
            latency = 0.31
        effective = self._gaze if (t - self._target_change_t) < latency else self._gaze_target_seen
        if step == "pursuit":
            effective = st.gaze_target
        tau = 0.035 if step != "pursuit" else 0.12
        self._gaze += (effective - self._gaze) * min(1.0, (1.0 / 30.0) / tau)
        gaze_noise = 0.03 if not tired else 0.06
        gaze = self._gaze + rng.normal(0, gaze_noise)

        # ---- blinks ----
        blink_gap = (3.5, 1.2) if not tired else (1.6, 0.6)
        blink_len = 0.14 if not tired else 0.32
        if since_start >= self._next_blink:
            self._blink_until = since_start + max(0.08, rng.normal(blink_len, 0.03))
            if tired and rng.random() < 0.12:
                self._blink_until = since_start + 0.7   # micro-sleep
            self._next_blink = self._blink_until + max(0.6, rng.normal(*blink_gap))
        lid = 1.0
        if since_start < self._blink_until:
            lid = 0.05
        if tired:
            lid *= 0.82

        face_params = dict(lid_r=lid, lid_l=lid, smile_r=0.0, smile_l=0.0, brow_r=0.0,
                           brow_l=0.0, aperture=0.04, gaze=gaze, droop_l=0.0)
        if weak:
            face_params["droop_l"] = 0.045
        if step == "face_smile":
            ramp = min(1.0, ts / 0.6)
            face_params["smile_r"] = 1.0 * ramp
            face_params["smile_l"] = (0.38 if weak else 0.95) * ramp
            face_params["aperture"] = 0.08
        elif step == "face_brows":
            ramp = min(1.0, ts / 0.6)
            face_params["brow_r"] = 1.0 * ramp
            face_params["brow_l"] = (0.85 if weak else 0.97) * ramp  # forehead is partly spared
        elif step == "face_eyes":
            ramp = min(1.0, ts / 0.4)
            face_params["lid_r"] = 1.0 - 0.95 * ramp
            face_params["lid_l"] = 1.0 - (0.62 if weak else 0.94) * ramp
        elif step == "ddk":
            f = 5.6 if not weak else 3.4
            jitter = 0.0 if not weak else 0.45 * math.sin(2 * math.pi * 0.7 * ts)
            ph = 2 * math.pi * f * ts + jitter
            amp = 0.16 if not weak else 0.09
            face_params["aperture"] = 0.03 + amp * (0.5 + 0.5 * math.sin(ph))
            face_params["smile_r"] = 0.15 * (0.5 + 0.5 * math.sin(ph))
            face_params["smile_l"] = (0.05 if weak else 0.14) * (0.5 + 0.5 * math.sin(ph))
        elif step == "reading":
            env = 1.0 if (ts % 2.0) < 1.6 else 0.0          # phrases with pauses
            if weak:
                env *= 0.55
            ph = 2 * math.pi * 4.2 * ts
            face_params["aperture"] = 0.03 + env * 0.12 * (0.5 + 0.5 * math.sin(ph))
            face_params["smile_r"] = env * 0.1 * (0.5 + 0.5 * math.sin(ph))
            face_params["smile_l"] = env * (0.03 if weak else 0.1) * (0.5 + 0.5 * math.sin(ph))

        face = _render_face(self._template, face_params, rng, t)

        # ---- hands ----
        hands: Dict[str, np.ndarray] = {}
        if step in ("tap_R", "tap_L", "ram"):
            for side in ("R", "L"):
                if step == "tap_R" and side != "R":
                    continue
                if step == "tap_L" and side != "L":
                    continue
                if step.startswith("tap"):
                    f = 4.3 if not (weak and side == "L") else 2.6
                    amp = 1.0 if not (weak and side == "L") else 0.55
                    decay = 1.0 - (0.04 * ts if not (weak and side == "L") else 0.07 * ts)
                    pinch = 0.06 + amp * max(0.2, decay) * 0.85 * (0.5 + 0.5 * math.sin(2 * math.pi * f * ts))
                    hands[side] = _render_hand(side, pinch=pinch, roll=0.0, t=t, rng=rng)
                else:
                    f = 2.1 if not (weak and side == "L") else 1.25
                    amp = 0.95 if not (weak and side == "L") else 0.6
                    roll = amp * math.sin(2 * math.pi * f * ts)
                    hands[side] = _render_hand(side, pinch=0.8, roll=roll, t=t, rng=rng)

        frame = self._bg.copy()
        return FrameResult(t=t, frame=frame, face=face, hands=hands, fps=30.0, simulated=True)


def _sim_background(w: int, h: int) -> np.ndarray:
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    cx, cy = w / 2, h / 2
    r = np.sqrt(((xx - cx) / w) ** 2 + ((yy - cy) / h) ** 2)
    base = np.clip(46 - 40 * r, 14, 46)
    img = np.dstack([base * 1.15, base * 0.95, base * 0.8]).astype(np.uint8)
    return img


def _ellipse_pts(cx, cy, rx, ry, n, start=-math.pi / 2):
    a = start + np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.stack([cx + rx * np.cos(a), cy + ry * np.sin(a)], axis=1)


def _face_template(rng) -> Dict[str, object]:
    """Static geometry (px) for a frontal face in a 1280x720 frame."""
    cx, cy = 640.0, 345.0
    pts = np.zeros((478, 3), dtype=np.float32)
    # fill everything inside the face ellipse first
    ang = rng.uniform(0, 2 * math.pi, 478)
    rad = np.sqrt(rng.uniform(0, 1, 478))
    pts[:, 0] = cx + 140 * rad * np.cos(ang)
    pts[:, 1] = cy + 175 * rad * np.sin(ang)
    oval = list(LM.FACE_OVAL[:-1])
    ring = _ellipse_pts(cx, cy, 150, 190, len(oval))
    for idx, p in zip(oval, ring):
        pts[idx, :2] = p
    mid = list(LM.MIDLINE)
    ys = np.linspace(cy - 190, cy + 190, len(mid))
    for idx, y in zip(mid, ys):
        pts[idx, :2] = (cx, y)
    pts[LM.NASION, :2] = (cx, cy - 70)
    pts[LM.NOSE_TIP, :2] = (cx, cy + 20)
    return {"pts": pts, "cx": cx, "cy": cy}


def _place_eye(pts, ring, cx, cy, w, h_up, h_lo):
    n_half = (len(ring) - 1) // 2
    for k, idx in enumerate(ring[:-1]):
        if k <= n_half:
            a = math.pi - math.pi * k / n_half
            pts[idx, :2] = (cx + w * math.cos(a), cy - h_up * math.sin(a))
        else:
            a = -math.pi * (k - n_half) / n_half
            pts[idx, :2] = (cx + w * math.cos(a), cy - h_lo * math.sin(a))


def _place_lips(pts, ring, cr, cl, h_up, h_lo):
    n_half = (len(ring) - 1) // 2
    for k, idx in enumerate(ring[:-1]):
        if k <= n_half:
            u = k / n_half
            p = (1 - u) * cr + u * cl
            pts[idx, :2] = (p[0], p[1] - h_up * math.sin(math.pi * u))
        else:
            u = 1 - (k - n_half) / n_half
            p = (1 - u) * cr + u * cl
            pts[idx, :2] = (p[0], p[1] + h_lo * math.sin(math.pi * u))


def _render_face(tpl, prm, rng, t) -> np.ndarray:
    pts = tpl["pts"].copy()
    cx, cy = tpl["cx"], tpl["cy"]
    eye_y = cy - 45
    eye_dx, eye_w, eye_h = 62.0, 27.0, 11.0
    gaze_px = 7.5 * float(np.clip(prm["gaze"], -1.4, 1.4))
    # subject's right eye appears on the image left
    for ring, ex, lid, iris_c, iris_ring in (
            (LM.R_EYE_RING, cx - eye_dx, prm["lid_r"], LM.R_IRIS_CENTER, LM.R_IRIS_RING),
            (LM.L_EYE_RING, cx + eye_dx, prm["lid_l"], LM.L_IRIS_CENTER, LM.L_IRIS_RING)):
        _place_eye(pts, ring, ex, eye_y, eye_w, eye_h * max(0.02, lid), 4.0)
        ic = (ex + gaze_px, eye_y - 1.5)
        pts[iris_c, :2] = ic
        for k, idx in enumerate(iris_ring):
            a = k * math.pi / 2
            pts[idx, :2] = (ic[0] + 6.5 * math.cos(a), ic[1] + 6.5 * math.sin(a))
    # brows
    for line, bx, raise_ in ((LM.R_BROW_LINE, cx - eye_dx, prm["brow_r"]),
                             (LM.L_BROW_LINE, cx + eye_dx, prm["brow_l"])):
        xs = np.linspace(bx - 34, bx + 34, len(line))
        for idx, x in zip(line, xs):
            arch = 7.0 * math.cos((x - bx) / 34.0 * math.pi / 2)
            pts[idx, :2] = (x, eye_y - 32 - arch - 14.0 * raise_)
    # mouth corners
    mouth_y = cy + 88
    cr = np.array([cx - 46 - 9 * prm["smile_r"], mouth_y - 13 * prm["smile_r"]])
    cl = np.array([cx + 46 + 9 * prm["smile_l"], mouth_y - 13 * prm["smile_l"] + 124.0 * prm["droop_l"]])
    ap = prm["aperture"] * 124.0       # aperture is in IOD units (IOD = 124 px here)
    _place_lips(pts, LM.LIPS_OUTER, cr, cl, 9 + ap / 2, 10 + ap / 2)
    _place_lips(pts, LM.LIPS_INNER, cr + (6, 0), cl - (6, 0), ap / 2, ap / 2)
    pts[LM.LIP_INNER_UP, :2] = (cx, mouth_y - ap / 2 - 0.2)
    pts[LM.LIP_INNER_LO, :2] = (cx, mouth_y + ap / 2 + 0.2)
    # small head sway + sensor noise
    sway = np.array([3.0 * math.sin(0.31 * t), 2.0 * math.sin(0.23 * t + 1.0)])
    pts[:, :2] += sway
    pts[:, :2] += rng.normal(0, 0.35, (pts.shape[0], 2))
    return pts


def _render_hand(side: str, pinch: float, roll: float, t: float, rng) -> np.ndarray:
    """21 hand points. pinch: thumb-index gap in hand-size units; roll in [-1, 1]."""
    size = 120.0
    base_x = 330.0 if side == "R" else 950.0     # subject's right hand is on the image left
    wrist = np.array([base_x, 620.0])
    s = -1.0 if side == "R" else 1.0             # thumb side for a palm facing the camera
    xs = s * 1.0
    # local layout (x to the side, y up = negative image y)
    local = {
        0: (0.0, 0.0), 1: (0.28 * xs, -0.22), 2: (0.5 * xs, -0.42), 3: (0.62 * xs, -0.62),
        5: (0.33 * xs, -0.95), 6: (0.36 * xs, -1.3), 7: (0.38 * xs, -1.55), 8: (0.4 * xs, -1.75),
        9: (0.08 * xs, -1.0), 10: (0.08 * xs, -1.4), 11: (0.08 * xs, -1.68), 12: (0.08 * xs, -1.9),
        13: (-0.15 * xs, -0.95), 14: (-0.17 * xs, -1.3), 15: (-0.18 * xs, -1.55), 16: (-0.19 * xs, -1.72),
        17: (-0.36 * xs, -0.85), 18: (-0.4 * xs, -1.1), 19: (-0.42 * xs, -1.28), 20: (-0.44 * xs, -1.42),
    }
    pts = np.zeros((21, 3), dtype=np.float32)
    for k, (lx, ly) in local.items():
        # roll in [-1, 1] squeezes and flips the hand width (pronation/supination)
        pts[k, :2] = wrist + size * np.array([lx * roll if roll else lx, ly])
    # thumb tip placed relative to the index tip by the pinch gap
    idx_tip = pts[8, :2]
    thumb_dir = np.array([s * 0.55, 0.85])
    thumb_dir /= np.linalg.norm(thumb_dir)
    pts[4, :2] = idx_tip + thumb_dir * pinch * size
    pts[3, :2] = 0.6 * pts[4, :2] + 0.4 * pts[2, :2]
    pts[:, :2] += np.array([2.0 * math.sin(0.5 * t), 2.0 * math.cos(0.4 * t)])
    pts[:, :2] += rng.normal(0, 0.6, (21, 2))
    return pts
