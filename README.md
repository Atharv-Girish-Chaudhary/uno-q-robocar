# Build Day prep: Robocar track

Prep for Build Day with Qualcomm (Saturday, Oct 24, 2026, Northeastern University Silicon Valley,
the venue). The robot finds a ball, drives to it and pushes it toward the goal. This repo
holds the detector, the camera reader and the decision logic, written and tested on a laptop
before the robot exists, plus the notes and templates for the day.

## Layout

- `docs/`: `NOTES.md` (the quick reference), `RUBRIC_PLAN.md`, `QUESTIONS.md`, `CHECKLIST.md`,
  `CALIBRATION_LOG.md`, `SUBMISSION_README_TEMPLATE.md`, `EDGE_IMPULSE.md`, and `SPEC.md` (the
  design).
- `prep/`: the code, a uv project on Python 3.10.
  - `detector.py` finds the ball and the goal by color and shape; `model_runner.py` runs a
    trained Edge Impulse model instead.
  - `stream.py` reads the camera, keeping only the newest frame, and notices stalls.
  - `controller.py` picks each move; `runloop.py` repeats look, decide, move.
  - `robocar_main_template.py` shows the guide's `main.py` wired to these; reference only.
  - `demo.py` dry-runs the whole loop on a laptop; `tune.py` tunes colors with sliders.
  - `tools/`: a synthetic field video, a fake camera, and a stand-in Edge Impulse model.
  - `robocar_config.json` holds every number.
- `upstream/`: a read-only copy of the event guide, kept out of this repo's history. Get it with
  `git clone https://github.com/aaishikasb/uno-q-hackout upstream`.

## Commands (from `prep/`)

```bash
uv run pytest
```

```bash
uv run python tools/make_synthetic_video.py
```

```bash
uv run python demo.py --source samples/synthetic_field.avi
```

```bash
uv run python demo.py --source 0 --show
```

```bash
uv run python tune.py --source samples/synthetic_field.avi --loop
```

`docs/NOTES.md` has the board commands, the fake camera, recording, and how to move the code into
the robot's app on the day.
