"""Fast end-to-end check with the simulator and a fake clock (no camera, no window).

    python tests/sim_harness.py            # prints verdicts and writes a sample report
"""
import os
import sys
import tempfile
import warnings
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
warnings.filterwarnings("ignore")

from PySide6.QtCore import QCoreApplication  # noqa: E402

from fastmug.config import Settings  # noqa: E402
from fastmug.demo import create_demo_crew  # noqa: E402
from fastmug.report import build_report  # noqa: E402
from fastmug.storage import Store  # noqa: E402


def main() -> None:
    app = QCoreApplication([])  # noqa: F841
    d = Path(tempfile.mkdtemp(prefix="fastmug_"))
    settings = Settings(d / "settings.json")
    settings.set("data_dir", str(d))
    store = Store(d)
    m = create_demo_crew(store, settings, daily=5)
    for s in store.sessions(m["id"]):
        v = s["verdict"]
        print("%-12s %-20s weaker=%s  measures=%d" % (s["type_title"], v["headline"],
                                                     s.get("weaker_side"), len(s["raw_metrics"])))
    last = store.sessions(m["id"])[-1]
    expected = ("Neurological alert", "L")
    assert (last["verdict"]["headline"], last["weaker_side"]) == expected, "unexpected verdict"
    print("report:", build_report(last, store, settings))
    print("data folder:", d)


if __name__ == "__main__":
    main()
