"""Design tokens, fonts and the application style sheet.

Palette: a cabin-lit slate console. Colour carries meaning only:
    right side  = cool blue    left side = warm amber (same in GUI, images and report)
    nominal/watch/alert status colours
Everything else stays neutral.
"""
from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

from ..config import FONTS_DIR

BG = "#1B232D"
SURFACE = "#222C38"
RAISED = "#2A3644"
LINE = "#364455"
LINE_SOFT = "#2C3846"
TEXT = "#E8EDF2"
MUTED = "#93A1B1"
FAINT = "#64738A"
CABIN = "#EDE9E1"          # primary action: warm cabin-light white
CABIN_HOVER = "#FFFFFF"

RIGHT = "#7DB7E8"
LEFT = "#E8A87C"
MIDLINE = "#D6E3EE"

OK = "#5CC08F"
WATCH = "#E2B451"
ALERT = "#E5544B"
NA = "#64738A"
STATUS = {"ok": OK, "watch": WATCH, "alert": ALERT, "na": NA}
STATUS_WORD = {"ok": "Within baseline", "watch": "Watch", "alert": "Alert", "na": "Not measured"}

UI_FAMILY = "Barlow"
NUM_FAMILY = "Barlow Semi Condensed"


def qc(hex_color: str, alpha: int = 255) -> QColor:
    c = QColor(hex_color)
    c.setAlpha(alpha)
    return c


def pen(color, width: float = 1.0, cap=None):
    from PySide6.QtGui import QPen
    pn = QPen(color if isinstance(color, QColor) else QColor(color), width)
    if cap is not None:
        pn.setCapStyle(cap)
    return pn


def load_fonts() -> None:
    global UI_FAMILY, NUM_FAMILY
    fams = set()
    for f in sorted(FONTS_DIR.glob("*.ttf")):
        fid = QFontDatabase.addApplicationFont(str(f))
        if fid >= 0:
            fams.update(QFontDatabase.applicationFontFamilies(fid))
    if "Barlow" not in fams:
        UI_FAMILY = "Segoe UI"
    if "Barlow Semi Condensed" not in fams:
        NUM_FAMILY = UI_FAMILY


def font(size: float, weight: int = 400, numeric: bool = False) -> QFont:
    f = QFont(NUM_FAMILY if numeric else UI_FAMILY)
    f.setPointSizeF(size)
    w = {400: QFont.Weight.Normal, 500: QFont.Weight.Medium, 600: QFont.Weight.DemiBold,
         700: QFont.Weight.Bold}.get(weight, QFont.Weight.Normal)
    f.setWeight(w)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


def apply(app: QApplication) -> None:
    load_fonts()
    app.setStyle("Fusion")
    pal = QPalette()
    for role, col in ((QPalette.ColorRole.Window, BG), (QPalette.ColorRole.Base, SURFACE),
                      (QPalette.ColorRole.AlternateBase, RAISED), (QPalette.ColorRole.Text, TEXT),
                      (QPalette.ColorRole.WindowText, TEXT), (QPalette.ColorRole.Button, RAISED),
                      (QPalette.ColorRole.ButtonText, TEXT), (QPalette.ColorRole.Highlight, "#3B5168"),
                      (QPalette.ColorRole.HighlightedText, TEXT),
                      (QPalette.ColorRole.PlaceholderText, FAINT),
                      (QPalette.ColorRole.ToolTipBase, RAISED), (QPalette.ColorRole.ToolTipText, TEXT)):
        pal.setColor(role, QColor(col))
    app.setPalette(pal)
    app.setFont(font(10.5))
    tokens = dict(globals())
    tokens["ARROW"] = _arrow_png()
    app.setStyleSheet(STYLE.format(**tokens))


def _arrow_png() -> str:
    """Style sheets need an image file for the combo-box arrow; draw one once."""
    import tempfile
    from pathlib import Path
    from PySide6.QtCore import QPointF, Qt
    from PySide6.QtGui import QPainter, QPen, QPixmap
    path = Path(tempfile.gettempdir()) / "fastmug_arrow.png"
    pm = QPixmap(30, 18)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pn = QPen(QColor(MUTED), 3.2)
    pn.setCapStyle(Qt.PenCapStyle.RoundCap)
    pn.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    p.setPen(pn)
    p.drawPolyline([QPointF(4, 4), QPointF(15, 14), QPointF(26, 4)])
    p.end()
    pm.save(str(path))
    return path.as_posix()


