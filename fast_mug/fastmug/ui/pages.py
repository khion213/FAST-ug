"""Application pages."""
from __future__ import annotations

import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog,
                               QFormLayout, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLineEdit,
                               QListWidget, QListWidgetItem, QMessageBox, QPlainTextEdit, QProgressBar,
                               QScrollArea, QSpinBox, QTableWidget, QTableWidgetItem, QVBoxLayout,
                               QWidget)

from .. import mailer, vision
from ..config import MODELS_DIR, Settings
from ..scoring import BY_KEY, CATALOG, DOMAINS, LATERAL_PAIRS, NEURO_DOMAINS
from ..storage import Store
from . import theme as T
from .stage import CameraStage
from .widgets import (Banner, LiveTrace, MidlineWidget, Ring, Sparkline, StatusPill, StepList,
                      TrendChart, button, hline, label, panel)


class AppContext(QObject):
    crew_changed = Signal()
    sessions_changed = Signal()
    open_session = Signal(object)

    def __init__(self, settings: Settings, store: Store):
        super().__init__()
        self.settings = settings
        self.store = store

    @property
    def member(self) -> Optional[Dict]:
        cid = self.settings.get("active_crew_id")
        m = self.store.member(cid) if cid else None
        if m is None:
            crew = self.store.crew()
            m = crew[0] if crew else None
            if m:
                self.settings.set("active_crew_id", m["id"])
        return m

    def set_member(self, cid: str) -> None:
        self.settings.set("active_crew_id", cid)
        self.settings.save()
        self.crew_changed.emit()


def fmt_when(iso: str, short: bool = False) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return iso or ""
    return d.strftime("%d %b, %H:%M" if short else "%d %b %Y, %H:%M UTC")


