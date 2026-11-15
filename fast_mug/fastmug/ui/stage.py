"""Exam stage: mirrored camera view with landmark overlay, or a visual stimulus."""
from __future__ import annotations

from typing import Dict, Optional

import cv2
import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from .. import landmarks as LM
from ..vision import FrameResult
from . import theme as T


class CameraStage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(520, 340)
        self._img: Optional[QImage] = None
        self._res: Optional[FrameResult] = None
        self.stim: Dict = {"kind": "camera"}
        self.notice = ""
        self.guide = True
        self.idle_text = "The camera starts when an exam begins."
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    # ------------------------------------------------------------------ data
    def set_frame(self, res: FrameResult) -> None:
        self._res = res
        rgb = cv2.cvtColor(res.frame, cv2.COLOR_BGR2RGB)
        rgb = np.ascontiguousarray(rgb[:, ::-1])          # mirror for a natural selfie view
        h, w = rgb.shape[:2]
        self._img = QImage(rgb.data, w, h, 3 * w, QImage.Format.Format_RGB888).copy()
        self.update()

    def clear(self, text: str = "") -> None:
        self._img, self._res = None, None
        if text:
            self.idle_text = text
        self.stim = {"kind": "camera"}
        self.notice = ""
        self.update()

    def set_stimulus(self, stim: Dict) -> None:
        self.stim = stim
        self.update()

    def set_notice(self, text: str) -> None:
        if text != self.notice:
            self.notice = text
            self.update()

    # ------------------------------------------------------------- geometry
    def _fit(self) -> QRectF:
        if self._img is None:
            return QRectF(self.rect())
        iw, ih = self._img.width(), self._img.height()
        W, H = self.width(), self.height()
        s = min(W / iw, H / ih)
        return QRectF((W - iw * s) / 2, (H - ih * s) / 2, iw * s, ih * s)

    def _map(self, rect: QRectF, x: float, y: float) -> QPointF:
        iw, ih = self._img.width(), self._img.height()
        # landmarks are in raw-frame pixels; the shown image is mirrored
        return QPointF(rect.left() + (iw - x) / iw * rect.width(), rect.top() + y / ih * rect.height())

    # ---------------------------------------------------------------- paint
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        r = QRectF(self.rect())
        clip = QPainterPath()
        clip.addRoundedRect(r, 12, 12)
        p.setClipPath(clip)
        p.fillRect(r, QColor("#141B23"))
        kind = self.stim.get("kind", "camera")
        if kind in ("fixation", "saccade", "pursuit", "reading"):
            self._paint_stimulus(p, r, kind)
        elif self._img is None:
            p.setPen(QColor(T.FAINT))
            p.setFont(T.font(11))
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, self.idle_text)
        else:
            fit = self._fit()
            p.drawImage(fit, self._img)
            self._paint_overlay(p, fit)
        if self.notice:
            self._paint_notice(p, r)

    def _paint_overlay(self, p: QPainter, fit: QRectF) -> None:
        res = self._res
        if res is None:
            return
        face = res.face
        if self.guide:
            ok = face is not None
            ow, oh = fit.height() * 0.42, fit.height() * 0.6
            oval = QRectF(fit.center().x() - ow / 2, fit.center().y() - oh / 2 - fit.height() * 0.03, ow, oh)
            pen = QPen(QColor(T.OK if ok else T.CABIN), 2, Qt.PenStyle.DashLine)
            pen.setDashPattern([4, 6])
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawEllipse(oval)
        if face is not None:
            self._contour(p, fit, face, LM.FACE_OVAL, T.qc(T.TEXT, 70), 1.2)
            self._contour(p, fit, face, LM.R_EYE_RING, T.qc(T.RIGHT, 230), 1.5)
            self._contour(p, fit, face, LM.L_EYE_RING, T.qc(T.LEFT, 230), 1.5)
            self._contour(p, fit, face, LM.R_BROW_LINE, T.qc(T.RIGHT, 200), 1.5)
            self._contour(p, fit, face, LM.L_BROW_LINE, T.qc(T.LEFT, 200), 1.5)
            self._contour(p, fit, face, LM.LIPS_OUTER, T.qc(T.TEXT, 150), 1.3)
            for idx, col in ((LM.MOUTH_R, T.RIGHT), (LM.MOUTH_L, T.LEFT),
                             (LM.R_IRIS_CENTER, T.RIGHT), (LM.L_IRIS_CENTER, T.LEFT)):
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(col))
                p.drawEllipse(self._map(fit, face[idx, 0], face[idx, 1]), 3.2, 3.2)
            self._midline(p, fit, face)
        for side, hand in res.hands.items():
            col = QColor(T.RIGHT if side == "R" else T.LEFT)
            p.setPen(T.pen(col, 2.2, Qt.PenCapStyle.RoundCap))
            for a, b in LM.HAND_EDGES:
                p.drawLine(self._map(fit, hand[a, 0], hand[a, 1]), self._map(fit, hand[b, 0], hand[b, 1]))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(T.TEXT))
            for i in (LM.THUMB_TIP, LM.INDEX_TIP):
                p.drawEllipse(self._map(fit, hand[i, 0], hand[i, 1]), 4, 4)
        # side markers: the view is mirrored, so the subject's right is on screen right
        p.setFont(T.font(10, 600))
        p.setPen(QColor(T.LEFT))
        p.drawText(QRectF(fit.left() + 14, fit.top() + 10, 120, 20), Qt.AlignmentFlag.AlignLeft, "Left")
        p.setPen(QColor(T.RIGHT))
        p.drawText(QRectF(fit.right() - 134, fit.top() + 10, 120, 20), Qt.AlignmentFlag.AlignRight, "Right")
        if res.fps:
            p.setPen(QColor(T.FAINT))
            p.setFont(T.font(9, numeric=True))
            p.drawText(QRectF(fit.left() + 14, fit.bottom() - 26, 200, 18), Qt.AlignmentFlag.AlignLeft,
                       "%.0f fps%s" % (res.fps, "  simulated" if res.simulated else ""))

    def _contour(self, p, fit, pts, idx, color: QColor, width: float) -> None:
        path = QPainterPath(self._map(fit, pts[idx[0], 0], pts[idx[0], 1]))
        for i in idx[1:]:
            path.lineTo(self._map(fit, pts[i, 0], pts[i, 1]))
        p.setPen(QPen(color, width))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(path)

    def _midline(self, p, fit, face) -> None:
        er = 0.5 * (face[LM.R_EYE_OUTER, :2] + face[LM.R_EYE_INNER, :2])
        el = 0.5 * (face[LM.L_EYE_OUTER, :2] + face[LM.L_EYE_INNER, :2])
        c = 0.5 * (er + el)
        ex = el - er
        iod = float(np.linalg.norm(ex))
        if iod < 1e-3:
            return
        ex = ex / iod
        ey = np.array([-ex[1], ex[0]])
        a, b = c - ey * 1.5 * iod, c + ey * 2.3 * iod
        pen = QPen(T.qc(T.MIDLINE, 160), 1.2, Qt.PenStyle.DashLine)
        pen.setDashPattern([5, 4])
        p.setPen(pen)
        p.drawLine(self._map(fit, a[0], a[1]), self._map(fit, b[0], b[1]))

    def _paint_stimulus(self, p: QPainter, r: QRectF, kind: str) -> None:
        p.fillRect(r, QColor("#10161D"))
        cx, cy = r.center().x(), r.center().y()
        half = r.width() / 2 - 40
        if kind == "fixation" or (kind == "saccade" and not self.stim.get("show")):
            p.setPen(T.pen(QColor(T.TEXT), 2.4, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(cx - 12, cy), QPointF(cx + 12, cy))
            p.drawLine(QPointF(cx, cy - 12), QPointF(cx, cy + 12))
        if kind == "saccade" and self.stim.get("show"):
            x = cx + self.stim.get("x", 0.0) * half
            self._dot(p, QPointF(x, cy))
        elif kind == "pursuit":
            x = cx + self.stim.get("x", 0.0) * half
            pen = QPen(QColor(T.LINE), 1, Qt.PenStyle.DashLine)
            pen.setDashPattern([2, 6])
            p.setPen(pen)
            p.drawLine(QPointF(cx - half * 0.8, cy), QPointF(cx + half * 0.8, cy))
            self._dot(p, QPointF(x, cy))
        elif kind == "reading":
            lines = self.stim.get("lines", ())
            p.setPen(QColor(T.TEXT))
            p.setFont(T.font(22, 500))
            lh = 46
            y0 = cy - lh * len(lines) / 2
            for i, ln in enumerate(lines):
                p.drawText(QRectF(r.left() + 40, y0 + i * lh, r.width() - 80, lh),
                           Qt.AlignmentFlag.AlignCenter, ln)
        # small presence indicator so the subject knows tracking continues
        ok = self._res is not None and self._res.face is not None
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(T.OK if ok else T.ALERT))
        p.drawEllipse(QPointF(r.right() - 22, r.bottom() - 22), 4, 4)

    def _dot(self, p: QPainter, c: QPointF) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.qc(T.CABIN, 50))
        p.drawEllipse(c, 18, 18)
        p.setBrush(QColor(T.CABIN))
        p.drawEllipse(c, 9, 9)
        p.setBrush(QColor("#10161D"))
        p.drawEllipse(c, 2.2, 2.2)

    def _paint_notice(self, p: QPainter, r: QRectF) -> None:
        p.setFont(T.font(11, 500))
        fm = p.fontMetrics()
        w = min(r.width() - 40, fm.horizontalAdvance(self.notice) + 40)
        box = QRectF(r.center().x() - w / 2, r.top() + 18, w, 38)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(T.qc("#141B23", 230))
        p.drawRoundedRect(box, 8, 8)
        p.setBrush(QColor(T.WATCH))
        p.drawRoundedRect(QRectF(box.left(), box.top(), 3, box.height()), 1.5, 1.5)
        p.setPen(QColor(T.TEXT))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, self.notice)
