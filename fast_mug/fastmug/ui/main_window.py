"""Main window: navigation, top bar and the exam flow."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QMainWindow, QMessageBox,
                               QStackedWidget, QVBoxLayout, QWidget)

from .. import APP_LONG_NAME, vision
from ..protocol import PROTOCOL_TITLES, ExamController
from ..report import mission_day
from . import icons
from . import theme as T
from .dialogs import SelfReportDialog
from .pages import (AppContext, CrewPage, ExamPage, HistoryPage, OverviewPage, ResultsPage,
                    SettingsPage)
from .widgets import NavRail, StatusPill, label

OVERVIEW, EXAM, RESULTS, HISTORY, CREW, SETTINGS = range(6)


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, force_sim: Optional[str] = None):
        super().__init__()
        self.ctx = ctx
        self.force_sim = force_sim
        self.worker = None
        self.setWindowTitle(APP_LONG_NAME)
        self.setWindowIcon(icons.app_icon())
        self.resize(1440, 900)
        self.setMinimumSize(1180, 760)

        root = QWidget()
        root.setObjectName("Root")
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.nav = NavRail([("overview", "Overview"), ("exam", "Exam"), ("results", "Results"),
                            ("history", "History"), ("crew", "Crew"), ("settings", "Settings")])
        self.nav.changed.connect(self.goto)
        h.addWidget(self.nav)

        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self._topbar())
        self.stack = QStackedWidget()
        self.overview = OverviewPage(ctx)
        self.exam = ExamPage()
        self.results = ResultsPage(ctx)
        self.history = HistoryPage(ctx)
        self.crew = CrewPage(ctx)
        self.settings_page = SettingsPage(ctx)
        for w in (self.overview, self.exam, self.results, self.history, self.crew, self.settings_page):
            self.stack.addWidget(w)
        col.addWidget(self.stack, 1)
        h.addLayout(col, 1)
        self.setCentralWidget(root)

        self.ctl = ExamController(ctx.store, ctx.settings, self)
        self.ctl.step_changed.connect(self.exam.on_step)
        self.ctl.progress.connect(self.exam.on_progress)
        self.ctl.stimulus.connect(self.exam.stage.set_stimulus)
        self.ctl.live_sample.connect(self.exam.trace.push)
        self.ctl.notice.connect(self.exam.stage.set_notice)
        self.ctl.need_hands.connect(self._need_hands)
        self.ctl.finished.connect(self._finished)
        self.ctl.aborted.connect(self._aborted)
        self.exam.stop_requested.connect(lambda: self.ctl.abort("Exam stopped. Nothing was saved."))
        self.overview.start_exam.connect(self.start_exam)
        self.overview.goto.connect(self.goto)
        ctx.open_session.connect(self.open_session)
        ctx.crew_changed.connect(self._fill_crew)
        self.settings_page.camera_changed.connect(self._update_link)
        QShortcut(QKeySequence(Qt.Key.Key_Escape), self, activated=self._escape)

        self._clock = QTimer(self)
        self._clock.timeout.connect(self._tick_clock)
        self._clock.start(1000)
        self._fill_crew()
        self._tick_clock()
        self._update_link()
        self.overview.refresh()
        self.history.refresh()
        self.crew.refresh()
        self.exam.stage.clear("The camera starts when an exam begins.")

    # ------------------------------------------------------------- top bar
    def _topbar(self) -> QWidget:
        bar = QFrame()
        bar.setObjectName("TopBar")
        bar.setFixedHeight(58)
        h = QHBoxLayout(bar)
        h.setContentsMargins(32, 0, 24, 0)
        h.setSpacing(14)
        h.addWidget(label("Crew member", "muted"))
        self.crew_box = QComboBox()
        self.crew_box.setMinimumWidth(230)
        self.crew_box.activated.connect(self._crew_picked)
        h.addWidget(self.crew_box)
        h.addStretch(1)
        self.mission = label("", "muted")
        h.addWidget(self.mission)
        self.utc = label("")
        self.utc.setFont(T.font(12, 600, numeric=True))
        h.addWidget(self.utc)
        h.addSpacing(10)
        self.link = StatusPill()
        h.addWidget(self.link)
        return bar

    def _fill_crew(self) -> None:
        self.crew_box.blockSignals(True)
        self.crew_box.clear()
        m = self.ctx.member
        for c in self.ctx.store.crew():
            self.crew_box.addItem(c["name"], c["id"])
        if m:
            self.crew_box.setCurrentIndex(max(0, self.crew_box.findData(m["id"])))
        else:
            self.crew_box.addItem("No crew yet", "")
        self.crew_box.blockSignals(False)

    def _crew_picked(self, i: int) -> None:
        cid = self.crew_box.itemData(i)
        if cid and not self.ctl.running:
            self.ctx.set_member(cid)

    def _tick_clock(self) -> None:
        now = datetime.now(timezone.utc)
        self.utc.setText(now.strftime("%H:%M UTC"))
        md = mission_day(self.ctx.settings, now.strftime("%Y-%m-%dT%H:%M:%S"))
        name = self.ctx.settings.get("mission.name", "")
        self.mission.setText("%s, day %d" % (name, md) if md and md > 0 else name)

    def _sim_scenario(self) -> Optional[str]:
        if self.force_sim:
            return self.force_sim
        if self.ctx.settings.get("camera.simulate"):
            return self.ctx.settings.get("camera.scenario", "healthy")
        return None

    def _update_link(self) -> None:
        if self.worker is not None:
            return
        sim = self._sim_scenario()
        if sim:
            self.link.set("watch", "Simulated feed")
        elif vision.models_present():
            self.link.set("na", "Camera idle")
        else:
            self.link.set("watch", "Models missing")

    # ---------------------------------------------------------- navigation
    def goto(self, i: int) -> None:
        if self.ctl.running and i != EXAM:
            self.nav.select(EXAM)
            return
        self.nav.select(i)
        self.stack.setCurrentIndex(i)
        if i == RESULTS and self.results.session is None:
            sess = self.ctx.store.sessions(self.ctx.member["id"]) if self.ctx.member else []
            if sess:
                self.results.show_session(sess[-1])
        if i == HISTORY:
            self.history.refresh()

    def open_session(self, session) -> None:
        self.results.show_session(session)
        self.goto(RESULTS)

    def _escape(self) -> None:
        if self.ctl.running:
            self.ctl.abort("Exam stopped. Nothing was saved.")

    # ------------------------------------------------------------ the exam
    def start_exam(self, kind: str) -> None:
        member = self.ctx.member
        if member is None:
            self.goto(CREW)
            return
        sim = self._sim_scenario()
        if not sim and not vision.models_present():
            ans = QMessageBox.question(
                self, "Landmark models needed",
                "The face and hand models are not installed yet. Open Settings to download them "
                "(about 11 MB)?")
            if ans == QMessageBox.StandardButton.Yes:
                self.goto(SETTINGS)
            return
        dlg = SelfReportDialog(kind, member["name"], self)
        if dlg.exec() != SelfReportDialog.DialogCode.Accepted:
            return
        report = dlg.result()
        self._start_worker(sim)
        self.exam.stage.clear()
        self.ctl.sim = self.worker.state if sim else None
        self.goto(EXAM)
        self.ctl.start(kind, member, report)
        self.exam.begin(PROTOCOL_TITLES[kind], self.ctl.steps)
        self.exam.on_step(0, self.ctl.steps[0])
        self.nav.setEnabled(False)
        self.crew_box.setEnabled(False)

    def _start_worker(self, sim: Optional[str]) -> None:
        self._stop_worker()
        if sim:
            st = vision.SimState()
            st.scenario = sim
            self.worker = vision.SimulatedWorker(st)
        else:
            s = self.ctx.settings
            self.worker = vision.CameraWorker(s.get("camera.source", 0), int(s.get("camera.width", 1280)),
                                              int(s.get("camera.height", 720)))
        self.worker.frame_ready.connect(self.exam.stage.set_frame)
        self.worker.frame_ready.connect(self.ctl.on_frame)
        self.worker.status.connect(lambda t: self.link.set("ok", t))
        self.worker.failed.connect(self._camera_failed)
        self.link.set("watch", "Starting camera")
        self.worker.start()

    def _stop_worker(self) -> None:
        if self.worker is not None:
            try:
                self.worker.frame_ready.disconnect()
            except (RuntimeError, TypeError):
                pass
            self.worker.stop()
            self.worker = None
        self._update_link()

    def _need_hands(self, on: bool) -> None:
        if self.worker is not None:
            self.worker.need_hands = on

    def _camera_failed(self, msg: str) -> None:
        self.link.set("alert", "Camera error")
        if self.ctl.running:
            self.ctl.abort(msg)
        else:
            QMessageBox.warning(self, "Camera", msg)

    def _finished(self, session) -> None:
        self._stop_worker()
        self.nav.setEnabled(True)
        self.crew_box.setEnabled(True)
        self.exam.stage.clear("Exam complete.")
        self.ctx.sessions_changed.emit()
        self.open_session(session)

    def _aborted(self, reason: str) -> None:
        self._stop_worker()
        self.nav.setEnabled(True)
        self.crew_box.setEnabled(True)
        self.exam.stage.clear(reason)
        self.goto(OVERVIEW)
        QMessageBox.information(self, "Exam stopped", reason)

    def closeEvent(self, e) -> None:
        if self.ctl.running:
            self.ctl.abort("Closing.")
        self._stop_worker()
        self.ctx.settings.save()
        super().closeEvent(e)
