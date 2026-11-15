"""Per-frame features and per-step clinical metrics (pure NumPy / SciPy).

Every function here is deterministic and free of Qt so it can be unit tested.
Units: face distances are expressed in inter-ocular distances (IOD); hand
distances in hand sizes (wrist to middle-finger knuckle).
"""
from __future__ import annotations

import math
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from scipy.signal import find_peaks, welch

from . import landmarks as LM

NAN = float("nan")
FS = 30.0  # analysis grid (Hz) all step signals are resampled to


# --------------------------------------------------------------------------- #
# Per-frame features
# --------------------------------------------------------------------------- #
def _d(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.hypot(a[0] - b[0], a[1] - b[1]))


def face_frame(face: np.ndarray) -> Dict[str, float]:
    """Geometry of one face in a face-aligned frame (origin between the eyes)."""
    p = face[:, :2].astype(np.float64)
    eye_r = 0.5 * (p[LM.R_EYE_OUTER] + p[LM.R_EYE_INNER])
    eye_l = 0.5 * (p[LM.L_EYE_OUTER] + p[LM.L_EYE_INNER])
    iod = _d(eye_r, eye_l)
    if iod < 1e-3:
        return {}
    origin = 0.5 * (eye_r + eye_l)
    ex = (eye_l - eye_r) / iod                  # toward the subject's left
    ey = np.array([-ex[1], ex[0]])              # downward

    def al(i):
        v = p[i] - origin
        return float(v @ ex) / iod, float(v @ ey) / iod

    def ear(outer, inner, ups, los):
        w = _d(p[outer], p[inner])
        if w < 1e-6:
            return NAN
        return (_d(p[ups[0]], p[los[0]]) + _d(p[ups[1]], p[los[1]])) / (2.0 * w)

    def gaze(c1, c2, iris):
        v = p[c2] - p[c1]
        n2 = float(v @ v)
        if n2 < 1e-6:
            return NAN
        return float((p[iris] - p[c1]) @ v) / n2

    cr = al(LM.MOUTH_R)
    cl = al(LM.MOUTH_L)
    brow_r = float(np.mean([al(i)[1] for i in LM.R_BROW]))
    brow_l = float(np.mean([al(i)[1] for i in LM.L_BROW]))
    nose = al(LM.NOSE_TIP)
    return {
        "iod_px": iod,
        "ear_r": ear(LM.R_EYE_OUTER, LM.R_EYE_INNER, LM.R_EYE_UP, LM.R_EYE_LO),
        "ear_l": ear(LM.L_EYE_OUTER, LM.L_EYE_INNER, LM.L_EYE_UP, LM.L_EYE_LO),
        # both oriented from the subject's right to left: larger = looking to the left
        "gaze_r": gaze(LM.R_EYE_OUTER, LM.R_EYE_INNER, LM.R_IRIS_CENTER),
        "gaze_l": gaze(LM.L_EYE_INNER, LM.L_EYE_OUTER, LM.L_IRIS_CENTER),
        "mouth_ap": _d(p[LM.LIP_INNER_UP], p[LM.LIP_INNER_LO]) / iod,
        "cr_x": cr[0], "cr_y": cr[1], "cl_x": cl[0], "cl_y": cl[1],
        "brow_r": brow_r, "brow_l": brow_l,
        # head position in IOD units of the image frame (for postural stability)
        "head_x": float(p[LM.NOSE_TIP][0]) / iod, "head_y": float(p[LM.NOSE_TIP][1]) / iod,
        "nose_ax": nose[0], "nose_ay": nose[1],
    }


def hand_frame(hand: np.ndarray) -> Dict[str, float]:
    p = hand[:, :2].astype(np.float64)
    size = _d(p[LM.WRIST], p[LM.MIDDLE_MCP])
    if size < 1e-3:
        return {}
    return {
        "pinch": _d(p[LM.THUMB_TIP], p[LM.INDEX_TIP]) / size,
        "roll": float(p[LM.INDEX_MCP][0] - p[LM.PINKY_MCP][0]) / size,
        "size_px": size,
    }