def midline_rows(session: Dict, history: Dict[str, List[float]]):
    raw = session.get("raw_metrics", {})
    rows = []
    for kr, kl, name in LATERAL_PAIRS:
        r, l = raw.get(kr), raw.get(kl)
        if r is None or l is None:
            continue
        vals = [v for v in history.get(kr, []) + history.get(kl, []) if v is not None]
        if len(vals) >= 2:
            ref = sorted(vals)[len(vals) // 2]
        elif kr in BY_KEY:
            ref = BY_KEY[kr].prior_mean
        else:
            ref = max(abs(r), abs(l))
        ref = ref or 1e-9
        rows.append((name, 100 * r / ref, 100 * l / ref))
    return rows


def scroll(widget: QWidget) -> QScrollArea:
    sa = QScrollArea()
    sa.setWidgetResizable(True)
    sa.setFrameShape(QFrame.Shape.NoFrame)
    sa.setWidget(widget)
    return sa


def _table(headers: List[str]) -> QTableWidget:
    t = QTableWidget(0, len(headers))
    t.setHorizontalHeaderLabels(headers)
    t.verticalHeader().setVisible(False)
    t.setShowGrid(False)
    t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    t.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    t.horizontalHeader().setHighlightSections(False)
    t.horizontalHeader().setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
    t.verticalHeader().setDefaultSectionSize(38)
    t.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    return t


def _item(text: str, color: str = "", bold: bool = False, align_right: bool = False) -> QTableWidgetItem:
    it = QTableWidgetItem(text)
    if color:
        it.setForeground(T.qc(color))
    if bold:
        it.setFont(T.font(10.5, 600))
    if align_right:
        it.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    return it


# =========================================================================== #
class OverviewPage(QWidget):
    start_exam = Signal(str)        # "daily" | "neuro"
    goto = Signal(int)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 26)
        root.setSpacing(18)

        head = QHBoxLayout()
        tv = QVBoxLayout()
        tv.setSpacing(2)
        self.name = label("", "h1")
        self.meta = label("", "muted")
        tv.addWidget(self.name)
        tv.addWidget(self.meta)
        head.addLayout(tv, 1)
        self.btn_daily = button("Start daily check", "primary", "large")
        self.btn_neuro = button("Run neuro exam", "danger", "large")
        self.btn_daily.setToolTip("About two minutes. Measures alertness and refreshes the baseline.")
        self.btn_neuro.setToolTip("About 80 seconds. Use when stroke-like symptoms appear.")
        self.btn_daily.clicked.connect(lambda: self.start_exam.emit("daily"))
        self.btn_neuro.clicked.connect(lambda: self.start_exam.emit("neuro"))
        head.addWidget(self.btn_daily, 0, Qt.AlignmentFlag.AlignBottom)
        head.addWidget(self.btn_neuro, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(head)

        self.empty = QFrame()
        ev = QVBoxLayout(self.empty)
        ev.addStretch(1)
        ev.addWidget(label("Add a crew member to begin.", "h2"), 0, Qt.AlignmentFlag.AlignHCenter)
        ev.addWidget(label("Each person gets a personal baseline from their own daily checks.", "muted"),
                     0, Qt.AlignmentFlag.AlignHCenter)
        b = button("Add crew member", "primary")
        b.clicked.connect(lambda: self.goto.emit(4))
        ev.addWidget(b, 0, Qt.AlignmentFlag.AlignHCenter)
        ev.addStretch(2)
        root.addWidget(self.empty, 1)

        self.body = QWidget()
        grid = QGridLayout(self.body)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)

        latest, lv = panel()
        lv.addWidget(label("Latest result", "section"))
        self.latest_pill = StatusPill()
        self.latest_head = label("", "h2")
        self.latest_when = label("", "muted")
        self.latest_text = label("", wrap=True)
        self.latest_text.setStyleSheet("color:%s;" % T.TEXT)
        row = QHBoxLayout()
        row.addWidget(self.latest_head)
        row.addStretch(1)
        row.addWidget(self.latest_pill)
        lv.addLayout(row)
        lv.addWidget(self.latest_when)
        lv.addWidget(self.latest_text)
        lv.addStretch(1)
        self.btn_open_latest = button("Open results", "ghost")
        self.btn_open_latest.clicked.connect(self._open_latest)
        lv.addWidget(self.btn_open_latest, 0, Qt.AlignmentFlag.AlignLeft)
        self.baseline_note = label("", "faint", wrap=True)
        lv.addWidget(self.baseline_note)

        mid, mv = panel()
        mv.addWidget(label("Side-to-side, latest exam", "section"))
        self.midline = MidlineWidget()
        mv.addWidget(self.midline, 1)

        doms, dv = panel()
        dv.addWidget(label("Domains", "section"))
        self.dom_rows: Dict[str, tuple] = {}
        for dk in list(NEURO_DOMAINS) + ["alert"]:
            r = QHBoxLayout()
            n = label(DOMAINS[dk])
            n.setFixedWidth(118)
            n.setStyleSheet("font-weight:500;")
            pill = StatusPill()
            idx = label("", "muted")
            idx.setFont(T.font(12, 600, numeric=True))
            idx.setFixedWidth(52)
            idx.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            sp = Sparkline()
            r.addWidget(n)
            r.addWidget(pill)
            r.addStretch(1)
            r.addWidget(sp)
            r.addWidget(idx)
            dv.addLayout(r)
            if dk != "alert":
                dv.addWidget(hline())
            self.dom_rows[dk] = (pill, idx, sp)
        dv.addStretch(1)

        recent, rv = panel()
        rh = QHBoxLayout()
        rh.addWidget(label("Recent sessions", "section"))
        rh.addStretch(1)
        allb = button("All history", "ghost")
        allb.clicked.connect(lambda: self.goto.emit(3))
        rh.addWidget(allb)
        rv.addLayout(rh)
        self.recent = _table(["When", "Exam", "Result"])
        self.recent.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.recent.cellDoubleClicked.connect(self._open_row)
        rv.addWidget(self.recent, 1)

        grid.addWidget(latest, 0, 0)
        grid.addWidget(mid, 0, 1)
        grid.addWidget(doms, 1, 0)
        grid.addWidget(recent, 1, 1)
        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 7)
        grid.setRowStretch(0, 5)
        grid.setRowStretch(1, 5)
        root.addWidget(self.body, 1)

        self._sessions: List[Dict] = []
        ctx.crew_changed.connect(self.refresh)
        ctx.sessions_changed.connect(self.refresh)

    def refresh(self) -> None:
        m = self.ctx.member
        has = m is not None
        self.empty.setVisible(not has)
        self.body.setVisible(has)
        self.btn_daily.setEnabled(has)
        self.btn_neuro.setEnabled(has)
        if not has:
            self.name.setText("No crew member selected")
            self.meta.setText("")
            return
        self.name.setText(m.get("name", ""))
        sess = self.ctx.store.sessions(m["id"])
        self._sessions = sess
        daily = [s for s in sess if s.get("type") == "daily"]
        role = m.get("role") or "Crew member"
        self.meta.setText("%s.  %d daily checks and %d neuro exams on file." %
                          (role, len(daily), len(sess) - len(daily)))
        need = int(self.ctx.settings.get("exam.min_personal_sessions", 3))
        if len(daily) < need:
            self.baseline_note.setText("Baseline still forming: %d of %d daily checks. Until then, "
                                       "reference values fill the gap." % (len(daily), need))
        else:
            self.baseline_note.setText("Personal baseline from the last %d daily checks." %
                                       min(len(daily), int(self.ctx.settings.get("exam.baseline_window", 10))))
        last = sess[-1] if sess else None
        if last:
            v = last["verdict"]
            self.latest_head.setText(v["headline"])
            self.latest_pill.set(v["level"], last.get("type_title", ""))
            self.latest_when.setText(fmt_when(last.get("started_utc", "")))
            from ..report import _verdict_lines
            lines = _verdict_lines(last)
            first = v["recommendations"][0] if v["recommendations"] else ""
            self.latest_text.setText("\n\n".join([lines[0], first]) if lines else first)
            self.btn_open_latest.setEnabled(True)
            hist = self.ctx.store.history(m["id"], int(self.ctx.settings.get("exam.baseline_window", 10)),
                                          exclude_id=last["id"])
            self.midline.set_rows(midline_rows(last, hist), last.get("weaker_side"))
        else:
            self.latest_head.setText("No exams yet")
            self.latest_pill.set("na", "Waiting")
            self.latest_when.setText("")
            self.latest_text.setText("Start with a daily check. It takes about two minutes and builds "
                                     "the personal baseline.")
            self.btn_open_latest.setEnabled(False)
            self.midline.set_rows([])
        for dk, (pill, idx, sp) in self.dom_rows.items():
            d = last["verdict"]["domains"].get(dk) if last else None
            if d:
                pill.set(d["status"])
                idx.setText("" if d["index"] is None else "%.0f" % d["index"])
            else:
                pill.set("na")
                idx.setText("")
            series = [s["verdict"]["domains"].get(dk, {}).get("index") for s in sess[-12:]]
            col = T.STATUS.get(d["status"], T.MUTED) if d else T.MUTED
            sp.set_values([x for x in series if x is not None], (85, 100), col)
        self.recent.setRowCount(0)
        for s in reversed(sess[-8:]):
            r = self.recent.rowCount()
            self.recent.insertRow(r)
            self.recent.setItem(r, 0, _item(fmt_when(s.get("started_utc", ""), True)))
            self.recent.setItem(r, 1, _item(s.get("type_title", "")))
            lv = s["verdict"]["level"]
            self.recent.setItem(r, 2, _item(s["verdict"]["headline"], T.STATUS.get(lv, T.TEXT), True))
            self.recent.item(r, 0).setData(Qt.ItemDataRole.UserRole, s["id"])

    def _open_latest(self) -> None:
        if self._sessions:
            self.ctx.open_session.emit(self._sessions[-1])

    def _open_row(self, row: int, _col: int) -> None:
        sid = self.recent.item(row, 0).data(Qt.ItemDataRole.UserRole)
        for s in self._sessions:
            if s["id"] == sid:
                self.ctx.open_session.emit(s)
                return


