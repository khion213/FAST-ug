"""Pre-exam self-report sheet."""
from __future__ import annotations

from typing import Dict, List

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDoubleSpinBox, QHBoxLayout, QLineEdit, QPlainTextEdit,
                               QVBoxLayout, QWidget)

from ..scoring import ALL_SYMPTOMS, NEURO_SYMPTOMS
from . import theme as T
from .widgets import Chip, FlowRow, Scale, button, hline, label


class SelfReportDialog(QDialog):
    def __init__(self, kind: str, crew_name: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setWindowTitle("Before you start")
        self.setModal(True)
        self.setMinimumWidth(620)
        self.setStyleSheet("QDialog{background:%s;}" % T.SURFACE)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 22)
        v.setSpacing(14)
        title = "Daily check" if kind == "daily" else "Neuro exam"
        v.addWidget(label(title, "h2"))
        sub = ("A few questions first, then about two minutes in front of the camera."
               if kind == "daily" else
               "Answer quickly. The exam itself takes about 80 seconds.")
        v.addWidget(label("%s. %s" % (crew_name, sub), "muted", wrap=True))
        v.addWidget(hline())

        self.mood = Scale("Low", "Very good", 4)
        self.sleepq = Scale("Poor", "Very good", 4)
        self.stress = Scale("Calm", "Very high", 2)
        self.hours = QDoubleSpinBox()
        self.hours.setRange(0, 14)
        self.hours.setSingleStep(0.5)
        self.hours.setValue(7.0)
        self.hours.setSuffix(" h")
        self.hours.setFixedWidth(90)
        for text, w in (("Mood", self.mood), ("Sleep quality", self.sleepq), ("Stress", self.stress)):
            v.addWidget(self._row(text, w))
        v.addWidget(self._row("Sleep last night", self.hours))

        v.addWidget(label("Symptoms right now", "section"))
        syms = list(NEURO_SYMPTOMS) + [s for s in ALL_SYMPTOMS if s not in NEURO_SYMPTOMS]
        self.chips: List[Chip] = [Chip(s.capitalize()) for s in syms]
        for c, s in zip(self.chips, syms):
            c.setProperty("symptom", s)
        v.addWidget(FlowRow(self.chips, per_row=5))

        self.onset = QLineEdit()
        self.onset.setPlaceholderText("For example: 14:05 UTC, or 'at dinner, about 20 minutes ago'")
        self.notes = QPlainTextEdit()
        self.notes.setPlaceholderText("Anything the flight surgeon should know")
        self.notes.setFixedHeight(64)
        v.addWidget(self._row("Symptom onset", self.onset))
        v.addWidget(self._row("Notes", self.notes))

        v.addSpacing(4)
        h = QHBoxLayout()
        h.addWidget(label("Results are compared with your own baseline.", "faint"))
        h.addStretch(1)
        cancel = button("Cancel", "ghost")
        cancel.clicked.connect(self.reject)
        go = button("Start camera exam", "primary" if kind == "daily" else "danger")
        go.setDefault(True)
        go.clicked.connect(self.accept)
        h.addWidget(cancel)
        h.addWidget(go)
        v.addLayout(h)

    def _row(self, text: str, w: QWidget) -> QWidget:
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        lb = label(text, "muted")
        lb.setFixedWidth(130)
        lb.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        h.addWidget(lb)
        h.addWidget(w, 1)
        return box

    def result(self) -> Dict:
        return {
            "mood": self.mood.value(),
            "sleep_quality": self.sleepq.value(),
            "stress": self.stress.value(),
            "sleep_hours": self.hours.value(),
            "symptoms": [c.property("symptom") for c in self.chips if c.isChecked()],
            "onset": self.onset.text().strip(),
            "notes": self.notes.toPlainText().strip(),
        }
