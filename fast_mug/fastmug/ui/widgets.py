"""Custom-painted widgets shared by the pages."""
from __future__ import annotations

import math
from collections import deque
from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QButtonGroup, QFrame, QHBoxLayout, QLabel,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from . import icons
from . import theme as T


def label(text: str = "", role: str = "", wrap: bool = False) -> QLabel:
    lb = QLabel(text)
    if role:
        lb.setProperty("role", role)
    lb.setWordWrap(wrap)
    return lb


def button(text: str, kind: str = "", size: str = "", icon_name: str = "") -> QPushButton:
    b = QPushButton(("  " + text) if icon_name else text)
    if kind:
        b.setProperty("kind", kind)
    if size:
        b.setProperty("size", size)
    if icon_name:
        col = {"primary": "#1B232D", "danger": T.ALERT}.get(kind, T.TEXT)
        b.setIcon(icons.icon(icon_name, col, col, 18))
        b.setIconSize(QSize(17, 17))
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


def panel(name: str = "Panel") -> Tuple[QFrame, QVBoxLayout]:
    f = QFrame()
    f.setObjectName(name)
    lay = QVBoxLayout(f)
    lay.setContentsMargins(20, 18, 20, 18)
    lay.setSpacing(12)
    return f, lay


def hline() -> QFrame:
    f = QFrame()
    f.setFixedHeight(1)
    f.setStyleSheet("background: %s;" % T.LINE_SOFT)
    return f


# --------------------------------------------------------------------------- #
class StatusPill(QWidget):
    """Coloured dot plus text; the dot is the only colour on the line."""

    def __init__(self, status: str = "na", text: str = "", parent=None):
        super().__init__(parent)
        self.status, self.text = status, text
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)

    def set(self, status: str, text: str = "") -> None:
        self.status = status
        self.text = text or T.STATUS_WORD.get(status, status)
        self.updateGeometry()
        self.update()

    def sizeHint(self) -> QSize:
        fm = QFontMetrics(T.font(10.5, 500))
        return QSize(fm.horizontalAdvance(self.text or "x") + 40, 26)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        col = QColor(T.STATUS.get(self.status, T.NA))
        r = self.rect().adjusted(0, 1, -1, -1)
        bg = QColor(col)
        bg.setAlpha(34)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(bg)
        p.drawRoundedRect(r, r.height() / 2, r.height() / 2)
        p.setBrush(col)
        p.drawEllipse(QPointF(13, r.center().y() + 0.5), 4, 4)
        p.setPen(QColor(T.TEXT))
        p.setFont(T.font(10.5, 500))
        p.drawText(r.adjusted(23, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter, self.text)


# --------------------------------------------------------------------------- #
class NavButton(QAbstractButton):
    def __init__(self, icon_name: str, text: str, parent=None):
        super().__init__(parent)
        self.icon_name, self.text_ = icon_name, text
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(76, 64)
        self._hover = False
        self.setToolTip(text)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        on = self.isChecked()
        if on or self._hover:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(T.RAISED if on else "#232E3A"))
            p.drawRoundedRect(QRectF(8, 4, 60, 56), 9, 9)
        if on:
            p.setBrush(QColor(T.CABIN))
            p.drawRoundedRect(QRectF(0, 18, 3, 28), 1.5, 1.5)
        col = T.TEXT if on else (T.TEXT if self._hover else T.MUTED)
        pm = icons.pixmap(self.icon_name, col, 22)
        p.drawPixmap(QRectF(27, 11, 22, 22), pm, QRectF(pm.rect()))
        p.setPen(QColor(col))
        p.setFont(T.font(8.5, 500))
        p.drawText(QRectF(0, 37, 76, 18), Qt.AlignmentFlag.AlignHCenter, self.text_)