# =========================================================================== #
class ExamPage(QWidget):
    stop_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        root = QHBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 22)
        root.setSpacing(20)
        self.stage = CameraStage()
        root.addWidget(self.stage, 1)

        side = QFrame()
        side.setObjectName("Panel")
        side.setFixedWidth(372)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(22, 20, 22, 20)
        sv.setSpacing(14)
        top = QHBoxLayout()
        self.title = label("", "h3")
        self.elapsed = label("", "faint")
        top.addWidget(self.title)
        top.addStretch(1)
        top.addWidget(self.elapsed)
        sv.addLayout(top)
        self.total = QProgressBar()
        self.total.setTextVisible(False)
        self.total.setFixedHeight(4)
        self.total.setRange(0, 1000)
        sv.addWidget(self.total)

        cur = QHBoxLayout()
        cur.setSpacing(16)
        self.ring = Ring()
        cur.addWidget(self.ring, 0, Qt.AlignmentFlag.AlignTop)
        cv = QVBoxLayout()
        cv.setSpacing(6)
        self.step_title = label("", "h2")
        self.step_title.setWordWrap(True)
        self.step_text = label("", wrap=True)
        self.step_text.setStyleSheet("font-size:11.5pt; color:%s;" % T.TEXT)
        cv.addWidget(self.step_title)
        cv.addWidget(self.step_text)
        cv.addStretch(1)
        cur.addLayout(cv, 1)
        sv.addLayout(cur)
        self.trace = LiveTrace()
        sv.addWidget(self.trace)
        sv.addWidget(hline())
        self.steps = StepList()
        sv.addWidget(scroll(self.steps), 1)
        self.stop = button("Stop exam", "", icon_name="stop")
        self.stop.clicked.connect(self.stop_requested.emit)
        sv.addWidget(self.stop)
        root.addWidget(side)

    TRACE_CAPTIONS = {
        "openness": ("Eyelid openness", T.TEXT), "gaze": ("Horizontal gaze", T.MIDLINE),
        "mouth": ("Lip opening", T.TEXT), "mouth_tilt": ("Mouth corner tilt", T.TEXT),
        "smile": ("Mouth corner lift", T.TEXT), "brows": ("Brow height", T.TEXT),
        "pinch_R": ("Right thumb-to-index gap", T.RIGHT), "pinch_L": ("Left thumb-to-index gap", T.LEFT),
        "roll": ("Palm rotation", T.TEXT),
    }

    def begin(self, title: str, steps) -> None:
        self.title.setText(title)
        self.steps.set_steps([(s.group, s.title) for s in steps])
        self.total.setValue(0)
        self.stage.clear()

    def on_step(self, idx: int, step) -> None:
        self.steps.set_current(idx)
        self.step_title.setText(step.title)
        self.step_text.setText(step.instruction)
        cap, col = self.TRACE_CAPTIONS.get(step.live, ("", T.TEXT))
        self.trace.reset(col, cap)
        self.stage.guide = step.key == "align"

    def on_progress(self, frac: float, left: float, total: float, recording: bool) -> None:
        self.ring.set(frac, left, recording)
        self.total.setValue(int(total * 1000))


# =========================================================================== #
class ReportWorker(QThread):
    done = Signal(bool, str)

    def __init__(self, session: Dict, store: Store, settings: Settings, parent=None):
        super().__init__(parent)
        self.session, self.store, self.settings = session, store, settings

    def run(self) -> None:
        try:
            from ..report import build_report
            p = build_report(self.session, self.store, self.settings)
            self.done.emit(True, str(p))
        except Exception as exc:  # noqa: BLE001
            self.done.emit(False, "%s: %s" % (type(exc).__name__, exc))