FACE_KEYS = ("ear_r", "ear_l", "gaze_r", "gaze_l", "mouth_ap", "cr_x", "cr_y", "cl_x", "cl_y",
             "brow_r", "brow_l", "head_x", "head_y", "iod_px")
HAND_KEYS = ("pinch", "roll")


def frame_features(face: Optional[np.ndarray], hands: Dict[str, np.ndarray]) -> Dict[str, float]:
    out = {k: NAN for k in FACE_KEYS}
    for side in ("R", "L"):
        for k in HAND_KEYS:
            out["%s_%s" % (k, side)] = NAN
    if face is not None:
        out.update({k: v for k, v in face_frame(face).items() if k in FACE_KEYS})
    for side, arr in hands.items():
        for k, v in hand_frame(arr).items():
            if k in HAND_KEYS:
                out["%s_%s" % (k, side)] = v
    return out


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
class Trace:
    """Time series for one step: t (s from step start) and named feature arrays."""

    def __init__(self, t: Sequence[float], feats: Dict[str, Sequence[float]]):
        self.t = np.asarray(t, dtype=np.float64)
        self.f = {k: np.asarray(v, dtype=np.float64) for k, v in feats.items()}

    def __len__(self) -> int:
        return int(self.t.size)

    def get(self, key: str) -> np.ndarray:
        return self.f.get(key, np.full(self.t.shape, np.nan))

    def coverage(self, key: str) -> float:
        x = self.get(key)
        return float(np.mean(np.isfinite(x))) if x.size else 0.0

    def window(self, t0: float, t1: float) -> "Trace":
        m = (self.t >= t0) & (self.t < t1)
        return Trace(self.t[m], {k: v[m] for k, v in self.f.items()})


def resample(t: np.ndarray, x: np.ndarray, fs: float = FS) -> Tuple[np.ndarray, np.ndarray]:
    ok = np.isfinite(x)
    if ok.sum() < 4:
        return np.array([]), np.array([])
    tt, xx = t[ok], x[ok]
    grid = np.arange(tt[0], tt[-1], 1.0 / fs)
    return grid, np.interp(grid, tt, xx)


