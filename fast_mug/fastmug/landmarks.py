"""MediaPipe landmark indices used by the exam.

Face indices follow the MediaPipe 478-point face mesh (468 mesh + 10 iris points).
"Right"/"left" always mean the SUBJECT's anatomical side. The face model runs on
the raw (non-mirrored) camera frame, where the subject's right side appears on the
image left; index semantics therefore stay anatomical.
"""

# Eyes: outer corner, inner corner, and two upper/lower lid pairs (for EAR)
R_EYE_OUTER, R_EYE_INNER = 33, 133
R_EYE_UP = (160, 158)
R_EYE_LO = (144, 153)
L_EYE_INNER, L_EYE_OUTER = 362, 263
L_EYE_UP = (385, 387)
L_EYE_LO = (380, 373)

R_IRIS_CENTER = 468
L_IRIS_CENTER = 473
R_IRIS_RING = (469, 470, 471, 472)
L_IRIS_RING = (474, 475, 476, 477)

# Mouth
MOUTH_R, MOUTH_L = 61, 291
LIP_INNER_UP, LIP_INNER_LO = 13, 14
LIP_OUTER_UP, LIP_OUTER_LO = 0, 17

# Brows
R_BROW = (70, 63, 105, 66, 107)
L_BROW = (300, 293, 334, 296, 336)

# Midline
FOREHEAD, NASION, NOSE_TIP, CHIN = 10, 168, 1, 152

# Sparse contours for on-screen drawing (kept light on purpose)
FACE_OVAL = (10, 338, 297, 332, 284, 251, 389, 356, 454, 323, 361, 288, 397, 365,
             379, 378, 400, 377, 152, 148, 176, 149, 150, 136, 172, 58, 132, 93,
             234, 127, 162, 21, 54, 103, 67, 109, 10)
R_EYE_RING = (33, 246, 161, 160, 159, 158, 157, 173, 133, 155, 154, 153, 145, 144, 163, 7, 33)
L_EYE_RING = (362, 398, 384, 385, 386, 387, 388, 466, 263, 249, 390, 373, 374, 380, 381, 382, 362)
LIPS_OUTER = (61, 185, 40, 39, 37, 0, 267, 269, 270, 409, 291, 375, 321, 405, 314, 17, 84, 181, 91, 146, 61)
LIPS_INNER = (78, 191, 80, 81, 82, 13, 312, 311, 310, 415, 308, 324, 318, 402, 317, 14, 87, 178, 88, 95, 78)
R_BROW_LINE = (70, 63, 105, 66, 107)
L_BROW_LINE = (300, 293, 334, 296, 336)
MIDLINE = (10, 151, 9, 8, 168, 6, 197, 195, 5, 4, 1, 19, 94, 2, 164, 0, 11, 12, 13, 14, 15, 16, 17, 18, 200, 199, 175, 152)

# Hands (MediaPipe 21-point model)
WRIST = 0
THUMB_TIP = 4
INDEX_MCP, INDEX_TIP = 5, 8
MIDDLE_MCP = 9
PINKY_MCP = 17
HAND_EDGES = (
    (0, 1), (1, 2), (2, 3), (3, 4),
    (0, 5), (5, 6), (6, 7), (7, 8),
    (5, 9), (9, 10), (10, 11), (11, 12),
    (9, 13), (13, 14), (14, 15), (15, 16),
    (13, 17), (17, 18), (18, 19), (19, 20), (0, 17),
)