class ResultsPage(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.session: Optional[Dict] = None
        self.report_path: Optional[Path] = None
        self._worker = None
        self._mail = None
        self._send_after = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(32, 26, 32, 26)
        root.setSpacing(18)
        outer.addWidget(scroll(content))

        head = QHBoxLayout()
        hv = QVBoxLayout()
        hv.setSpacing(2)
        self.h_title = label("", "h1")
        self.h_meta = label("", "muted")
        hv.addWidget(self.h_title)
        hv.addWidget(self.h_meta)
        head.addLayout(hv, 1)
        self.btn_report = button("Create Word report", "", icon_name="doc")
        self.btn_send = button("Send to flight surgeon", "primary", icon_name="send")
        self.btn_folder = button("Open folder", "ghost", icon_name="folder")
        self.btn_report.clicked.connect(lambda: self.make_report(False))
        self.btn_send.clicked.connect(self.send)
        self.btn_folder.clicked.connect(self.open_folder)
        for b in (self.btn_folder, self.btn_report, self.btn_send):
            head.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(head)
        self.banner = Banner()
        root.addWidget(self.banner)

        top = QHBoxLayout()
        top.setSpacing(18)
        self.verdict = QFrame()
        self.verdict.setObjectName("Panel")
        vv = QVBoxLayout(self.verdict)
        vv.setContentsMargins(24, 20, 22, 20)
        vv.setSpacing(10)
        self.v_head = label("", "h2")
        self.v_lines = label("", wrap=True)
        self.v_lines.setStyleSheet("font-size:11pt;")
        vv.addWidget(self.v_head)
        vv.addWidget(self.v_lines)
        vv.addWidget(label("Recommended actions", "section"))
        self.v_recs = label("", wrap=True)
        self.v_recs.setStyleSheet("font-size:11pt; line-height: 140%;")
        vv.addWidget(self.v_recs)
        vv.addStretch(1)
        top.addWidget(self.verdict, 5)
        mid, mv = panel()
        mv.addWidget(label("Side-to-side", "section"))
        self.midline = MidlineWidget()
        mv.addWidget(self.midline, 1)
        top.addWidget(mid, 6)
        root.addLayout(top)

        doms, dv = panel()
        dv.addWidget(label("Domains", "section"))
        self.dom_grid = QGridLayout()
        self.dom_grid.setHorizontalSpacing(24)
        self.dom_grid.setVerticalSpacing(10)
        dv.addLayout(self.dom_grid)
        root.addWidget(doms)

        tbl, tv = panel()
        tv.addWidget(label("All measurements", "section"))
        self.table = _table(["Measure", "Value", "Baseline", "z", "Status"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for c, w in ((1, 130), (2, 170), (3, 70), (4, 140)):
            hh.setSectionResizeMode(c, QHeaderView.ResizeMode.Fixed)
            self.table.setColumnWidth(c, w)
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tv.addWidget(self.table)
        root.addWidget(tbl)

    def show_session(self, session: Dict) -> None:
        self.session = session
        self.report_path = None
        folder = Path(session.get("folder", ""))
        existing = sorted(folder.glob("report_*.docx")) if folder.exists() else []
        if existing:
            self.report_path = existing[-1]
        self.banner.hide()
        v = session["verdict"]
        crew = session.get("crew", {})
        self.h_title.setText(session.get("type_title", "Results"))
        meta = "%s, %s, %.0f s" % (crew.get("name", ""), fmt_when(session.get("started_utc", "")),
                                    session.get("duration_s", 0))
        if session.get("simulated"):
            meta += ", simulated feed"
        self.h_meta.setText(meta)
        col = T.STATUS.get(v["level"], T.NA)
        self.verdict.setStyleSheet("#Panel{background:%s;border:1px solid %s;border-left:4px solid %s;"
                                   "border-radius:10px;}" % (T.SURFACE, T.LINE_SOFT, col))
        self.v_head.setText(v["headline"])
        self.v_head.setStyleSheet("color:%s;" % col)
        from ..report import _verdict_lines
        self.v_lines.setText("\n".join(_verdict_lines(session)))
        self.v_recs.setText("\n\n".join(v["recommendations"]))
        hist = self.ctx.store.history(session["crew_id"], int(self.ctx.settings.get("exam.baseline_window", 10)),
                                      exclude_id=session["id"])
        self.midline.set_rows(midline_rows(session, hist), session.get("weaker_side"))

        while self.dom_grid.count():
            it = self.dom_grid.takeAt(0)
            w = it.widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        for i, dk in enumerate(list(NEURO_DOMAINS) + ["alert"]):
            d = v["domains"].get(dk)
            if not d:
                continue
            n = label(d["name"])
            n.setStyleSheet("font-weight:600;")
            pill = StatusPill()
            pill.set(d["status"])
            idx = label("" if d["index"] is None else "%.0f / 100" % d["index"], "muted")
            flags = ", ".join(BY_KEY[k].label for k in d["flags"]) or "No flagged measures"
            fl = label(flags, "" if d["flags"] else "faint", wrap=True)
            self.dom_grid.addWidget(n, i, 0)
            self.dom_grid.addWidget(pill, i, 1)
            self.dom_grid.addWidget(idx, i, 2)
            self.dom_grid.addWidget(fl, i, 3)
        self.dom_grid.setColumnStretch(3, 1)

        self.table.setRowCount(0)
        last_dom = None
        for defn in CATALOG:
            s = v["metrics"].get(defn.key)
            if not s or not defn.scored:
                continue
            if defn.domain != last_dom:
                last_dom = defn.domain
                r = self.table.rowCount()
                self.table.insertRow(r)
                it = _item(DOMAINS[defn.domain], T.MUTED, True)
                self.table.setItem(r, 0, it)
                self.table.setSpan(r, 0, 1, 5)
            r = self.table.rowCount()
            self.table.insertRow(r)
            it = _item("    " + defn.label)
            it.setToolTip(defn.help)
            self.table.setItem(r, 0, it)
            self.table.setItem(r, 1, _item("%s %s" % (defn.format(s["value"]), defn.unit)))
            src = "" if s["source"] == "personal" else "  ref"
            self.table.setItem(r, 2, _item("%s ± %s%s" % (defn.format(s["mean"]), defn.format(s["sd"]), src),
                                           T.MUTED))
            self.table.setItem(r, 3, _item("—" if s["z"] is None else "%+.1f" % s["z"]))
            self.table.setItem(r, 4, _item(T.STATUS_WORD[s["status"]], T.STATUS[s["status"]], True))
        self.table.setFixedHeight(self.table.rowCount() * 38 + 42)

    # ---------------------------------------------------------- report/mail
    def make_report(self, then_send: bool) -> None:
        if not self.session or self._worker is not None:
            return
        self._send_after = then_send
        self.btn_report.setEnabled(False)
        self.btn_send.setEnabled(False)
        self.banner.show_msg("Creating the Word report with charts and images…", "info")
        self._worker = ReportWorker(self.session, self.ctx.store, self.ctx.settings, self)
        self._worker.done.connect(self._report_done)
        self._worker.start()

    def _report_done(self, ok: bool, msg: str) -> None:
        self._worker = None
        self.btn_report.setEnabled(True)
        self.btn_send.setEnabled(True)
        if not ok:
            self.banner.show_msg("The report could not be created. " + msg, "error")
            return
        self.report_path = Path(msg)
        if self._send_after:
            self._send_now()
        else:
            self.banner.show_msg("Report saved: %s" % self.report_path.name, "ok")
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.report_path)))

    def send(self) -> None:
        if not self.session:
            return
        cfg = self.ctx.settings.get("email", {})
        if not cfg.get("flight_surgeon") or not cfg.get("host"):
            self.banner.show_msg("Add the mail server and the flight surgeon's address in Settings "
                                 "> Ground link, then send again.", "warn")
            return
        if self.report_path is None or not self.report_path.exists():
            self.make_report(True)
        else:
            self._send_now()

    def _send_now(self) -> None:
        cfg = self.ctx.settings.get("email", {})
        s = self.session
        v = s["verdict"]
        subject = "[%s] %s, %s, %s" % (v["headline"], s.get("type_title"), s.get("crew", {}).get("name", ""),
                                       fmt_when(s.get("started_utc", ""), True))
        try:
            msg = mailer.build_message(cfg, subject, mailer.summary_body(s), [self.report_path])
        except Exception as exc:  # noqa: BLE001
            self.banner.show_msg("Could not prepare the email: %s" % exc, "error")
            return
        self.btn_send.setEnabled(False)
        self.banner.show_msg("Sending to %s…" % cfg.get("flight_surgeon"), "info")
        self._mail = mailer.MailWorker(cfg, msg, self)
        self._mail.done.connect(self._mail_done)
        self._mail.start()

    def _mail_done(self, ok: bool, msg: str) -> None:
        self.btn_send.setEnabled(True)
        self._mail = None
        if ok:
            self.banner.show_msg("Report sent. %s" % msg, "ok")
            self.session.setdefault("sent_to", []).append(msg)
        else:
            self.banner.show_msg("Not sent. " + msg, "error")

    def open_folder(self) -> None:
        if self.session:
            QDesktopServices.openUrl(QUrl.fromLocalFile(self.session.get("folder", "")))


