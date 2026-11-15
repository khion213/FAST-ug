# FAST-μg

A camera-only neuro-health console for spaceflight crews, built for the NASA Space Apps
Challenge 2026 brief *Create Health Monitoring Software for Astronauts on Space Missions*.

It does two jobs with one ordinary webcam:

| Mode | Time | What it is for |
|---|---|---|
| **Daily check** | about 2 min | Alertness and behavioural health (PERCLOS, blinks, micro-sleeps, saccade reaction time, fixation), and it refreshes the personal baseline for every neuro measure. |
| **Neuro exam** | about 80 s | A stroke screen in the spirit of FAST (face, arm, speech, time) adapted for weightlessness. Run it when stroke-like symptoms appear. |

Every result is compared with the crew member's own rolling baseline, then written to a
Word report with charts and annotated patient images that can be emailed to the flight
surgeon from inside the app.

> Screening and decision support only. It does not diagnose stroke, TIA or anything else.

## Why "adapted for weightlessness"

* **The arm test stops working in orbit.** The NIH Stroke Scale scores arm strength by whether
  the outstretched arm drifts down within 10 seconds. Without gravity the arm does not fall,
  so FAST-μg screens motor strength with **finger tapping** and **rapid hand turning
  (pronation and supination)**, compared side to side.
* **The face changes shape in orbit.** Fluid shifts toward the head make faces puffy, so facial
  symmetry is judged against the **in-flight personal baseline**, not population norms.
* **The balance item of BE-FAST** also depends on gravity and is left out.
* Eye movements (smooth pursuit, binocular conjugacy) cover the "Eyes" part of BE-FAST.

## Measures

| Domain | Measures |
|---|---|
| Face | mouth-corner tilt at rest, smile symmetry, brow-raise symmetry, eye-closure asymmetry |
| Speech (lips, no microphone) | pa-ta-ka rate and regularity, articulation amplitude, lip-corner symmetry, reading articulation (NIHSS sentences) |
| Hands | tapping rate, amplitude and fatigue per hand, rapid alternating movements per hand, left/right symmetry |
| Eye movements | smooth-pursuit coherence, binocular conjugacy |
| Alertness | PERCLOS, blink rate and duration, micro-sleeps, saccade reaction time and errors, fixation instability, head sway |

Each measure gets a directional z-score against the baseline (median and robust spread of the
last 10 daily checks). z ≥ 2 is *watch*, z ≥ 3 is *alert*; a few measures also have absolute
limits. Until a crew member has 3 daily checks, reference values are blended in and the report
marks those rows.

## Quick start (Windows, Python 3.9)

```bat
run_windows.bat
```

or by hand:

```bat
py -3.9 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

1. **Settings > Landmark models > Download models** (once, about 11 MB). If the download is
   blocked, fetch the two files yourself and put them in the `models` folder:
   * https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/latest/face_landmarker.task
   * https://storage.googleapis.com/mediapipe-models/hand_landmarker/hand_landmarker/float16/latest/hand_landmarker.task
2. **Crew > Add crew member.**
3. **Overview > Start daily check.** Do three of these on different occasions to form a baseline.
4. **Run neuro exam** whenever symptoms appear.
5. On the results page: **Create Word report** or **Send to flight surgeon**.

### Email (ground link)

Settings > Ground link. For Gmail: server `smtp.gmail.com`, port `465`, security `SSL`, your
address as username and an **app password** (Google account > Security > App passwords).
With `keyring` installed the password is kept in the Windows Credential Manager.

### Without a camera

```bat
python main.py --simulate                 # healthy
python main.py --simulate left_weakness   # left-sided facial and hand weakness, slow speech
python main.py --simulate fatigue         # long blinks, micro-sleeps, slow saccades
```

Settings > Data > **Create demo crew** adds a simulated crew member with a week of daily checks,
a fatigue day and a neuro alert, which is useful for practising the presentation. Simulated
sessions are labelled as simulated everywhere.

### Recorded video

Put the path of a video file in Settings > Camera > Source to run the exam on a recording.

## Filming tips

* Camera at eye level, an arm's length away, face evenly lit from the front.
* Keep the head still during the eye tests.
* During hand steps, raise the hand beside the face with the palm toward the camera.

## Project layout

```
main.py                 launcher
fastmug/vision.py       camera thread, MediaPipe Tasks inference, simulator
fastmug/signals.py      per-frame features and all clinical metrics (NumPy/SciPy)
fastmug/protocol.py     exam steps, stimuli and the real-time controller
fastmug/scoring.py      metric catalogue, baselines, z-scores, verdict, recommendations
fastmug/report.py       Word report (python-docx) with charts from fastmug/charts.py
fastmug/mailer.py       SMTP sending with attachment
fastmug/ui/             PySide6 interface (custom-painted widgets, no web view)
tests/sim_harness.py    fast deterministic end-to-end run with the simulator
```

Data lives in `%APPDATA%\FAST-ug` (sessions, traces, snapshots, reports). Nothing leaves the
computer unless you press *Send*.

## Honest limits

* Reference priors are engineering starting values, not clinical norms. Replace them with your
  own recordings when you have them.
* Webcam timing (about 33 ms per frame) limits saccade precision; the personal baseline cancels
  the constant camera and display delay.
* Lip reading catches slurred or absent speech, not aphasia with fluent but wrong words.
* Not validated in microgravity.

## Licences

Barlow fonts: SIL Open Font License (assets/fonts/OFL.txt). MediaPipe models: Apache 2.0.
