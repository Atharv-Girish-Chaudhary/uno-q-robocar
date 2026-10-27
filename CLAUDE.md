# CLAUDE.md: qualcomm-build-day

My Robocar-track project from Build Day with Qualcomm (Sat Oct 24, 2026). The event is
over, and the repo is public on GitHub as uno-q-robocar. My global Claude Code rules still
apply; this file wins on a conflict. The design is in `docs/SPEC.md`.

- Code in `prep/` must run on Python 3.10, since that is the oldest Python allowed; the board's
  App Lab container runs 3.13. No 3.11+ features (`tomllib`, `ExceptionGroup`, `typing.Self`,
  `StrEnum`, `datetime.UTC`). Runtime dependencies are numpy and OpenCV only. The `notebooks`
  group (ipykernel, matplotlib, nbclient) is for the laptop, like `dev`; robot code never
  imports it.
- `uv run` recreates `prep/.venv`, with `opencv-python` (the GUI build). The board already ships
  `opencv-python-headless`. Never install both into one environment, and never list OpenCV in
  the App Lab app's `requirements.txt` (it breaks the install on board images up to
  `bricks/0.13.1`).
- Nothing in `prep/` sends motor commands except `robocar_main_template.py`, which only runs on
  the board. Every `drive()` pulse is 1 to `max_pulse_ms` ms, and `max_pulse_ms` is capped at 1000
  in `controller.py`; duration 0 means "drive forever" and is never allowed.
- Every threshold, speed and timing lives in `prep/robocar_config.json`, not in code.
- No em dashes or en dashes in any file.
- Run the tests from `prep/` with `uv run pytest`.