def _smooth(x: np.ndarray, n: int = 3) -> np.ndarray:
    if x.size < n:
        return x
    k = np.ones(n) / n
    return np.convolve(np.pad(x, (n // 2, n - 1 - n // 2), mode="edge"), k, mode="valid")


def _robust_amp(x: np.ndarray) -> float:
    if x.size == 0:
        return NAN
    return float(np.percentile(x, 95) - np.percentile(x, 5))


def _nanmedian(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    return float(np.median(x)) if x.size else NAN


def _ratio(a: float, b: float) -> float:
    if not (np.isfinite(a) and np.isfinite(b)):
        return NAN
    hi = max(abs(a), abs(b))
    if hi < 1e-9:
        return 1.0
    return float(min(abs(a), abs(b)) / hi)


def dominant_freq(x: np.ndarray, fs: float, lo: float, hi: float) -> float:
    if x.size < int(fs):
        return NAN
    f, p = welch(x - np.mean(x), fs=fs, nperseg=min(len(x), int(fs * 4)))
    m = (f >= lo) & (f <= hi)
    if not np.any(m) or np.max(p[m]) <= 0:
        return NAN
    return float(f[m][np.argmax(p[m])])


def oscillation(t: np.ndarray, x: np.ndarray, fmin: float, fmax: float,
                min_prom_frac: float = 0.25) -> Dict[str, float]:
    """Cycle rate, amplitude, decrement and rhythm variability of a repetitive movement."""
    grid, y = resample(t, x)
    if y.size < FS * 2:
        return {}
    y = _smooth(y, 3)
    amp_total = _robust_amp(y)
    if not np.isfinite(amp_total) or amp_total < 1e-6:
        return {"rate": 0.0, "amp": 0.0, "decrement": NAN, "cv": NAN, "n": 0}
    peaks, props = find_peaks(y, distance=max(1, int(FS / fmax * 0.8)),
                              prominence=min_prom_frac * amp_total)
    dur = grid[-1] - grid[0]
    n = len(peaks)
    rate = n / dur if dur > 0 else NAN
    f_dom = dominant_freq(y, FS, fmin, fmax)
    # Use the spectral estimate when the peak count is implausible (missed peaks).
    if np.isfinite(f_dom) and (n < 3 or abs(rate - f_dom) / max(f_dom, 1e-6) > 0.35):
        rate = f_dom
    proms = props.get("prominences", np.array([]))
    amp = float(np.median(proms)) if proms.size else 0.0
    decrement = NAN
    if proms.size >= 6:
        k = max(2, proms.size // 3)
        first, last = np.mean(proms[:k]), np.mean(proms[-k:])
        decrement = float((first - last) / first) if first > 1e-9 else NAN
    cv = NAN
    if n >= 4:
        iv = np.diff(grid[peaks])
        cv = float(np.std(iv) / np.mean(iv)) if np.mean(iv) > 0 else NAN
    return {"rate": float(rate), "amp": amp, "decrement": decrement, "cv": cv, "n": n}


# --------------------------------------------------------------------------- #
# Step metrics
# --------------------------------------------------------------------------- #
def eye_openness(tr: Trace) -> Tuple[np.ndarray, Dict[str, float]]:
    er, el = tr.get("ear_r"), tr.get("ear_l")
    ref_r = np.nanpercentile(er, 90) if np.isfinite(er).any() else NAN
    ref_l = np.nanpercentile(el, 90) if np.isfinite(el).any() else NAN
    op = np.nanmean(np.vstack([er / ref_r, el / ref_l]), axis=0) if np.isfinite(ref_r) else er * NAN
    return op, {"ear_open_r": float(ref_r), "ear_open_l": float(ref_l)}


def alertness_metrics(tr: Trace) -> Dict[str, float]:
    """PERCLOS, blinks, micro-sleeps, fixation stability and head motion."""
    out: Dict[str, float] = {}
    if len(tr) < FS * 5 or tr.coverage("ear_r") < 0.6:
        return out
    op, _ = eye_openness(tr)
    grid, y = resample(tr.t, op)
    if y.size == 0:
        return out
    dur = grid[-1] - grid[0]
    out["alert.perclos"] = float(np.mean(y < 0.2))
    closed = y < 0.5
    edges = np.diff(np.concatenate([[0], closed.astype(int), [0]]))
    starts, ends = np.where(edges == 1)[0], np.where(edges == -1)[0]
    lens = (ends - starts) / FS
    blinks = lens[(lens >= 0.05) & (lens <= 0.5)]
    out["alert.blink_rate"] = float(len(blinks) / dur * 60.0) if dur > 0 else NAN
    out["alert.blink_duration_ms"] = float(np.mean(blinks) * 1000.0) if blinks.size else NAN
    out["alert.microsleeps"] = float(np.sum(lens > 0.5))
    g = np.nanmean(np.vstack([tr.get("gaze_r"), tr.get("gaze_l")]), axis=0)
    g = np.where(op > 0.6, g, np.nan)
    out["alert.fixation_instability"] = float(np.nanstd(g)) if np.isfinite(g).sum() > 10 else NAN
    hx, hy = tr.get("head_x"), tr.get("head_y")
    ok = np.isfinite(hx) & np.isfinite(hy)
    if ok.sum() > 10:
        out["alert.head_motion"] = float(np.sqrt(np.var(hx[ok]) + np.var(hy[ok])))
    return out


def saccade_metrics(tr: Trace, trials: List[Tuple[float, int]]) -> Tuple[Dict[str, float], List[Dict]]:
    """Reaction latency of visually guided saccades.

    trials: list of (onset time in step seconds, expected direction +1 left / -1 right).
    """
    g = np.nanmean(np.vstack([tr.get("gaze_r"), tr.get("gaze_l")]), axis=0)
    op, _ = eye_openness(tr)
    g = np.where(op > 0.5, g, np.nan)
    rows: List[Dict] = []
    for onset, direction in trials:
        pre = (tr.t >= onset - 0.35) & (tr.t < onset)
        post = (tr.t >= onset) & (tr.t < onset + 0.9)
        tail = (tr.t >= onset + 0.55) & (tr.t < onset + 0.9)
        base = _nanmedian(g[pre])
        final = _nanmedian(g[tail])
        row = {"onset": onset, "dir": direction, "latency_ms": NAN, "valid": False, "error": False}
        if not (np.isfinite(base) and np.isfinite(final)):
            rows.append(row)
            continue
        disp = (final - base) * direction
        tt, gg = tr.t[post], g[post]
        ok = np.isfinite(gg)
        tt, gg = tt[ok], gg[ok]
        if disp < 0.02 or tt.size < 4:
            row["error"] = True        # no movement toward the target
            row["valid"] = True
            rows.append(row)
            continue
        rel = (gg - base) * direction
        wrong = np.where(rel < -0.5 * disp)[0]
        hit = np.where(rel >= 0.5 * disp)[0]
        if hit.size == 0:
            row["error"] = True
        else:
            if wrong.size and wrong[0] < hit[0]:
                row["error"] = True
            # interpolate the 50 % crossing between frames for sub-frame resolution
            i = hit[0]
            if i > 0 and rel[i] != rel[i - 1]:
                frac = (0.5 * disp - rel[i - 1]) / (rel[i] - rel[i - 1])
                tc = tt[i - 1] + frac * (tt[i] - tt[i - 1])
            else:
                tc = tt[i]
            row["latency_ms"] = float((tc - onset) * 1000.0)
        row["valid"] = True
        rows.append(row)
    valid = [r for r in rows if r["valid"]]
    out: Dict[str, float] = {}
    if len(valid) >= 4:
        lat = [r["latency_ms"] for r in valid if np.isfinite(r["latency_ms"]) and not r["error"]]
        out["alert.saccade_latency_ms"] = float(np.median(lat)) if lat else NAN
        out["alert.saccade_errors"] = float(np.mean([r["error"] for r in valid]))
    return out, rows


def pursuit_metrics(tr: Trace, target: np.ndarray) -> Dict[str, float]:
    """Smooth-pursuit coherence and binocular conjugacy.

    target: expected gaze direction for every sample of tr (+1 = subject's left).
    """
    out: Dict[str, float] = {}
    gr, gl = tr.get("gaze_r"), tr.get("gaze_l")
    op, _ = eye_openness(tr)
    ok = np.isfinite(gr) & np.isfinite(gl) & np.isfinite(target) & (op > 0.5)
    if ok.sum() < FS * 3:
        return out
    t = tr.t[ok]
    g = 0.5 * (gr[ok] + gl[ok])
    tg = target[ok]
    _, gu = resample(t, g)
    _, tu = resample(t, tg)
    n = min(gu.size, tu.size)
    gu, tu = gu[:n] - np.mean(gu[:n]), tu[:n] - np.mean(tu[:n])
    best_r, best_lag = -1.0, 0
    for lag in range(0, int(0.4 * FS) + 1):           # eyes lag the target
        a, b = gu[lag:], tu[:n - lag]
        if a.size < FS * 2 or np.std(a) < 1e-9 or np.std(b) < 1e-9:
            continue
        r = float(np.corrcoef(a, b)[0, 1])
        if r > best_r:
            best_r, best_lag = r, lag
    out["eyes.pursuit_coherence"] = max(0.0, best_r)
    out["eyes.pursuit_lag_ms"] = best_lag / FS * 1000.0
    a, b = gr[ok] - np.mean(gr[ok]), gl[ok] - np.mean(gl[ok])
    if np.std(a) > 1e-9 and np.std(b) > 1e-9:
        out["eyes.conjugacy"] = max(0.0, float(np.corrcoef(a, b)[0, 1]))
    return out


def face_metrics(neutral: Trace, smile: Trace, brows: Trace, eyes: Trace) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if neutral.coverage("cr_y") < 0.5:
        return out
    med = {k: _nanmedian(neutral.get(k)) for k in ("cr_x", "cr_y", "cl_x", "cl_y",
                                                   "brow_r", "brow_l", "ear_r", "ear_l")}
    out["face.rest_mouth_tilt"] = abs(med["cr_y"] - med["cl_y"])
    out["face.droop_side"] = 1.0 if med["cl_y"] > med["cr_y"] else -1.0   # +1: left lower

    def late(tr: Trace, frac: float = 0.45) -> Trace:
        if len(tr) == 0:
            return tr
        return tr.window(tr.t[0] + (tr.t[-1] - tr.t[0]) * frac, tr.t[-1] + 1)

    s = late(smile)
    if s.coverage("cr_y") > 0.5:
        exc_r = np.hypot(s.get("cr_x") - med["cr_x"], s.get("cr_y") - med["cr_y"])
        exc_l = np.hypot(s.get("cl_x") - med["cl_x"], s.get("cl_y") - med["cl_y"])
        er, el = _nanmedian(exc_r), _nanmedian(exc_l)
        out["face.smile_exc_r"], out["face.smile_exc_l"] = er, el
        out["face.smile_symmetry"] = _ratio(er, el)
    b = late(brows)
    if b.coverage("brow_r") > 0.5:
        rr = med["brow_r"] - _nanmedian(b.get("brow_r"))
        rl = med["brow_l"] - _nanmedian(b.get("brow_l"))
        out["face.brow_raise_r"], out["face.brow_raise_l"] = rr, rl
        out["face.brow_symmetry"] = _ratio(max(rr, 0.0), max(rl, 0.0))
    e = late(eyes, 0.35)
    if e.coverage("ear_r") > 0.5 and med["ear_r"] > 0 and med["ear_l"] > 0:
        res_r = _nanmedian(e.get("ear_r")) / med["ear_r"]
        res_l = _nanmedian(e.get("ear_l")) / med["ear_l"]
        out["face.eye_closure_res_r"], out["face.eye_closure_res_l"] = res_r, res_l
        out["face.eye_closure_asym"] = abs(res_r - res_l)
    return out


def speech_metrics(ddk: Trace, reading: Trace) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if ddk.coverage("mouth_ap") > 0.6:
        osc = oscillation(ddk.t, ddk.get("mouth_ap"), 1.5, 9.0)
        if osc:
            out["speech.ddk_rate"] = osc["rate"]
            out["speech.ddk_regularity_cv"] = osc["cv"]
            out["speech.articulation_amp"] = osc["amp"]
    corner_r, corner_l = [], []
    for tr in (ddk, reading):
        if len(tr) and tr.coverage("cr_y") > 0.5:
            corner_r.append(np.hypot(tr.get("cr_x") - _nanmedian(tr.get("cr_x")),
                                     tr.get("cr_y") - _nanmedian(tr.get("cr_y"))))
            corner_l.append(np.hypot(tr.get("cl_x") - _nanmedian(tr.get("cl_x")),
                                     tr.get("cl_y") - _nanmedian(tr.get("cl_y"))))
    if corner_r:
        mr = float(np.nanmean(np.concatenate(corner_r)))
        ml = float(np.nanmean(np.concatenate(corner_l)))
        out["speech.corner_motion_r"], out["speech.corner_motion_l"] = mr, ml
        out["speech.lip_symmetry"] = _ratio(mr, ml)
    if reading.coverage("mouth_ap") > 0.6:
        grid, ap = resample(reading.t, reading.get("mouth_ap"))
        if ap.size > FS:
            vel = np.abs(np.gradient(_smooth(ap, 3), 1.0 / FS))
            out["speech.reading_activity"] = float(np.mean(vel > 0.25))
    return out


def tapping_metrics(tr: Trace, side: str) -> Dict[str, float]:
    key = "pinch_" + side
    out: Dict[str, float] = {}
    if tr.coverage(key) < 0.5:
        return out
    osc = oscillation(tr.t, tr.get(key), 1.0, 9.0)
    if not osc:
        return out
    s = side
    out["arm.tap_rate_" + s] = osc["rate"]
    out["arm.tap_amp_" + s] = osc["amp"]
    out["arm.tap_decrement_" + s] = osc["decrement"]
    out["arm.tap_cv_" + s] = osc["cv"]
    return out


def ram_metrics(tr: Trace) -> Dict[str, float]:
    out: Dict[str, float] = {}
    for side in ("R", "L"):
        key = "roll_" + side
        if tr.coverage(key) < 0.5:
            continue
        grid, y = resample(tr.t, tr.get(key))
        if y.size < FS * 2:
            continue
        f = dominant_freq(y, FS, 0.4, 5.0)
        osc = oscillation(tr.t, tr.get(key), 0.4, 5.0, min_prom_frac=0.3)
        rate = osc.get("rate", NAN) if osc else NAN
        if not np.isfinite(rate) or (np.isfinite(f) and abs(rate - f) / max(f, 1e-6) > 0.35):
            rate = f
        out["arm.ram_rate_" + side] = float(rate)
        out["arm.ram_amp_" + side] = _robust_amp(y) / 2.0
    return out


def symmetry_pairs(m: Dict[str, float]) -> Dict[str, float]:
    out: Dict[str, float] = {}
    if "arm.tap_rate_R" in m and "arm.tap_rate_L" in m:
        out["arm.tap_symmetry"] = _ratio(m["arm.tap_rate_R"], m["arm.tap_rate_L"])
        if "arm.tap_amp_R" in m and "arm.tap_amp_L" in m:
            out["arm.tap_amp_symmetry"] = _ratio(m["arm.tap_amp_R"], m["arm.tap_amp_L"])
    if "arm.ram_rate_R" in m and "arm.ram_rate_L" in m:
        out["arm.ram_symmetry"] = _ratio(m["arm.ram_rate_R"], m["arm.ram_rate_L"])
    return out


def weaker_side(m: Dict[str, float]) -> Optional[str]:
    """Votes across paired measures; returns 'L', 'R' or None when balanced."""
    votes = 0.0
    pairs = (("face.smile_exc_r", "face.smile_exc_l", 1.0),
             ("face.brow_raise_r", "face.brow_raise_l", 0.5),
             ("speech.corner_motion_r", "speech.corner_motion_l", 0.5),
             ("arm.tap_rate_R", "arm.tap_rate_L", 1.0),
             ("arm.tap_amp_R", "arm.tap_amp_L", 0.5),
             ("arm.ram_rate_R", "arm.ram_rate_L", 1.0))
    for kr, kl, w in pairs:
        r, l = m.get(kr, NAN), m.get(kl, NAN)
        if np.isfinite(r) and np.isfinite(l) and max(abs(r), abs(l)) > 1e-9:
            rel = (r - l) / max(abs(r), abs(l))
            if abs(rel) > 0.15:
                votes += w * math.copysign(1.0, rel)   # positive: right stronger
    # eye closure: larger residual opening means weaker
    rr, rl = m.get("face.eye_closure_res_r", NAN), m.get("face.eye_closure_res_l", NAN)
    if np.isfinite(rr) and np.isfinite(rl) and abs(rr - rl) > 0.1:
        votes += 0.5 * (1.0 if rl > rr else -1.0)
    if votes >= 1.5:
        return "L"
    if votes <= -1.5:
        return "R"
    return None