# =========================================================================== #
class HistoryPage(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self._sessions: List[Dict] = []
        root = QHBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 26)
        root.setSpacing(18)

        left, lv = panel()
        lv.addWidget(label("Sessions", "h3"))
        self.table = _table(["When", "Exam", "Result", "Weaker side"])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.cellDoubleClicked.connect(lambda r, c: self._open())
        lv.addWidget(self.table, 1)
        ob = button("Open results", "")
        ob.clicked.connect(self._open)
        lv.addWidget(ob, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(left, 5)

        right, rv = panel()
        hr = QHBoxLayout()
        hr.addWidget(label("Trend", "h3"))
        hr.addStretch(1)
        self.metric = QComboBox()
        self.metric.setMinimumWidth(260)
        for d in CATALOG:
            if d.scored:
                self.metric.addItem("%s: %s" % (DOMAINS[d.domain], d.label), d.key)
        self.metric.currentIndexChanged.connect(self._trend)
        hr.addWidget(self.metric)
        rv.addLayout(hr)
        self.chart = TrendChart()
        rv.addWidget(self.chart, 1)
        rv.addWidget(label("Grey band: baseline ± 2 SD. Red points are neuro exams.", "faint"))
        root.addWidget(right, 6)
        ctx.crew_changed.connect(self.refresh)
        ctx.sessions_changed.connect(self.refresh)

    def refresh(self) -> None:
        m = self.ctx.member
        self._sessions = self.ctx.store.sessions(m["id"]) if m else []
        self.table.setRowCount(0)
        for s in reversed(self._sessions):
            r = self.table.rowCount()
            self.table.insertRow(r)
            self.table.setItem(r, 0, _item(fmt_when(s.get("started_utc", ""), True)))
            self.table.setItem(r, 1, _item(s.get("type_title", "")))
            lv = s["verdict"]["level"]
            self.table.setItem(r, 2, _item(s["verdict"]["headline"], T.STATUS.get(lv, T.TEXT), True))
            side = s.get("weaker_side")
            self.table.setItem(r, 3, _item({"L": "Left", "R": "Right"}.get(side, "—"),
                                           T.LEFT if side == "L" else T.RIGHT if side == "R" else T.FAINT))
            self.table.item(r, 0).setData(Qt.ItemDataRole.UserRole, s["id"])
        self._trend()

    def _trend(self) -> None:
        key = self.metric.currentData()
        if not key:
            return
        d = BY_KEY[key]
        pts = [(fmt_when(s.get("started_utc", ""), True).split(",")[0], s.get("raw_metrics", {}).get(key),
                s.get("type")) for s in self._sessions[-20:]]
        band = None
        if self._sessions:
            sc = self._sessions[-1]["verdict"]["metrics"].get(key)
            if sc:
                band = (sc["mean"] - 2 * sc["sd"], sc["mean"], sc["mean"] + 2 * sc["sd"])
        self.chart.set_data("%s (%s)" % (d.label, d.unit), d.unit, pts, band,
                            fmt=lambda v, d=d: d.format(v))

    def _open(self) -> None:
        r = self.table.currentRow()
        if r < 0:
            return
        sid = self.table.item(r, 0).data(Qt.ItemDataRole.UserRole)
        for s in self._sessions:
            if s["id"] == sid:
                self.ctx.open_session.emit(s)
                return


# =========================================================================== #
class CrewPage(QWidget):
    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        root = QHBoxLayout(self)
        root.setContentsMargins(32, 26, 32, 26)
        root.setSpacing(18)
        left, lv = panel()
        lv.addWidget(label("Crew", "h3"))
        self.list = QListWidget()
        self.list.currentRowChanged.connect(self._load)
        lv.addWidget(self.list, 1)
        nb = button("Add crew member", "")
        nb.clicked.connect(self._new)
        lv.addWidget(nb)
        root.addWidget(left, 4)

        right, rv = panel()
        self.form_title = label("New crew member", "h3")
        rv.addWidget(self.form_title)
        form = QFormLayout()
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(12)
        form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        self.f_name = QLineEdit()
        self.f_role = QLineEdit()
        self.f_role.setPlaceholderText("Commander, flight engineer, mission specialist")
        self.f_agency = QLineEdit()
        self.f_notes = QPlainTextEdit()
        self.f_notes.setPlaceholderText("Relevant history the flight surgeon already knows, glasses, "
                                        "dominant hand")
        self.f_notes.setFixedHeight(110)
        for text, w in (("Name", self.f_name), ("Role", self.f_role), ("Agency", self.f_agency),
                        ("Notes", self.f_notes)):
            form.addRow(label(text, "muted"), w)
        rv.addLayout(form)
        self.msg = Banner()
        rv.addWidget(self.msg)
        h = QHBoxLayout()
        self.b_del = button("Delete", "ghost")
        self.b_del.clicked.connect(self._delete)
        self.b_active = button("Use for exams", "")
        self.b_active.clicked.connect(self._activate)
        self.b_save = button("Save", "primary")
        self.b_save.clicked.connect(self._save)
        h.addWidget(self.b_del)
        h.addStretch(1)
        h.addWidget(self.b_active)
        h.addWidget(self.b_save)
        rv.addLayout(h)
        rv.addStretch(1)
        root.addWidget(right, 6)
        self._cur: Optional[str] = None
        ctx.crew_changed.connect(self.refresh)

    def refresh(self) -> None:
        crew = self.ctx.store.crew()
        active = self.ctx.settings.get("active_crew_id")
        self.list.blockSignals(True)
        self.list.clear()
        sel = -1
        for i, c in enumerate(crew):
            txt = c["name"] + ("    in use" if c["id"] == active else "")
            it = QListWidgetItem(txt)
            it.setData(Qt.ItemDataRole.UserRole, c["id"])
            self.list.addItem(it)
            if c["id"] == (self._cur or active):
                sel = i
        self.list.blockSignals(False)
        if sel >= 0:
            self.list.setCurrentRow(sel)
        elif not crew:
            self._new()

    def _load(self, row: int) -> None:
        if row < 0:
            return
        cid = self.list.item(row).data(Qt.ItemDataRole.UserRole)
        m = self.ctx.store.member(cid)
        if not m:
            return
        self._cur = cid
        self.form_title.setText(m["name"])
        self.f_name.setText(m.get("name", ""))
        self.f_role.setText(m.get("role", ""))
        self.f_agency.setText(m.get("agency", ""))
        self.f_notes.setPlainText(m.get("notes", ""))
        self.b_del.setEnabled(True)
        self.b_active.setEnabled(True)
        self.msg.hide()

    def _new(self) -> None:
        self._cur = None
        self.list.clearSelection()
        self.form_title.setText("New crew member")
        for w in (self.f_name, self.f_role, self.f_agency):
            w.clear()
        self.f_notes.clear()
        self.b_del.setEnabled(False)
        self.b_active.setEnabled(False)
        self.f_name.setFocus()

    def _save(self) -> None:
        name = self.f_name.text().strip()
        if not name:
            self.msg.show_msg("Enter a name before saving.", "warn")
            return
        m = {"name": name, "role": self.f_role.text().strip(), "agency": self.f_agency.text().strip(),
             "notes": self.f_notes.toPlainText().strip()}
        if self._cur:
            m["id"] = self._cur
        m = self.ctx.store.upsert_member(m)
        self._cur = m["id"]
        if not self.ctx.settings.get("active_crew_id") or len(self.ctx.store.crew()) == 1:
            self.ctx.set_member(m["id"])
        self.msg.show_msg("Saved.", "ok")
        self.ctx.crew_changed.emit()

    def _activate(self) -> None:
        if self._cur:
            self.ctx.set_member(self._cur)

    def _delete(self) -> None:
        if not self._cur:
            return
        m = self.ctx.store.member(self._cur)
        ans = QMessageBox.question(self, "Delete crew member",
                                   "Delete %s from the crew list? Their exam files stay on disk." % m["name"])
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.ctx.store.delete_member(self._cur)
        if self.ctx.settings.get("active_crew_id") == self._cur:
            self.ctx.settings.set("active_crew_id", "")
            self.ctx.settings.save()
        self._cur = None
        self.ctx.crew_changed.emit()


# =========================================================================== #
class _Task(QThread):
    done = Signal(bool, str)
    step = Signal(str)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self) -> None:
        try:
            self.done.emit(True, self.fn(self.step.emit) or "")
        except Exception as exc:  # noqa: BLE001
            self.done.emit(False, "%s: %s" % (type(exc).__name__, exc))