STYLE = """
QWidget {{ color: {TEXT}; font-family: "{UI_FAMILY}"; }}
QMainWindow, #Root {{ background: {BG}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {LINE}; padding: 6px 8px; }}

QLabel[role="muted"] {{ color: {MUTED}; }}
QLabel[role="faint"] {{ color: {FAINT}; }}
QLabel[role="h1"] {{ font-family: "{NUM_FAMILY}"; font-size: 26pt; font-weight: 600; }}
QLabel[role="h2"] {{ font-family: "{NUM_FAMILY}"; font-size: 17pt; font-weight: 600; }}
QLabel[role="h3"] {{ font-size: 12.5pt; font-weight: 600; }}
QLabel[role="section"] {{ color: {MUTED}; font-size: 10.5pt; font-weight: 500; }}

#Panel {{ background: {SURFACE}; border: 1px solid {LINE_SOFT}; border-radius: 10px; }}
#Inset {{ background: {BG}; border: 1px solid {LINE_SOFT}; border-radius: 8px; }}
#TopBar {{ background: {BG}; border-bottom: 1px solid {LINE_SOFT}; }}

QPushButton {{
    background: {RAISED}; border: 1px solid {LINE}; border-radius: 7px;
    padding: 8px 16px; font-size: 10.5pt; font-weight: 500; color: {TEXT};
}}
QPushButton:hover {{ border-color: {FAINT}; background: #304052; }}
QPushButton:pressed {{ background: {SURFACE}; }}
QPushButton:disabled {{ color: {FAINT}; border-color: {LINE_SOFT}; background: {SURFACE}; }}
QPushButton:focus {{ outline: none; border-color: {MIDLINE}; }}
QPushButton[kind="primary"] {{
    background: {CABIN}; color: #1B232D; border: 1px solid {CABIN}; font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{ background: {CABIN_HOVER}; border-color: {CABIN_HOVER}; }}
QPushButton[kind="primary"]:disabled {{ background: #6E747A; border-color: #6E747A; color: #2A3036; }}
QPushButton[kind="danger"] {{
    background: transparent; color: {ALERT}; border: 1px solid {ALERT}; font-weight: 600;
}}
QPushButton[kind="danger"]:hover {{ background: rgba(229, 84, 75, 0.14); }}
QPushButton[kind="ghost"] {{ background: transparent; border: 1px solid transparent; color: {MUTED}; }}
QPushButton[kind="ghost"]:hover {{ color: {TEXT}; background: {RAISED}; }}
QPushButton[size="large"] {{ padding: 13px 22px; font-size: 12pt; border-radius: 9px; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateTimeEdit, QPlainTextEdit {{
    background: {BG}; border: 1px solid {LINE}; border-radius: 6px; padding: 6px 9px;
    selection-background-color: #3B5168; font-size: 10.5pt;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QDateTimeEdit:focus,
QPlainTextEdit:focus {{ border-color: {MIDLINE}; }}
QLineEdit:disabled {{ color: {FAINT}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url("{ARROW}"); width: 10px; height: 6px; margin-right: 10px; }}
QComboBox QAbstractItemView {{ background: {RAISED}; border: 1px solid {LINE}; padding: 4px;
    selection-background-color: #3B5168; outline: none; }}
QSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::up-button, QDoubleSpinBox::down-button,
QDateTimeEdit::up-button, QDateTimeEdit::down-button {{ width: 0; border: none; }}

QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid {LINE};
    background: {BG}; }}
QCheckBox::indicator:checked {{ background: {CABIN}; border-color: {CABIN}; }}

QTableWidget, QTableView, QListWidget {{
    background: transparent; border: none; gridline-color: {LINE_SOFT};
    selection-background-color: #2F3D4D; outline: none; font-size: 10.5pt;
}}
QTableWidget::item, QListWidget::item {{ padding: 6px 8px; border-bottom: 1px solid {LINE_SOFT}; }}
QTableWidget::item:selected, QListWidget::item:selected {{ background: #2F3D4D; color: {TEXT}; }}
QHeaderView {{ background: transparent; }}
QTableCornerButton::section {{ background: transparent; border: none; }}
QHeaderView::section {{ background: transparent; color: {MUTED}; border: none;
    border-bottom: 1px solid {LINE}; padding: 6px 8px; font-weight: 500; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {LINE}; border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {FAINT}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {LINE}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

QProgressBar {{ background: {RAISED}; border: none; border-radius: 2px; height: 4px; }}
QProgressBar::chunk {{ background: {CABIN}; border-radius: 2px; }}

QDialog {{ background: {SURFACE}; }}
QMessageBox {{ background: {SURFACE}; }}
QMessageBox QLabel {{ font-size: 10.5pt; }}
"""
