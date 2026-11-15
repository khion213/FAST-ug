# FAST-µg: The Gravity-Free Stroke Screen

**An 80-second neurological screening console designed for weightlessness. One webcam. No wearables. Completely offline.**

Developed by **HOPE CANOPUS** (Baghdad, Iraq) for the **NASA Space Apps Challenge 2026**.

---

## Overview

On Earth, standard stroke screening protocols (such as FAST) rely on gravity to reveal motor weakness—for example, downward arm drift—and compare patients against terrestrial averages. In microgravity, a weak limb can float level, fluid shifts alter facial appearance, and deep-space communication delays can prevent ground flight surgeons from evaluating transient symptoms in time.

**FAST-µg** adapts rapid stroke screening to the physics of space using a standard webcam and on-device computer vision:
- **80-Second Guided Exam:** Evaluates facial symmetry, lip articulation (*"pa-ta-ka"* and reading), gravity-free hand motor tasks (thumb-to-index finger tapping and alternating hand turning), and ocular gaze tracking.
- **2-Minute Daily Alertness Check:** Tracks blinking, PERCLOS, and reaction time to continuously update each astronaut's personal rolling baseline.
- **Personalized In-Flight Baseline:** Compares crew members against their own rolling median and MAD variability ($z \ge 2$ Watch; $z \ge 3$ Alert) rather than Earth norms.
- **100% Offline & Autonomous:** Runs locally on standard hardware with zero wearables and generates structured clinical Word reports for the flight surgeon.

---

## Quick Start (Windows)

No IDE or coding environment (such as VS Code) is required to run the application:

1. **Install Python:** Ensure **Python 3.11 or 3.12** is installed on your Windows PC *(make sure to check **"Add python.exe to PATH"** during installation)*.
2. **Download the Repository:** Click **Code > Download ZIP** on this GitHub page and extract the folder.
3. **Launch the App:** Open the `fast_mug` folder and **double-click `run_windows.bat`**.
   - On the first launch, the script automatically installs the required libraries and downloads the MediaPipe face/hand landmark models.
   - **Testing without a webcam:** Open **Settings** inside the app and check *"Use the simulated feed instead of a camera"* (supports `Healthy`, `Left weakness`, and `Fatigue` simulation scenarios).

*(Alternative terminal launch from inside `fast_mug`:)*
```bash
pip install -r requirements.txt
python main.py --simulate
```

---

## System Architecture

- **Computer Vision:** MediaPipe (478-point Face Mesh + 21-point Hand Landmarker) & OpenCV
- **Signal Processing & Statistics:** NumPy & SciPy (30 Hz resampling, Welch spectral analysis, MAD-based personal $z$-scores)
- **User Interface & Reporting:** PySide6 (Qt6), Matplotlib, and `python-docx`

---

## Disclaimer

FAST-µg is a clinical screening aid and objective evidence-capture tool designed for spaceflight medicine research. It is not a standalone medical diagnostic device and has not yet been tested in orbital microgravity.

---

## Team — HOPE CANOPUS (Baghdad, Iraq)

- **Khayoon Alaayedi** — Team Lead
- **Zahraa Basheer**
- **Rami Rashan**
- **Falah Alaa**
- **Imad Dheyab**
- **Jaafar Salim**