"""Matplotlib figures for the Word report (rendered off-screen to PNG)."""
from __future__ import annotations

import math
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402
import numpy as np  # noqa: E402

from .config import FONTS_DIR  # noqa: E402
from .scoring import BY_KEY, DOMAINS, LATERAL_PAIRS  # noqa: E402

INK = "#1F2933"
MUTED = "#6B7785"
GRID = "#E3E8EE"
RIGHT = "#3F7FBF"
LEFT = "#D27A43"
STATUS = {"ok": "#2E9E6B", "watch": "#C98F12", "alert": "#C9423B", "na": "#A7B1BC"}

_FONT = "DejaVu Sans"


def _setup_fonts() -> None:
    global _FONT
    try:
        for f in FONTS_DIR.glob("*.ttf"):
            font_manager.fontManager.addfont(str(f))
        names = {f.name for f in font_manager.fontManager.ttflist}
        if "Barlow" in names:
            _FONT = "Barlow"
    except Exception:  # noqa: BLE001
        pass
    plt.rcParams.update({
        "font.family": _FONT,
        "font.size": 9.5,
        "axes.edgecolor": GRID,
        "axes.labelcolor": MUTED,
        "axes.titlesize": 10.5,
        "axes.titleweight": "semibold",
        "axes.titlecolor": INK,
        "axes.titlelocation": "left",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "grid.color": GRID,
        "grid.linewidth": 0.8,
        "legend.frameon": False,
        "figure.dpi": 100,
        "savefig.dpi": 200,
        "savefig.bbox": "tight",
        "savefig.facecolor": "white",
    })


_setup_fonts()


def _save(fig, path: Path) -> Path:
    fig.savefig(path)
    plt.close(fig)
    return path


def midline_chart(raw: Dict[str, float], scored: Dict[str, Dict], history: Dict[str, List[float]],
                  path: Path) -> Optional[Path]:
    """Right and left performance drawn as mirrored bars from the body midline.

    Each side is shown relative to that side's personal baseline mean (100 %).
    """
    rows = []
    for kr, kl, label in LATERAL_PAIRS:
        r, l = raw.get(kr), raw.get(kl)
        if r is None or l is None:
            continue
        ref = _ref(kr, kl, history, r, l)
        rows.append((label, 100.0 * r / ref, 100.0 * l / ref))
    if not rows:
        return None
    fig, ax = plt.subplots(figsize=(6.6, 0.55 * len(rows) + 1.0))
    y = np.arange(len(rows))[::-1]
    lim = max(130.0, max(max(a, b) for _, a, b in rows) * 1.08)
    for yi, (label, r, l) in zip(y, rows):
        ax.barh(yi, -r, height=0.52, color=RIGHT, alpha=0.9)
        ax.barh(yi, l, height=0.52, color=LEFT, alpha=0.9)
        ax.text(-r - 3, yi, "%.0f%%" % r, va="center", ha="right", color=INK, fontsize=8.5)
        ax.text(l + 3, yi, "%.0f%%" % l, va="center", ha="left", color=INK, fontsize=8.5)
        ax.text(-lim * 1.02, yi, label, va="center", ha="right", color=INK, fontsize=9.5)
    for v in (-100, 100):
        ax.axvline(v, color=MUTED, lw=0.8, ls=(0, (3, 3)))
    ax.axvline(0, color=INK, lw=1.4)
    ax.set_xlim(-lim, lim)
    ax.set_yticks([])
    ticks = [-100, -50, 0, 50, 100]
    ax.set_xticks(ticks)
    ax.set_xticklabels([str(abs(t)) for t in ticks])
    ax.set_xlabel("Performance relative to personal baseline (%)")
    ax.spines["left"].set_visible(False)
    ax.text(-lim / 2, len(rows) - 0.35, "Right side", ha="center", color=RIGHT, fontweight="semibold")
    ax.text(lim / 2, len(rows) - 0.35, "Left side", ha="center", color=LEFT, fontweight="semibold")
    ax.set_ylim(-0.7, len(rows) - 0.1)
    ax.set_title("Midline comparison")
    return _save(fig, path)


def _ref(kr: str, kl: str, history: Dict[str, List[float]], r: float, l: float) -> float:
    vals = [v for v in history.get(kr, []) + history.get(kl, []) if v is not None and np.isfinite(v)]
    if len(vals) >= 2:
        return max(float(np.median(vals)), 1e-9)
    for k in (kr, kl):
        if k in BY_KEY:
            return BY_KEY[k].prior_mean
    return max(max(abs(r), abs(l)), 1e-9)