class SettingsPage(QWidget):
    camera_changed = Signal()

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        s = ctx.settings
        self._task = None
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        content = QWidget()
        root = QVBoxLayout(content)
        root.setContentsMargins(32, 26, 32, 26)
        root.setSpacing(18)
        outer.addWidget(scroll(content))
        head = QHBoxLayout()
        head.addWidget(label("Settings", "h1"))
        head.addStretch(1)
        save = button("Save settings", "primary")
        save.clicked.connect(self.save)
        head.addWidget(save, 0, Qt.AlignmentFlag.AlignBottom)
        root.addLayout(head)
        self.banner = Banner()
        root.addWidget(self.banner)

        cols = QHBoxLayout()
        cols.setSpacing(18)
        c1, c2 = QVBoxLayout(), QVBoxLayout()
        c1.setSpacing(18)
        c2.setSpacing(18)
        cols.addLayout(c1, 1)
        cols.addLayout(c2, 1)
        root.addLayout(cols)

        # camera
        p, v = panel()
        v.addWidget(label("Camera", "h3"))
        f = self._form(v)
        self.cam_src = QLineEdit(str(s.get("camera.source")))
        self.cam_src.setToolTip("Webcam index (0, 1, 2) or the path of a video file for a recorded demo.")
        bb = button("Video file…", "ghost")
        bb.clicked.connect(self._pick_video)
        row = QHBoxLayout()
        row.addWidget(self.cam_src, 1)
        row.addWidget(bb)
        w = QWidget()
        w.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        f.addRow(label("Source", "muted"), w)
        self.cam_res = QComboBox()
        for txt, wh in (("1280 × 720", (1280, 720)), ("1920 × 1080", (1920, 1080)),
                        ("640 × 480", (640, 480))):
            self.cam_res.addItem(txt, wh)
        cur = (s.get("camera.width"), s.get("camera.height"))
        for i in range(self.cam_res.count()):
            if tuple(self.cam_res.itemData(i)) == tuple(cur):
                self.cam_res.setCurrentIndex(i)
        f.addRow(label("Resolution", "muted"), self.cam_res)
        self.sim = QCheckBox("Use the simulated feed instead of a camera")
        self.sim.setChecked(bool(s.get("camera.simulate", False)))
        self.scen = QComboBox()
        for txt, key in (("Healthy", "healthy"), ("Left-sided weakness", "left_weakness"),
                         ("Fatigue", "fatigue")):
            self.scen.addItem(txt, key)
        idx = self.scen.findData(s.get("camera.scenario", "healthy"))
        self.scen.setCurrentIndex(max(0, idx))
        f.addRow(label("Testing", "muted"), self.sim)
        f.addRow(label("Scenario", "muted"), self.scen)
        v.addWidget(label("The simulated feed drives synthetic landmarks for testing the software "
                          "without a camera. Its sessions are labelled as simulated.", "faint", wrap=True))
        c1.addWidget(p)

        # models
        p, v = panel()
        v.addWidget(label("Landmark models", "h3"))
        self.models_state = label("", "muted", wrap=True)
        v.addWidget(self.models_state)
        h = QHBoxLayout()
        self.b_models = button("Download models", "")
        self.b_models.clicked.connect(self._download_models)
        h.addWidget(self.b_models)
        mb = button("Open models folder", "ghost")
        mb.clicked.connect(lambda: (MODELS_DIR.mkdir(exist_ok=True),
                                    QDesktopServices.openUrl(QUrl.fromLocalFile(str(MODELS_DIR)))))
        h.addWidget(mb)
        h.addStretch(1)
        v.addLayout(h)
        c1.addWidget(p)

        # mission
        p, v = panel()
        v.addWidget(label("Mission", "h3"))
        f = self._form(v)
        self.m_name = QLineEdit(s.get("mission.name", ""))
        self.m_vehicle = QLineEdit(s.get("mission.vehicle", ""))
        self.m_start = QLineEdit(s.get("mission.start_utc", ""))
        self.m_start.setPlaceholderText("2026-11-01T00:00:00")
        f.addRow(label("Mission", "muted"), self.m_name)
        f.addRow(label("Vehicle", "muted"), self.m_vehicle)
        f.addRow(label("Launch (UTC)", "muted"), self.m_start)
        c1.addWidget(p)

        # email
        p, v = panel()
        v.addWidget(label("Ground link", "h3"))
        v.addWidget(label("Reports go to the flight surgeon by email.", "muted"))
        f = self._form(v)
        e = s.get("email", {})
        self.e_to = QLineEdit(e.get("flight_surgeon", ""))
        self.e_to.setPlaceholderText("surgeon@example.org")
        self.e_cc = QLineEdit(e.get("cc", ""))
        self.e_host = QLineEdit(e.get("host", ""))
        self.e_port = QSpinBox()
        self.e_port.setRange(1, 65535)
        self.e_port.setValue(int(e.get("port", 465)))
        self.e_sec = QComboBox()
        self.e_sec.addItems(["SSL", "STARTTLS", "NONE"])
        self.e_sec.setCurrentText(e.get("security", "SSL"))
        self.e_user = QLineEdit(e.get("username", ""))
        self.e_pass = QLineEdit()
        self.e_pass.setEchoMode(QLineEdit.EchoMode.Password)
        self.e_pass.setPlaceholderText("Unchanged" if (e.get("password") or e.get("username")) else "App password")
        self.e_from = QLineEdit(e.get("sender", ""))
        self.e_from.setPlaceholderText("Defaults to the username")
        for text, w in (("Flight surgeon", self.e_to), ("Copy to", self.e_cc), ("Mail server", self.e_host),
                        ("Port", self.e_port), ("Security", self.e_sec), ("Username", self.e_user),
                        ("Password", self.e_pass), ("From", self.e_from)):
            f.addRow(label(text, "muted"), w)
        h = QHBoxLayout()
        self.b_test = button("Test connection", "")
        self.b_test.clicked.connect(self._test_mail)
        h.addWidget(self.b_test)
        h.addStretch(1)
        v.addLayout(h)
        v.addWidget(label("Gmail: use smtp.gmail.com, port 465, SSL, and an app password. "
                          "Passwords go to the system keychain when the keyring package is installed.",
                          "faint", wrap=True))
        c2.addWidget(p)

        # exam
        p, v = panel()
        v.addWidget(label("Scoring", "h3"))
        f = self._form(v)
        self.x_watch = QDoubleSpinBox()
        self.x_watch.setRange(1.0, 5.0)
        self.x_watch.setSingleStep(0.1)
        self.x_watch.setValue(float(s.get("exam.watch_z", 2.0)))
        self.x_alert = QDoubleSpinBox()
        self.x_alert.setRange(1.5, 8.0)
        self.x_alert.setSingleStep(0.1)
        self.x_alert.setValue(float(s.get("exam.alert_z", 3.0)))
        self.x_window = QSpinBox()
        self.x_window.setRange(3, 60)
        self.x_window.setValue(int(s.get("exam.baseline_window", 10)))
        self.x_min = QSpinBox()
        self.x_min.setRange(1, 20)
        self.x_min.setValue(int(s.get("exam.min_personal_sessions", 3)))
        f.addRow(label("Watch at z ≥", "muted"), self.x_watch)
        f.addRow(label("Alert at z ≥", "muted"), self.x_alert)
        f.addRow(label("Baseline window", "muted"), self.x_window)
        f.addRow(label("Personal after", "muted"), self.x_min)
        c2.addWidget(p)

        # data
        p, v = panel()
        v.addWidget(label("Data", "h3"))
        self.data_lbl = label(str(s.data_dir), "muted", wrap=True)
        v.addWidget(self.data_lbl)
        h = QHBoxLayout()
        ob = button("Open data folder", "ghost")
        ob.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.settings.data_dir))))
        h.addWidget(ob)
        self.b_demo = button("Create demo crew", "")
        self.b_demo.setToolTip("Adds a simulated crew member with a week of daily checks, a fatigue "
                               "day and a neuro alert, for training and presentations.")
        self.b_demo.clicked.connect(self._demo)
        h.addWidget(self.b_demo)
        h.addStretch(1)
        v.addLayout(h)
        c2.addWidget(p)
        c1.addStretch(1)
        c2.addStretch(1)
        self._models_label()

    def _form(self, v: QVBoxLayout) -> QFormLayout:
        f = QFormLayout()
        f.setHorizontalSpacing(18)
        f.setVerticalSpacing(10)
        f.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        v.addLayout(f)
        return f

    def _models_label(self) -> None:
        if vision.models_present():
            self.models_state.setText("Face and hand models are installed in %s." % MODELS_DIR)
            self.b_models.setText("Download again")
        else:
            self.models_state.setText("Models are not installed yet. They are about 11 MB and are "
                                      "needed once, with an internet connection.")

    def _pick_video(self) -> None:
        f, _ = QFileDialog.getOpenFileName(self, "Choose a recorded video", "",
                                           "Video (*.mp4 *.avi *.mov *.mkv)")
        if f:
            self.cam_src.setText(f)

    def save(self) -> None:
        s = self.ctx.settings
        src = self.cam_src.text().strip() or "0"
        s.set("camera.source", int(src) if src.isdigit() else src)
        wh = self.cam_res.currentData()
        s.set("camera.width", wh[0])
        s.set("camera.height", wh[1])
        s.set("camera.simulate", self.sim.isChecked())
        s.set("camera.scenario", self.scen.currentData())
        s.set("mission.name", self.m_name.text().strip())
        s.set("mission.vehicle", self.m_vehicle.text().strip())
        s.set("mission.start_utc", self.m_start.text().strip())
        s.set("email.flight_surgeon", self.e_to.text().strip())
        s.set("email.cc", self.e_cc.text().strip())
        s.set("email.host", self.e_host.text().strip())
        s.set("email.port", self.e_port.value())
        s.set("email.security", self.e_sec.currentText())
        s.set("email.username", self.e_user.text().strip())
        s.set("email.sender", self.e_from.text().strip())
        pw = self.e_pass.text()
        note = ""
        if pw:
            if mailer.store_password(s.get("email", {}), pw):
                s.set("email.password", "")
                note = " The password is in the system keychain."
            else:
                s.set("email.password", pw)
                note = " The password is stored in settings.json on this computer."
            self.e_pass.clear()
            self.e_pass.setPlaceholderText("Unchanged")
        s.set("exam.watch_z", self.x_watch.value())
        s.set("exam.alert_z", max(self.x_alert.value(), self.x_watch.value() + 0.1))
        s.set("exam.baseline_window", self.x_window.value())
        s.set("exam.min_personal_sessions", self.x_min.value())
        s.save()
        self.banner.show_msg("Settings saved." + note, "ok")
        self.camera_changed.emit()

    def _test_mail(self) -> None:
        self.save()
        self.b_test.setEnabled(False)
        self.banner.show_msg("Connecting to %s…" % self.ctx.settings.get("email.host"), "info")
        self._mail = mailer.TestWorker(self.ctx.settings.get("email", {}), self)
        self._mail.done.connect(self._mail_done)
        self._mail.start()

    def _mail_done(self, ok: bool, msg: str) -> None:
        self.b_test.setEnabled(True)
        self.banner.show_msg(msg, "ok" if ok else "error")

    def _download_models(self) -> None:
        self.b_models.setEnabled(False)
        self.banner.show_msg("Downloading landmark models…", "info")
        self._task = _Task(lambda cb: (vision.download_models(cb), "Models installed.")[1], self)
        self._task.step.connect(lambda t: self.banner.show_msg(t + "…", "info"))
        self._task.done.connect(self._models_done)
        self._task.start()

    def _models_done(self, ok: bool, msg: str) -> None:
        self.b_models.setEnabled(True)
        self._models_label()
        if ok:
            self.banner.show_msg(msg, "ok")
        else:
            self.banner.show_msg("Download failed (%s). Download the two files manually from "
                                 "the links in README.md and put them in the models folder." % msg, "error")

    def _demo(self) -> None:
        self.b_demo.setEnabled(False)
        self.banner.show_msg("Creating the demo crew with simulated sessions…", "info")

        def work(cb):
            from ..demo import create_demo_crew
            m = create_demo_crew(self.ctx.store, self.ctx.settings,
                                 progress=lambda i, n: cb("Simulated session %d of %d" % (i, n)))
            self.ctx.settings.set("active_crew_id", m["id"])
            self.ctx.settings.save()
            return "Demo crew created. It is now the active crew member."
        self._task = _Task(work, self)
        self._task.step.connect(lambda t: self.banner.show_msg(t + "…", "info"))
        self._task.done.connect(self._demo_done)
        self._task.start()

    def _demo_done(self, ok: bool, msg: str) -> None:
        self.b_demo.setEnabled(True)
        self.banner.show_msg(msg, "ok" if ok else "error")
        self.ctx.crew_changed.emit()
        self.ctx.sessions_changed.emit()


__all__ = ["AppContext", "OverviewPage", "ExamPage", "ResultsPage", "HistoryPage", "CrewPage",
           "SettingsPage", "math"]