class NavRail(QFrame):
    changed = Signal(int)

    def __init__(self, items: Sequence[Tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setFixedWidth(84)
        self.setStyleSheet("NavRail { background: %s; border-right: 1px solid %s; }" % (T.BG, T.LINE_SOFT))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(4, 14, 4, 14)
        lay.setSpacing(4)
        logo = Logo()
        lay.addWidget(logo, 0, Qt.AlignmentFlag.AlignHCenter)
        lay.addSpacing(16)
        self.group = QButtonGroup(self)
        self.group.setExclusive(True)
        self.buttons: List[NavButton] = []
        for i, (ic, text) in enumerate(items):
            b = NavButton(ic, text)
            self.group.addButton(b, i)
            self.buttons.append(b)
            if ic == "settings":
                lay.addStretch(1)
            lay.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        self.group.idClicked.connect(self.changed.emit)
        self.buttons[0].setChecked(True)

    def select(self, i: int) -> None:
        self.buttons[i].setChecked(True)


class Logo(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 44)
        self.setToolTip("FAST-μg")

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(7, 7, 30, 30)
        p.setPen(T.pen(QColor(T.RIGHT), 2.6, Qt.PenCapStyle.FlatCap))
        p.drawArc(r, 90 * 16, 180 * 16)
        p.setPen(T.pen(QColor(T.LEFT), 2.6, Qt.PenCapStyle.FlatCap))
        p.drawArc(r, -90 * 16, 180 * 16)
        p.setPen(QPen(QColor(T.TEXT), 2.0))
        p.drawLine(QPointF(22, 2), QPointF(22, 42))


# --------------------------------------------------------------------------- #
class MidlineWidget(QWidget):
    """Mirrored bars: right side to the left of the midline, left side to the right.

    Rows: (label, right %, left %) relative to the personal baseline (100 %).
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows: List[Tuple[str, Optional[float], Optional[float]]] = []
        self.weaker: Optional[str] = None
        self.setMinimumHeight(220)

    def set_rows(self, rows, weaker: Optional[str] = None) -> None:
        self.rows = list(rows)
        self.weaker = weaker
        self.setMinimumHeight(70 + 44 * max(1, len(self.rows)))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        label_w = 118
        cx = label_w + (w - label_w) / 2
        half = (w - label_w) / 2 - 46
        top = 36
        p.setFont(T.font(10, 600))
        p.setPen(QColor(T.RIGHT))
        p.drawText(QRectF(label_w, 4, cx - label_w - 10, 20), Qt.AlignmentFlag.AlignRight, "Right side")
        p.setPen(QColor(T.LEFT))
        p.drawText(QRectF(cx + 10, 4, half, 20), Qt.AlignmentFlag.AlignLeft, "Left side")
        if not self.rows:
            p.setPen(QColor(T.FAINT))
            p.setFont(T.font(10.5))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter,
                       "Side-to-side results appear after the first check.")
            return
        scale = half / 130.0
        n = len(self.rows)
        row_h = (h - top - 26) / n
        # 100 % guides
        guide = QPen(QColor(T.LINE), 1, Qt.PenStyle.DashLine)
        guide.setDashPattern([3, 4])
        p.setPen(guide)
        for sgn in (-1, 1):
            x = cx + sgn * 100 * scale
            p.drawLine(QPointF(x, top - 4), QPointF(x, top + n * row_h))
        p.setFont(T.font(8.5))
        p.setPen(QColor(T.FAINT))
        for sgn in (-1, 1):
            x = cx + sgn * 100 * scale
            p.drawText(QRectF(x - 30, top + n * row_h + 4, 60, 16), Qt.AlignmentFlag.AlignHCenter,
                       "baseline")
        for i, (name, r, l) in enumerate(self.rows):
            y = top + i * row_h + row_h / 2
            bh = min(18.0, row_h * 0.46)
            p.setPen(QColor(T.TEXT))
            p.setFont(T.font(10.5, 500))
            p.drawText(QRectF(0, y - 11, label_w - 12, 22),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, name)
            for val, sgn, col in ((r, -1, T.RIGHT), (l, 1, T.LEFT)):
                if val is None:
                    continue
                v = max(0.0, min(130.0, val))
                rect = QRectF(cx, y - bh / 2, sgn * v * scale, bh).normalized()
                p.setPen(Qt.PenStyle.NoPen)
                c = QColor(col)
                if v < 75:
                    c.setAlpha(255)
                else:
                    c.setAlpha(210)
                p.setBrush(c)
                path = QPainterPath()
                path.addRoundedRect(rect, 3, 3)
                p.drawPath(path)
                p.setPen(QColor(T.TEXT if v >= 75 else col))
                p.setFont(T.font(10, 600, numeric=True))
                txt = "%.0f%%" % val
                if sgn < 0:
                    p.drawText(QRectF(rect.left() - 52, y - 10, 48, 20),
                               Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, txt)
                else:
                    p.drawText(QRectF(rect.right() + 5, y - 10, 48, 20),
                               Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, txt)
        p.setPen(QPen(QColor(T.MIDLINE), 2))
        p.drawLine(QPointF(cx, top - 10), QPointF(cx, top + n * row_h + 2))


# --------------------------------------------------------------------------- #
class Sparkline(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.values: List[float] = []
        self.band: Optional[Tuple[float, float]] = None
        self.color = T.MUTED
        self.setFixedSize(120, 30)

    def set_values(self, values: List[float], band=None, color: str = T.MUTED) -> None:
        self.values = [v for v in values if v is not None and math.isfinite(v)]
        self.band, self.color = band, color
        self.update()

    def paintEvent(self, _):
        if len(self.values) < 2:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        lo, hi = min(self.values), max(self.values)
        if self.band:
            lo, hi = min(lo, self.band[0]), max(hi, self.band[1])
        span = (hi - lo) or 1.0
        w, h = self.width() - 6, self.height() - 6

        def pt(i, v):
            return QPointF(3 + w * i / (len(self.values) - 1), 3 + h * (1 - (v - lo) / span))
        if self.band:
            y0 = 3 + h * (1 - (self.band[1] - lo) / span)
            y1 = 3 + h * (1 - (self.band[0] - lo) / span)
            p.fillRect(QRectF(3, y0, w, y1 - y0), QColor(T.RAISED))
        path = QPainterPath(pt(0, self.values[0]))
        for i, v in enumerate(self.values[1:], 1):
            path.lineTo(pt(i, v))
        p.setPen(QPen(QColor(T.FAINT), 1.3))
        p.drawPath(path)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(pt(len(self.values) - 1, self.values[-1]), 3, 3)


# --------------------------------------------------------------------------- #
class Ring(QWidget):
    """Countdown ring: arc shows step progress, centre shows seconds left."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.frac = 0.0
        self.seconds = 0.0
        self.recording = False
        self.setFixedSize(132, 132)

    def set(self, frac: float, seconds: float, recording: bool) -> None:
        self.frac, self.seconds, self.recording = frac, seconds, recording
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(8, 8, self.width() - 16, self.height() - 16)
        p.setPen(QPen(QColor(T.RAISED), 7))
        p.drawEllipse(r)
        col = QColor(T.CABIN if self.recording else T.FAINT)
        pen = QPen(col, 7)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(r, 90 * 16, int(-360 * 16 * max(0.0, min(1.0, self.frac))))
        p.setPen(QColor(T.TEXT))
        p.setFont(T.font(30, 600, numeric=True))
        p.drawText(r.adjusted(0, -10, 0, 0), Qt.AlignmentFlag.AlignCenter, "%d" % math.ceil(self.seconds))
        p.setFont(T.font(9.5, 500))
        p.setPen(QColor(T.MUTED if self.recording else T.FAINT))
        p.drawText(r.adjusted(0, 46, 0, 0), Qt.AlignmentFlag.AlignCenter,
                   "recording" if self.recording else "get ready")


# --------------------------------------------------------------------------- #
class LiveTrace(QWidget):
    def __init__(self, seconds: float = 6.0, parent=None):
        super().__init__(parent)
        self.seconds = seconds
        self.buf: deque = deque(maxlen=600)
        self.color = T.TEXT
        self.caption = ""
        self.setMinimumHeight(92)

    def reset(self, color: str = T.TEXT, caption: str = "") -> None:
        self.buf.clear()
        self.color, self.caption = color, caption
        self.update()

    def push(self, t: float, v: float) -> None:
        self.buf.append((t, v))
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(QPen(QColor(T.LINE_SOFT), 1))
        p.setBrush(QColor(T.BG))
        p.drawRoundedRect(r, 8, 8)
        p.setPen(QColor(T.FAINT))
        p.setFont(T.font(9))
        p.drawText(r.adjusted(10, 6, -10, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                   self.caption)
        if len(self.buf) < 2:
            return
        t_end = self.buf[-1][0]
        pts = [(t, v) for t, v in self.buf if t >= t_end - self.seconds]
        if len(pts) < 2:
            return
        vs = [v for _, v in pts]
        lo, hi = min(vs), max(vs)
        span = (hi - lo) or 1e-6
        lo -= 0.15 * span
        hi += 0.15 * span
        span = hi - lo
        inner = r.adjusted(10, 24, -10, -8)
        path = QPainterPath()
        for i, (t, v) in enumerate(pts):
            x = inner.left() + inner.width() * (1 - (t_end - t) / self.seconds)
            y = inner.top() + inner.height() * (1 - (v - lo) / span)
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)
        p.setPen(QPen(QColor(self.color), 1.8))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)


# --------------------------------------------------------------------------- #
class StepList(QWidget):
    """The exam sequence. Numbered because it is a true sequence."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.steps: List[Tuple[str, str]] = []   # (group, title)
        self.current = -1
        self.setMinimumHeight(120)

    def set_steps(self, steps: List[Tuple[str, str]]) -> None:
        self.steps = steps
        self.current = -1
        self.setMinimumHeight(len(steps) * 27 + 6)
        self.update()

    def set_current(self, i: int) -> None:
        self.current = i
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        y = 2
        for i, (group, title) in enumerate(self.steps):
            done = i < self.current
            cur = i == self.current
            cy = y + 12
            if i < len(self.steps) - 1:
                p.setPen(QPen(QColor(T.CABIN if done else T.LINE), 1.4))
                p.drawLine(QPointF(11, cy + 8), QPointF(11, cy + 19))
            if done:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(T.CABIN))
                p.drawEllipse(QPointF(11, cy), 7.5, 7.5)
                pen = QPen(QColor(T.BG), 1.8)
                pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                p.setPen(pen)
                p.drawPolyline([QPointF(7.6, cy + 0.2), QPointF(10.2, cy + 2.7), QPointF(14.6, cy - 2.4)])
            elif cur:
                p.setPen(QPen(QColor(T.CABIN), 2))
                p.setBrush(QColor(T.BG))
                p.drawEllipse(QPointF(11, cy), 7.5, 7.5)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(T.CABIN))
                p.drawEllipse(QPointF(11, cy), 3, 3)
            else:
                p.setPen(QPen(QColor(T.LINE), 1.4))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawEllipse(QPointF(11, cy), 7, 7)
            p.setFont(T.font(10.5, 600 if cur else 400))
            p.setPen(QColor(T.TEXT if (cur or done) else T.FAINT))
            p.drawText(QRectF(28, y, self.width() - 110, 24), Qt.AlignmentFlag.AlignVCenter, title)
            p.setFont(T.font(9))
            p.setPen(QColor(T.FAINT))
            p.drawText(QRectF(self.width() - 100, y, 100, 24),
                       Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, group)
            y += 27


# --------------------------------------------------------------------------- #
class TrendChart(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.points: List[Tuple[str, Optional[float], str]] = []   # (label, value, kind)
        self.band: Optional[Tuple[float, float, float]] = None     # (lo, mean, hi)
        self.title = ""
        self.unit = ""
        self.fmt: Callable[[float], str] = lambda v: "%.2f" % v
        self.setMinimumHeight(240)

    def set_data(self, title: str, unit: str, points, band=None, fmt=None) -> None:
        self.title, self.unit, self.points, self.band = title, unit, list(points), band
        if fmt:
            self.fmt = fmt
        self.update()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect())
        p.setPen(QColor(T.TEXT))
        p.setFont(T.font(12, 600))
        p.drawText(r.adjusted(0, 0, 0, 0), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, self.title)
        vals = [v for _, v, _ in self.points if v is not None and math.isfinite(v)]
        if len(vals) < 1:
            p.setPen(QColor(T.FAINT))
            p.setFont(T.font(10.5))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, "No values recorded for this measure yet.")
            return
        lo, hi = min(vals), max(vals)
        if self.band:
            lo, hi = min(lo, self.band[0]), max(hi, self.band[2])
        span = (hi - lo) or abs(hi) or 1.0
        lo -= 0.12 * span
        hi += 0.12 * span
        span = hi - lo
        plot = r.adjusted(56, 34, -16, -30)
        p.setFont(T.font(9, numeric=True))
        for k in range(5):
            v = lo + span * k / 4
            y = plot.bottom() - plot.height() * k / 4
            p.setPen(QPen(QColor(T.LINE_SOFT), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(T.FAINT))
            p.drawText(QRectF(0, y - 8, 50, 16), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       self.fmt(v))
        n = len(self.points)

        def X(i):
            return plot.left() + (plot.width() * (i / (n - 1)) if n > 1 else plot.width() / 2)

        def Y(v):
            return plot.bottom() - plot.height() * (v - lo) / span
        if self.band:
            b0, bm, b1 = self.band
            p.fillRect(QRectF(plot.left(), Y(b1), plot.width(), Y(b0) - Y(b1)), QColor(T.RAISED))
            p.setPen(QPen(QColor(T.FAINT), 1, Qt.PenStyle.DashLine))
            p.drawLine(QPointF(plot.left(), Y(bm)), QPointF(plot.right(), Y(bm)))
        path = QPainterPath()
        first = True
        for i, (_, v, _) in enumerate(self.points):
            if v is None or not math.isfinite(v):
                continue
            if first:
                path.moveTo(X(i), Y(v))
                first = False
            else:
                path.lineTo(X(i), Y(v))
        p.setPen(QPen(QColor(T.MUTED), 1.6))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)
        for i, (lab, v, kind) in enumerate(self.points):
            if v is None or not math.isfinite(v):
                continue
            col = QColor(T.ALERT if kind == "neuro" else T.TEXT)
            p.setPen(QPen(QColor(T.BG), 2))
            p.setBrush(col)
            p.drawEllipse(QPointF(X(i), Y(v)), 4.5, 4.5)
        p.setPen(QColor(T.FAINT))
        p.setFont(T.font(8.5))
        step = max(1, n // 6)
        for i in range(0, n, step):
            p.drawText(QRectF(X(i) - 40, plot.bottom() + 6, 80, 16), Qt.AlignmentFlag.AlignHCenter,
                       self.points[i][0])


# --------------------------------------------------------------------------- #
class Scale(QWidget):
    """1 to 5 segmented selector with words at both ends."""
    changed = Signal(int)

    def __init__(self, low: str, high: str, value: int = 3, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        lo = label(low, "faint")
        lo.setFixedWidth(64)
        lay.addWidget(lo)
        self.group = QButtonGroup(self)
        for i in range(1, 6):
            b = QPushButton(str(i))
            b.setCheckable(True)
            b.setFixedSize(40, 34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setStyleSheet("QPushButton{padding:0;} QPushButton:checked{background:%s;color:%s;"
                            "border-color:%s;font-weight:600;}" % (T.CABIN, T.BG, T.CABIN))
            self.group.addButton(b, i)
            lay.addWidget(b)
        hi = label(high, "faint")
        lay.addWidget(hi)
        lay.addStretch(1)
        self.group.button(value).setChecked(True)
        self.group.idClicked.connect(self.changed.emit)

    def value(self) -> int:
        return self.group.checkedId()


class Chip(QPushButton):
    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet(
            "QPushButton{border-radius:15px;padding:5px 13px;background:transparent;}"
            "QPushButton:checked{background:rgba(229,84,75,0.16);border-color:%s;color:%s;}"
            % (T.ALERT, T.TEXT))


class FlowRow(QWidget):
    """Wraps chips onto several rows."""

    def __init__(self, widgets: List[QWidget], per_row: int = 4, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        for i in range(0, len(widgets), per_row):
            h = QHBoxLayout()
            h.setSpacing(8)
            for w in widgets[i:i + per_row]:
                h.addWidget(w)
            h.addStretch(1)
            v.addLayout(h)


class Banner(QFrame):
    """Inline message strip. Tone: info | warn | error | ok."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        self.lb = label("", wrap=True)
        lay.addWidget(self.lb, 1)
        self.hide()

    def show_msg(self, text: str, tone: str = "info") -> None:
        col = {"info": T.MIDLINE, "warn": T.WATCH, "error": T.ALERT, "ok": T.OK}[tone]
        self.setStyleSheet("Banner{background:%s;border:1px solid %s;border-left:3px solid %s;"
                           "border-radius:6px;}" % (T.SURFACE, T.LINE, col))
        self.lb.setText(text)
        self.show()


__all__ = ["label", "button", "panel", "hline", "StatusPill", "NavRail", "MidlineWidget",
           "Sparkline", "Ring", "LiveTrace", "StepList", "TrendChart", "Scale", "Chip",
           "FlowRow", "Banner", "QBrush", "QLinearGradient", "QVBoxLayout"]
