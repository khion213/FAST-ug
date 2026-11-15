"""Hand-drawn vector icons (QPainterPath) so the app ships no icon font."""
from __future__ import annotations

import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from . import theme as T


def _pix(draw, color: str, size: int = 24) -> QPixmap:
    scale = 3
    pm = QPixmap(size * scale, size * scale)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(scale, scale)
    pen = QPen(QColor(color), 1.6)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    draw(p)
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def _overview(p: QPainter) -> None:
    # crew status: a pulse trace over a horizon line
    path = QPainterPath(QPointF(3, 13))
    for x, y in ((7, 13), (9, 8), (12, 18), (15, 6), (17, 13), (21, 13)):
        path.lineTo(x, y)
    p.drawPath(path)


def _exam(p: QPainter) -> None:
    # face with a midline
    p.drawEllipse(QRectF(5, 3, 14, 18))
    pen = p.pen()
    pen.setStyle(Qt.PenStyle.DashLine)
    pen.setDashPattern([1.5, 1.8])
    p.setPen(pen)
    p.drawLine(QPointF(12, 1.5), QPointF(12, 22.5))
    pen.setStyle(Qt.PenStyle.SolidLine)
    p.setPen(pen)
    p.drawLine(QPointF(8.5, 10), QPointF(10, 10))
    p.drawLine(QPointF(14, 10), QPointF(15.5, 10))
    p.drawLine(QPointF(9, 15.5), QPointF(15, 15.5))


def _results(p: QPainter) -> None:
    # mirrored bars around the midline
    p.drawLine(QPointF(12, 3), QPointF(12, 21))
    for y, l, r in ((7, 6, 7), (12, 7, 4), (17, 5, 6)):
        p.drawLine(QPointF(12 - l, y), QPointF(12, y))
        p.drawLine(QPointF(12, y), QPointF(12 + r, y))


def _history(p: QPainter) -> None:
    p.drawArc(QRectF(4, 4, 16, 16), 100 * 16, 300 * 16)
    p.drawLine(QPointF(12, 8), QPointF(12, 12))
    p.drawLine(QPointF(12, 12), QPointF(15, 14))
    p.drawLine(QPointF(4.5, 6), QPointF(5.2, 9.5))
    p.drawLine(QPointF(5.2, 9.5), QPointF(8.6, 8.7))


def _crew(p: QPainter) -> None:
    p.drawEllipse(QRectF(8.5, 3.5, 7, 7))
    path = QPainterPath(QPointF(4.5, 20.5))
    path.cubicTo(QPointF(5, 14), QPointF(19, 14), QPointF(19.5, 20.5))
    p.drawPath(path)


def _settings(p: QPainter) -> None:
    for y, k in ((6, 15), (12, 8), (18, 13)):
        p.drawLine(QPointF(4, y), QPointF(20, y))
        p.save()
        p.setBrush(QColor(T.BG))
        p.drawEllipse(QPointF(k, y), 2.2, 2.2)
        p.restore()


def _send(p: QPainter) -> None:
    path = QPainterPath(QPointF(3.5, 11))
    path.lineTo(20.5, 4)
    path.lineTo(14, 20.5)
    path.lineTo(11, 13)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(11, 13), QPointF(20.5, 4))


def _doc(p: QPainter) -> None:
    path = QPainterPath(QPointF(6, 3))
    path.lineTo(14, 3)
    path.lineTo(18, 7)
    path.lineTo(18, 21)
    path.lineTo(6, 21)
    path.closeSubpath()
    p.drawPath(path)
    p.drawLine(QPointF(14, 3), QPointF(14, 7))
    p.drawLine(QPointF(14, 7), QPointF(18, 7))
    for y in (11, 14, 17):
        p.drawLine(QPointF(9, y), QPointF(15, y))


def _folder(p: QPainter) -> None:
    path = QPainterPath(QPointF(3.5, 7))
    path.lineTo(9, 7)
    path.lineTo(11, 9)
    path.lineTo(20.5, 9)
    path.lineTo(20.5, 19)
    path.lineTo(3.5, 19)
    path.closeSubpath()
    p.drawPath(path)


def _check(p: QPainter) -> None:
    path = QPainterPath(QPointF(5, 12.5))
    path.lineTo(10, 17)
    path.lineTo(19, 7)
    p.drawPath(path)


def _stop(p: QPainter) -> None:
    p.drawRoundedRect(QRectF(6, 6, 12, 12), 2, 2)


_DRAW = {"overview": _overview, "exam": _exam, "results": _results, "history": _history,
         "crew": _crew, "settings": _settings, "send": _send, "doc": _doc, "folder": _folder,
         "check": _check, "stop": _stop}


def icon(name: str, color: str = T.MUTED, active: str = T.TEXT, size: int = 24) -> QIcon:
    ic = QIcon()
    ic.addPixmap(_pix(_DRAW[name], color, size), QIcon.Mode.Normal, QIcon.State.Off)
    ic.addPixmap(_pix(_DRAW[name], active, size), QIcon.Mode.Normal, QIcon.State.On)
    ic.addPixmap(_pix(_DRAW[name], active, size), QIcon.Mode.Active, QIcon.State.Off)
    ic.addPixmap(_pix(_DRAW[name], T.FAINT, size), QIcon.Mode.Disabled, QIcon.State.Off)
    return ic


def pixmap(name: str, color: str, size: int = 24) -> QPixmap:
    return _pix(_DRAW[name], color, size)


def app_icon() -> QIcon:
    """Window icon: a midline crossing a ring, in the two laterality colours."""
    def draw(p: QPainter) -> None:
        p.setPen(QPen(QColor(T.RIGHT), 2.2))
        p.drawArc(QRectF(3, 3, 18, 18), 90 * 16, 180 * 16)
        p.setPen(QPen(QColor(T.LEFT), 2.2))
        p.drawArc(QRectF(3, 3, 18, 18), -90 * 16, 180 * 16)
        p.setPen(QPen(QColor(T.TEXT), 1.8))
        p.drawLine(QPointF(12, 1), QPointF(12, 23))
    ic = QIcon()
    for s in (16, 24, 32, 48, 64):
        ic.addPixmap(_pix(draw, T.TEXT, s if s <= 24 else 24))
    return ic


__all__ = ["icon", "pixmap", "app_icon", "math"]
