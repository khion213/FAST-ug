"""Offline simulated sessions (fake clock) for demos and tests.

Everything created here is labelled as simulated in the session file and the report.
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional

from .protocol import ExamController
from .storage import Store
from .vision import SimState, SimulatedWorker


class _Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def run_offline(kind: str, scenario: str, store: Store, settings, member: Dict, seed: int = 1,
                self_report: Optional[Dict] = None) -> Dict:
    clock = _Clock()
    st = SimState()
    st.scenario = scenario
    sim = SimulatedWorker(st, seed=seed)
    ctl = ExamController(store, settings, clock=clock, use_timer=False)
    ctl.sim = st
    out: Dict = {}
    ctl.finished.connect(lambda s: out.setdefault("session", s))
    ctl.aborted.connect(lambda r: out.setdefault("error", r))
    ctl.start(kind, member, self_report or {"mood": 4, "sleep_quality": 4, "sleep_hours": 7,
                                            "stress": 2, "symptoms": []})
    t0 = clock.t
    while ctl.running and clock.t - t0 < 400:
        clock.t += 1.0 / 30.0
        ctl.on_frame(sim.synthesize(clock.t, clock.t - t0))
        ctl._tick()
    if "error" in out:
        raise RuntimeError(out["error"])
    return out["session"]


def create_demo_crew(store: Store, settings, daily: int = 6,
                     progress: Optional[Callable[[int, int], None]] = None) -> Dict:
    member = store.upsert_member({"name": "Demo crew (simulated)", "role": "Flight engineer",
                                  "agency": "Simulation", "notes": "Synthetic landmarks, not a person."})
    total = daily + 2
    for i in range(daily):
        run_offline("daily", "healthy", store, settings, member, seed=i)
        if progress:
            progress(i + 1, total)
    run_offline("daily", "fatigue", store, settings, member, seed=50,
                self_report={"mood": 4, "sleep_quality": 4, "sleep_hours": 5, "stress": 3, "symptoms": []})
    if progress:
        progress(daily + 1, total)
    run_offline("neuro", "left_weakness", store, settings, member, seed=99,
                self_report={"mood": 3, "sleep_quality": 3, "sleep_hours": 6, "stress": 4,
                             "symptoms": ["speech difficulty", "facial droop"],
                             "onset": "Within the last hour",
                             "notes": "Crewmate noticed slurred speech during dinner."})
    if progress:
        progress(total, total)
    return member
