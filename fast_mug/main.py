"""FAST-ug launcher.

    python main.py                      # normal use with a webcam
    python main.py --simulate           # synthetic landmarks, no camera needed
    python main.py --simulate left_weakness
    python main.py --data D:\\fastmug    # use another data folder
"""
from __future__ import annotations

import argparse
import os
import sys
import warnings


def main() -> int:
    ap = argparse.ArgumentParser(description="FAST-ug crew neuro-health console")
    ap.add_argument("--simulate", nargs="?", const="healthy",
                    choices=["healthy", "left_weakness", "fatigue"],
                    help="use the simulated feed instead of a camera")
    ap.add_argument("--data", help="data folder (default: %%APPDATA%%\\FAST-ug)")
    args = ap.parse_args()

    warnings.filterwarnings("ignore", category=RuntimeWarning)
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    os.environ.setdefault("GLOG_minloglevel", "2")          # quiet MediaPipe
    os.environ.setdefault("TF_CPP_MIN_LOG_LEVEL", "2")

    from pathlib import Path
    from PySide6.QtWidgets import QApplication
    from fastmug import APP_NAME
    from fastmug.config import Settings
    from fastmug.storage import Store
    from fastmug.ui import theme
    from fastmug.ui.main_window import MainWindow
    from fastmug.ui.pages import AppContext

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName("FAST-ug")
    theme.apply(app)

    if args.data:
        settings = Settings(Path(args.data) / "settings.json")
        settings.set("data_dir", str(Path(args.data)))
    else:
        settings = Settings()
    store = Store(settings.data_dir)
    ctx = AppContext(settings, store)
    win = MainWindow(ctx, force_sim=args.simulate)
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
