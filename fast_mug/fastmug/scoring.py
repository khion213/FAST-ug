"""Metric catalogue, personal baselines, z-scores and the session verdict.

Reference priors below are engineering starting values for healthy adults
filmed with a 30 fps webcam. They only matter until a crew member has a few
daily checks on file; after that the personal baseline takes over. Replace
them with values from your own ground-truth recordings when available.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import numpy as np

OK, WATCH, ALERT, NA = "ok", "watch", "alert", "na"
STATUS_RANK = {NA: -1, OK: 0, WATCH: 1, ALERT: 2}

DOMAINS = {
    "face": "Face",
    "speech": "Speech",
    "arm": "Hands",
    "eyes": "Eye movements",
    "alert": "Alertness",
}
NEURO_DOMAINS = ("face", "speech", "arm", "eyes")


@dataclass(frozen=True)
class MetricDef:
    key: str
    label: str
    unit: str
    direction: str            # "high_bad" | "low_bad" | "info"
    prior_mean: float
    prior_sd: float
    fmt: str = "{:.2f}"
    abs_watch: Optional[float] = None
    abs_alert: Optional[float] = None
    help: str = ""
    scored: bool = True

    @property
    def domain(self) -> str:
        return self.key.split(".", 1)[0]

    def format(self, v: Optional[float]) -> str:
        if v is None or not np.isfinite(v):
            return "—"
        return self.fmt.format(v)


def _m(*args, **kw) -> MetricDef:
    return MetricDef(*args, **kw)


CATALOG: List[MetricDef] = [
    # Face (weightlessness puffs the face, so only change from the in-flight baseline matters)
    _m("face.rest_mouth_tilt", "Mouth corner tilt at rest", "IOD", "high_bad", 0.02, 0.015,
       "{:.3f}", 0.05, 0.08, "Vertical offset between mouth corners with a relaxed face."),
    _m("face.smile_symmetry", "Smile symmetry", "ratio", "low_bad", 0.86, 0.07,
       "{:.2f}", 0.72, 0.6, "Weaker side excursion divided by the stronger side."),
    _m("face.brow_symmetry", "Brow raise symmetry", "ratio", "low_bad", 0.82, 0.09,
       "{:.2f}", 0.6, 0.45, "Forehead movement is often spared in central facial weakness."),
    _m("face.eye_closure_asym", "Eye closure asymmetry", "openness", "high_bad", 0.05, 0.04,
       "{:.2f}", 0.15, 0.25, "Difference in residual eye opening during forced closure."),
    _m("face.smile_exc_r", "Smile excursion, right", "IOD", "info", 0.12, 0.03, "{:.3f}", scored=False),
    _m("face.smile_exc_l", "Smile excursion, left", "IOD", "info", 0.12, 0.03, "{:.3f}", scored=False),
    # Speech (visual articulation)
    _m("speech.ddk_rate", "Pa-ta-ka rate", "syll/s", "low_bad", 5.4, 0.8,
       "{:.1f}", 4.0, 3.0, "Diadochokinetic rate from lip aperture rhythm."),
    _m("speech.ddk_regularity_cv", "Pa-ta-ka irregularity", "CV", "high_bad", 0.14, 0.06,
       "{:.2f}", 0.3, 0.45, "Variation of syllable intervals."),
    _m("speech.articulation_amp", "Articulation amplitude", "IOD", "low_bad", 0.13, 0.05,
       "{:.3f}", None, 0.03, "Median lip opening per syllable."),
    _m("speech.lip_symmetry", "Lip movement symmetry", "ratio", "low_bad", 0.82, 0.09,
       "{:.2f}", 0.6, 0.45, "Mouth-corner motion while speaking, weaker over stronger side."),
    _m("speech.reading_activity", "Reading articulation", "fraction", "low_bad", 0.55, 0.15,
       "{:.2f}", 0.25, 0.12, "Share of reading time with visible articulation."),
    # Hands (gravity-independent replacements for the arm drift test)
    _m("arm.tap_rate_R", "Finger tapping, right", "Hz", "low_bad", 4.0, 0.8, "{:.1f}", 2.5, 1.8),
    _m("arm.tap_rate_L", "Finger tapping, left", "Hz", "low_bad", 4.0, 0.8, "{:.1f}", 2.5, 1.8),
    _m("arm.tap_symmetry", "Tapping rate symmetry", "ratio", "low_bad", 0.88, 0.07,
       "{:.2f}", 0.75, 0.6, "Slower hand divided by faster hand."),
    _m("arm.tap_amp_symmetry", "Tapping amplitude symmetry", "ratio", "low_bad", 0.85, 0.09,
       "{:.2f}", 0.65, 0.5),
    _m("arm.tap_decrement_R", "Tapping fatigue, right", "fraction", "high_bad", 0.1, 0.12, "{:.2f}", 0.4, None),
    _m("arm.tap_decrement_L", "Tapping fatigue, left", "fraction", "high_bad", 0.1, 0.12, "{:.2f}", 0.4, None),
    _m("arm.ram_rate_R", "Hand turning, right", "Hz", "low_bad", 2.0, 0.45, "{:.2f}", 1.2, 0.8),
    _m("arm.ram_rate_L", "Hand turning, left", "Hz", "low_bad", 2.0, 0.45, "{:.2f}", 1.2, 0.8),
    _m("arm.ram_symmetry", "Hand turning symmetry", "ratio", "low_bad", 0.86, 0.08,
       "{:.2f}", 0.72, 0.6, "Rapid alternating movement, slower over faster hand."),
    _m("arm.tap_amp_R", "Tapping amplitude, right", "hand", "info", 0.7, 0.2, "{:.2f}", scored=False),
    _m("arm.tap_amp_L", "Tapping amplitude, left", "hand", "info", 0.7, 0.2, "{:.2f}", scored=False),
    # Eye movements
    _m("eyes.pursuit_coherence", "Smooth pursuit coherence", "r", "low_bad", 0.86, 0.07,
       "{:.2f}", 0.6, 0.4, "Correlation between gaze and the moving target."),
    _m("eyes.conjugacy", "Binocular conjugacy", "r", "low_bad", 0.9, 0.06,
       "{:.2f}", 0.7, 0.5, "Agreement between left and right eye movements."),
    _m("eyes.pursuit_lag_ms", "Pursuit lag", "ms", "info", 120, 60, "{:.0f}", scored=False),
    # Alertness / behavioural health
    _m("alert.perclos", "PERCLOS", "fraction", "high_bad", 0.04, 0.04,
       "{:.2f}", 0.12, 0.2, "Share of time the eyes are at least 80 % closed."),
    _m("alert.blink_rate", "Blink rate", "/min", "high_bad", 17.0, 7.0, "{:.0f}", 32, None),
    _m("alert.blink_duration_ms", "Blink duration", "ms", "high_bad", 160, 50, "{:.0f}", 300, 400),
    _m("alert.microsleeps", "Micro-sleeps", "count", "high_bad", 0.0, 0.5, "{:.0f}", 1, 2,
       "Eye closures longer than half a second."),
    _m("alert.saccade_latency_ms", "Saccade reaction time", "ms", "high_bad", 290, 55,
       "{:.0f}", 420, 520, "Includes camera and display delay; compare against baseline."),
    _m("alert.saccade_errors", "Saccade errors", "fraction", "high_bad", 0.05, 0.08, "{:.2f}", 0.25, 0.4),
    _m("alert.fixation_instability", "Fixation instability", "gaze sd", "high_bad", 0.03, 0.015,
       "{:.3f}", None, None),
    _m("alert.head_motion", "Head sway", "IOD", "high_bad", 0.03, 0.02, "{:.3f}", None, None),
]
BY_KEY: Dict[str, MetricDef] = {m.key: m for m in CATALOG}

# Pairs drawn as mirrored bars around the midline: (right key, left key, label)
LATERAL_PAIRS = (
    ("face.smile_exc_r", "face.smile_exc_l", "Smile"),
    ("face.brow_raise_r", "face.brow_raise_l", "Brow raise"),
    ("speech.corner_motion_r", "speech.corner_motion_l", "Lip corners"),
    ("arm.tap_rate_R", "arm.tap_rate_L", "Finger tapping"),
    ("arm.ram_rate_R", "arm.ram_rate_L", "Hand turning"),
)


# --------------------------------------------------------------------------- #
# Baseline
# --------------------------------------------------------------------------- #
@dataclass
class BaselineStat:
    mean: float
    sd: float
    n: int
    source: str        # personal | blended | reference


def baseline_for(defn: MetricDef, history: Sequence[float], min_personal: int) -> BaselineStat:
    vals = np.array([v for v in history if v is not None and np.isfinite(v)], dtype=float)
    n = int(vals.size)
    floor = defn.prior_sd * 0.35
    if n >= min_personal:
        med = float(np.median(vals))
        mad = float(np.median(np.abs(vals - med))) * 1.4826
        return BaselineStat(med, max(mad, floor), n, "personal")
    if n > 0:
        k = float(min_personal - n)
        med = float(np.median(vals))
        mean = (n * med + k * defn.prior_mean) / (n + k)
        return BaselineStat(mean, defn.prior_sd, n, "blended")
    return BaselineStat(defn.prior_mean, defn.prior_sd, 0, "reference")


def directional_z(defn: MetricDef, value: float, base: BaselineStat) -> float:
    if base.sd <= 0 or not np.isfinite(value):
        return float("nan")
    z = (value - base.mean) / base.sd
    if defn.direction == "low_bad":
        return -z
    return z


def classify(defn: MetricDef, value: Optional[float], z: float, watch_z: float, alert_z: float) -> str:
    if value is None or not np.isfinite(value):
        return NA
    st = OK
    if np.isfinite(z):
        if z >= alert_z:
            st = ALERT
        elif z >= watch_z:
            st = WATCH
    if defn.direction == "low_bad":
        if defn.abs_alert is not None and value <= defn.abs_alert:
            st = ALERT
        elif defn.abs_watch is not None and value <= defn.abs_watch and st == OK:
            st = WATCH
    elif defn.direction == "high_bad":
        if defn.abs_alert is not None and value >= defn.abs_alert:
            st = ALERT
        elif defn.abs_watch is not None and value >= defn.abs_watch and st == OK:
            st = WATCH
    return st


def worst(statuses) -> str:
    out = NA
    for s in statuses:
        if STATUS_RANK[s] > STATUS_RANK[out]:
            out = s
    return out


NEURO_SYMPTOMS = ("speech difficulty", "facial droop", "limb weakness", "numbness",
                  "vision loss", "confusion")
ALL_SYMPTOMS = NEURO_SYMPTOMS + ("headache", "dizziness", "nausea", "blurred vision")


def score_session(metrics: Dict[str, float], history: Dict[str, List[float]],
                  settings: Dict[str, float], self_report: Optional[Dict] = None) -> Dict:
    """Score metrics against baselines and build the verdict."""
    watch_z = float(settings.get("watch_z", 2.0))
    alert_z = float(settings.get("alert_z", 3.0))
    min_personal = int(settings.get("min_personal_sessions", 3))
    scored: Dict[str, Dict] = {}
    for defn in CATALOG:
        if defn.key not in metrics:
            continue
        v = metrics.get(defn.key)
        base = baseline_for(defn, history.get(defn.key, []), min_personal)
        z = directional_z(defn, v, base) if defn.scored else float("nan")
        st = classify(defn, v, z, watch_z, alert_z) if defn.scored else NA
        scored[defn.key] = {"value": _f(v), "mean": base.mean, "sd": base.sd, "n": base.n,
                            "source": base.source, "z": _f(z), "status": st}

    domains: Dict[str, Dict] = {}
    for dk, dname in DOMAINS.items():
        items = [(k, s) for k, s in scored.items() if k.startswith(dk + ".") and BY_KEY[k].scored]
        st = worst([s["status"] for _, s in items])
        zs = [s["z"] for _, s in items if s["z"] is not None and np.isfinite(s["z"])]
        index = float(np.clip(100 - 15 * max(0.0, max(zs)), 0, 100)) if zs else None
        domains[dk] = {"name": dname, "status": st, "index": index,
                       "flags": [k for k, s in items if s["status"] in (WATCH, ALERT)]}

    sr = self_report or {}
    symptoms = [s for s in sr.get("symptoms", [])]
    neuro_sym = [s for s in symptoms if s in NEURO_SYMPTOMS]
    neuro = worst([domains[d]["status"] for d in NEURO_DOMAINS if d in domains])
    alert_dom = domains.get("alert", {}).get("status", NA)

    if neuro == ALERT or neuro_sym:
        level = ALERT
        headline = "Neurological alert"
    elif neuro == WATCH or alert_dom == ALERT:
        level = WATCH
        headline = "Fatigue alert" if (alert_dom == ALERT and neuro != WATCH) else "Watch"
    elif neuro == NA and alert_dom == NA:
        level = NA
        headline = "Incomplete"
    else:
        level = OK
        headline = "Nominal"

    discordant = False
    if sr and alert_dom in (WATCH, ALERT):
        if int(sr.get("mood", 3)) >= 4 and int(sr.get("sleep_quality", 3)) >= 4:
            discordant = True

    recs = recommendations(level, neuro, alert_dom, neuro_sym, discordant, domains)
    return {"metrics": scored, "domains": domains, "level": level, "headline": headline,
            "neuro_status": neuro, "alert_status": alert_dom, "discordant": discordant,
            "recommendations": recs}


def recommendations(level: str, neuro: str, alert_dom: str, neuro_sym: List[str],
                    discordant: bool, domains: Dict[str, Dict]) -> List[str]:
    out: List[str] = []
    if neuro == ALERT or neuro_sym:
        out.append("Notify the flight surgeon now and send this report. Record the time of "
                   "symptom onset; it determines which treatments remain possible.")
        out.append("Repeat the neuro exam in 10 minutes to see whether findings are "
                   "persisting, resolving or progressing.")
        out.append("Use the onboard ultrasound per the flight surgeon's guidance to assess "
                   "carotid and jugular flow.")
    elif neuro == WATCH:
        out.append("Repeat the neuro exam within 30 minutes. If the same measure is flagged "
                   "again, notify the flight surgeon.")
    if alert_dom == ALERT:
        out.append("Alertness is well below this crew member's baseline. Avoid "
                   "safety-critical tasks such as EVA preparation or robotics until rested.")
    elif alert_dom == WATCH:
        out.append("Alertness is below baseline. Consider a rest period and re-check before "
                   "the next critical task.")
    if discordant:
        out.append("Self-report and objective alertness disagree. A private medical "
                   "conference with behavioural health support is suggested.")
    if not out:
        out.append("No action needed. Results were added to the personal baseline.")
    return out


def _f(v) -> Optional[float]:
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None
