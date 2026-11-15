"""OpenCV drawing of landmarks for saved clinical snapshots."""
from __future__ import annotations

from typing import Dict, Optional

import cv2
import numpy as np

from . import landmarks as LM

# BGR. Laterality colours are shared with the GUI and the report:
RIGHT_BGR = (232, 183, 125)   # #7DB7E8  subject's right
LEFT_BGR = (124, 168, 232)    # #E8A87C  subject's left
LINE_BGR = (220, 226, 233)
MID_BGR = (120, 210, 240)


def _poly(img, pts, idx, color, thick=1, closed=False):
    arr = np.array([[pts[i, 0], pts[i, 1]] for i in idx], dtype=np.int32)
    cv2.polylines(img, [arr], closed, color, thick, cv2.LINE_AA)


def midline_points(face: np.ndarray):
    """A straight midline: perpendicular bisector of the two eye centres."""
    p = face[:, :2]
    er = 0.5 * (p[LM.R_EYE_OUTER] + p[LM.R_EYE_INNER])
    el = 0.5 * (p[LM.L_EYE_OUTER] + p[LM.L_EYE_INNER])
    c = 0.5 * (er + el)
    ex = el - er
    iod = float(np.linalg.norm(ex))
    if iod < 1e-6:
        return None
    ex /= iod
    ey = np.array([-ex[1], ex[0]])
    return c - ey * 1.6 * iod, c + ey * 2.4 * iod


def draw_face(img: np.ndarray, face: np.ndarray, thick: int = 1) -> None:
    _poly(img, face, LM.FACE_OVAL, LINE_BGR, thick)
    _poly(img, face, LM.R_EYE_RING, RIGHT_BGR, thick)
    _poly(img, face, LM.L_EYE_RING, LEFT_BGR, thick)
    _poly(img, face, LM.R_BROW_LINE, RIGHT_BGR, thick)
    _poly(img, face, LM.L_BROW_LINE, LEFT_BGR, thick)
    _poly(img, face, LM.LIPS_OUTER, LINE_BGR, thick)
    for i, col in ((LM.MOUTH_R, RIGHT_BGR), (LM.MOUTH_L, LEFT_BGR)):
        cv2.circle(img, (int(face[i, 0]), int(face[i, 1])), 4 + thick, col, -1, cv2.LINE_AA)
    for i, col in ((LM.R_IRIS_CENTER, RIGHT_BGR), (LM.L_IRIS_CENTER, LEFT_BGR)):
        cv2.circle(img, (int(face[i, 0]), int(face[i, 1])), 3, col, -1, cv2.LINE_AA)
    mid = midline_points(face)
    if mid is not None:
        a, b = mid
        cv2.line(img, (int(a[0]), int(a[1])), (int(b[0]), int(b[1])), MID_BGR, 1, cv2.LINE_AA)
        # horizontal tick through the mouth corners shows tilt against the midline normal
        cr, cl = face[LM.MOUTH_R, :2], face[LM.MOUTH_L, :2]
        cv2.line(img, (int(cr[0]), int(cr[1])), (int(cl[0]), int(cl[1])), MID_BGR, 1, cv2.LINE_AA)


def draw_hand(img: np.ndarray, hand: np.ndarray, side: str, thick: int = 2) -> None:
    col = RIGHT_BGR if side == "R" else LEFT_BGR
    for a, b in LM.HAND_EDGES:
        cv2.line(img, (int(hand[a, 0]), int(hand[a, 1])), (int(hand[b, 0]), int(hand[b, 1])),
                 col, thick, cv2.LINE_AA)
    for i in (LM.THUMB_TIP, LM.INDEX_TIP):
        cv2.circle(img, (int(hand[i, 0]), int(hand[i, 1])), 5, (255, 255, 255), -1, cv2.LINE_AA)


def annotate(frame: np.ndarray, face: Optional[np.ndarray], hands: Dict[str, np.ndarray],
             caption: str = "") -> np.ndarray:
    img = frame.copy()
    h, w = img.shape[:2]
    thick = 2 if w >= 1000 else 1
    if face is not None:
        draw_face(img, face, thick)
    for side, arr in hands.items():
        draw_hand(img, arr, side, thick + 1)
    if caption:
        cv2.rectangle(img, (0, h - 34), (w, h), (20, 24, 30), -1)
        cv2.putText(img, caption, (14, h - 11), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (230, 230, 230), 1,
                    cv2.LINE_AA)
    # anatomical side markers (camera view is not mirrored)
    cv2.putText(img, "R", (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, RIGHT_BGR, 2, cv2.LINE_AA)
    cv2.putText(img, "L", (w - 34, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, LEFT_BGR, 2, cv2.LINE_AA)
    return img


def crop_to_content(img: np.ndarray, face: Optional[np.ndarray], hands: Dict[str, np.ndarray],
                    pad: float = 0.35) -> np.ndarray:
    pts = []
    if face is not None:
        pts.append(face[:, :2])
    for arr in hands.values():
        pts.append(arr[:, :2])
    if not pts:
        return img
    allp = np.concatenate(pts)
    x0, y0 = allp.min(axis=0)
    x1, y1 = allp.max(axis=0)
    h, w = img.shape[:2]
    bw, bh = x1 - x0, y1 - y0
    x0 = int(max(0, x0 - pad * bw))
    x1 = int(min(w, x1 + pad * bw))
    y0 = int(max(0, y0 - pad * bh))
    y1 = int(min(h, y1 + pad * bh))
    # keep a pleasant 4:3 aspect
    cw, ch = x1 - x0, y1 - y0
    target = 4 / 3.0
    if cw / max(ch, 1) < target:
        extra = int((ch * target - cw) / 2)
        x0, x1 = max(0, x0 - extra), min(w, x1 + extra)
    else:
        extra = int((cw / target - ch) / 2)
        y0, y1 = max(0, y0 - extra), min(h, y1 + extra)
    return img[y0:y1, x0:x1]