def zprofile_chart(scored: Dict[str, Dict], watch_z: float, alert_z: float, path: Path) -> Optional[Path]:
    items = [(k, v) for k, v in scored.items()
             if BY_KEY.get(k) and BY_KEY[k].scored and v.get("z") is not None]
    if not items:
        return None
    order = list(DOMAINS.keys())
    items.sort(key=lambda kv: (order.index(kv[0].split(".")[0]), kv[0]))
    labels = [BY_KEY[k].label for k, _ in items]
    zs = np.array([max(-3.0, min(8.0, v["z"])) for _, v in items])
    cols = [STATUS[v["status"]] for _, v in items]
    fig, ax = plt.subplots(figsize=(6.6, 0.24 * len(items) + 1.0))
    y = np.arange(len(items))[::-1]
    ax.axvspan(watch_z, alert_z, color=STATUS["watch"], alpha=0.08, lw=0)
    ax.axvspan(alert_z, 8.5, color=STATUS["alert"], alpha=0.08, lw=0)
    ax.barh(y, zs, color=cols, height=0.62)
    ax.axvline(0, color=INK, lw=1)
    ax.set_yticks(y)
    ax.set_yticklabels(labels, fontsize=8.5, color=INK)
    ax.set_xlim(-3, 8.5)
    ax.set_xlabel("Deviation from baseline (z, positive = worse)")
    ax.grid(axis="x")
    prev = None
    for yi, (k, _) in zip(y, items):
        d = k.split(".")[0]
        if prev is not None and d != prev:
            ax.axhline(yi + 0.5, color=GRID, lw=1)
        prev = d
    ax.set_title("Deviation profile")
    return _save(fig, path)


def tapping_chart(tr: Dict[str, np.ndarray], path: Path) -> Optional[Path]:
    series = []
    for side, step, col in (("R", "tap_R", RIGHT), ("L", "tap_L", LEFT)):
        t, x = tr.get(step + "__t"), tr.get("%s__pinch_%s" % (step, side))
        if t is not None and x is not None and np.isfinite(x).sum() > 10:
            series.append((side, t, x, col))
    if not series:
        return None
    fig, axes = plt.subplots(len(series), 1, figsize=(6.6, 1.35 * len(series) + 0.5), sharex=True)
    axes = np.atleast_1d(axes)
    for ax, (side, t, x, col) in zip(axes, series):
        ax.plot(t, x, color=col, lw=1.3)
        ax.set_ylabel("gap (hand)")
        ax.grid(axis="y")
        ax.text(0.995, 0.92, "Right hand" if side == "R" else "Left hand", transform=ax.transAxes,
                ha="right", va="top", color=col, fontweight="semibold")
    axes[-1].set_xlabel("Time (s)")
    axes[0].set_title("Finger tapping: thumb-to-index gap")
    return _save(fig, path)


def ram_chart(tr: Dict[str, np.ndarray], path: Path) -> Optional[Path]:
    t = tr.get("ram__t")
    if t is None:
        return None
    fig, ax = plt.subplots(figsize=(6.6, 1.8))
    drawn = False
    for side, col, sign in (("R", RIGHT, 1), ("L", LEFT, -1)):
        x = tr.get("ram__roll_" + side)
        if x is not None and np.isfinite(x).sum() > 10:
            ax.plot(t, sign * x, color=col, lw=1.3, label="Right" if side == "R" else "Left")
            drawn = True
    if not drawn:
        plt.close(fig)
        return None
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("palm width")
    ax.grid(axis="y")
    ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, borderaxespad=0.2)
    ax.set_title("Hand turning (pronation and supination)")
    return _save(fig, path)


def speech_chart(tr: Dict[str, np.ndarray], path: Path) -> Optional[Path]:
    t, ap = tr.get("ddk__t"), tr.get("ddk__mouth_ap")
    if t is None or ap is None or np.isfinite(ap).sum() < 30:
        return None
    from scipy.signal import welch
    from .signals import resample, FS
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(6.6, 1.9), gridspec_kw={"width_ratios": [2.2, 1]})
    a1.plot(t, ap, color=INK, lw=1.1)
    a1.set_xlabel("Time (s)")
    a1.set_ylabel("lip opening (IOD)")
    a1.grid(axis="y")
    a1.set_title("Pa-ta-ka: lip aperture")
    g, y = resample(t, ap)
    if y.size > FS:
        f, p = welch(y - y.mean(), fs=FS, nperseg=min(len(y), int(FS * 4)))
        m = f <= 10
        a2.fill_between(f[m], p[m] / (p[m].max() or 1), color=INK, alpha=0.18, lw=0)
        a2.plot(f[m], p[m] / (p[m].max() or 1), color=INK, lw=1.1)
        a2.set_xlabel("Hz")
        a2.set_yticks([])
        a2.set_title("Rhythm spectrum")
    return _save(fig, path)


def eyes_chart(tr: Dict[str, np.ndarray], path: Path) -> Optional[Path]:
    t = tr.get("observe__t")
    er, el = tr.get("observe__ear_r"), tr.get("observe__ear_l")
    if t is None or er is None or np.isfinite(er).sum() < 30:
        return None
    op = np.nanmean(np.vstack([er / np.nanpercentile(er, 90), el / np.nanpercentile(el, 90)]), axis=0)
    fig, ax = plt.subplots(figsize=(6.6, 1.7))
    ax.plot(t, op, color=INK, lw=1.0)
    ax.axhline(0.5, color=STATUS["watch"], lw=0.8, ls=(0, (3, 3)))
    ax.axhline(0.2, color=STATUS["alert"], lw=0.8, ls=(0, (3, 3)))
    ax.fill_between(t, 0, 1.2, where=op < 0.5, color=STATUS["watch"], alpha=0.15, lw=0)
    ax.set_ylim(0, 1.25)
    ax.set_xlabel("Time (s)")
    ax.set_ylabel("eye openness")
    ax.set_title("Relaxed fixation: eyelid openness (blinks shaded)")
    return _save(fig, path)


def oculomotor_chart(tr: Dict[str, np.ndarray], trials: List[Dict], pursuit_hz: float,
                     path: Path) -> Optional[Path]:
    has_p = tr.get("pursuit__t") is not None
    lat = [r["latency_ms"] for r in trials if r.get("valid") and not r.get("error")
           and r.get("latency_ms") is not None and np.isfinite(r["latency_ms"])]
    panels = int(has_p) + int(bool(lat))
    if panels == 0:
        return None
    fig, axes = plt.subplots(1, panels, figsize=(6.6, 2.0),
                             gridspec_kw={"width_ratios": ([2.2] if has_p else []) + ([1] if lat else [])})
    axes = np.atleast_1d(axes)
    i = 0
    if has_p:
        ax = axes[i]
        i += 1
        t = tr["pursuit__t"]
        g = np.nanmean(np.vstack([tr.get("pursuit__gaze_r"), tr.get("pursuit__gaze_l")]), axis=0)
        g = g - np.nanmedian(g)
        tgt = -np.sin(2 * math.pi * pursuit_hz * t)
        scale = np.nanpercentile(np.abs(g), 95) or 1.0
        ax.plot(t, tgt, color=MUTED, lw=1.0, ls=(0, (4, 3)), label="Target")
        ax.plot(t, g / scale, color=INK, lw=1.2, label="Gaze")
        ax.set_xlabel("Time (s)")
        ax.set_yticks([])
        ax.legend(loc="lower right", bbox_to_anchor=(1.0, 1.0), ncol=2, borderaxespad=0.2)
        ax.set_title("Smooth pursuit")
    if lat:
        ax = axes[i]
        ax.scatter(np.random.default_rng(0).normal(0, 0.06, len(lat)), lat, color=INK, s=16, alpha=0.8)
        ax.axhline(np.median(lat), color=INK, lw=1.4)
        ax.set_xlim(-0.5, 0.5)
        ax.set_xticks([])
        ax.set_ylabel("ms")
        ax.set_title("Saccade reaction")
    return _save(fig, path)


def trend_chart(sessions: List[Dict], current: Dict, keys: List[str], path: Path) -> Optional[Path]:
    pts = sessions + [current]
    if len(pts) < 2:
        return None
    keys = [k for k in keys if any(k in s.get("raw_metrics", {}) for s in pts)]
    if not keys:
        return None
    n = len(keys)
    cols = 2
    rows = int(math.ceil(n / cols))
    fig, axes = plt.subplots(rows, cols, figsize=(6.6, 1.55 * rows + 0.3))
    axes = np.atleast_1d(axes).ravel()
    for ax, k in zip(axes, keys):
        xs = np.arange(len(pts))
        ys = np.array([s.get("raw_metrics", {}).get(k, np.nan) for s in pts], dtype=float)
        sc = current.get("verdict", {}).get("metrics", {}).get(k)
        if sc:
            ax.axhspan(sc["mean"] - 2 * sc["sd"], sc["mean"] + 2 * sc["sd"], color="#DCE6F0", lw=0)
            ax.axhline(sc["mean"], color="#9FB3C8", lw=1)
        kinds = [s.get("type") for s in pts]
        ax.plot(xs, ys, color=INK, lw=1.0)
        for x, y, kd in zip(xs, ys, kinds):
            ax.plot(x, y, "o", ms=3.5, color=INK if kd == "daily" else STATUS["alert"])
        ax.plot(xs[-1], ys[-1], "o", ms=6, mfc="white", mec=INK, mew=1.4)
        d = BY_KEY.get(k)
        ax.set_title(d.label if d else k, fontsize=9)
        ax.set_xticks([])
    for ax in axes[n:]:
        ax.axis("off")
    fig.tight_layout()
    return _save(fig, path)
