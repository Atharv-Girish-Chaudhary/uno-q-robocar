# Build Day prep: spec

Approved 2026-10-22. Source of truth for every robot fact here is `upstream/`
(github.com/aaishikasb/uno-q-hackout) at commit `8f40c4e` of 2026-10-20, rechecked at `1fc4493` of
2026-10-22, which only adds a pre-work page and a new setup link. Facts about the
board's software come from Arduino's own source (app-bricks-py at `bricks/0.13.1`, PR 458), and
facts about the field come from the organizers' August event, the Robot Soccer Cup
(github.com/aaishikasb/qc-robot-soccer-cup and Edge Impulse project 1085406).

## Goal

Arrive at Build Day with Qualcomm (Sat Oct 24, 2026, Robocar track) with the detector, the
camera reader and the decision logic already written and tested on the laptop, so the day goes to
calibration, tuning and the scored runs. Nothing here needs the robot until Saturday.

## What the field probably looks like

The event page says the robocar track uses the Robot Soccer Cup resources. That August event had
a green floor, dark walls with red tape on one side and blue on the other, a small white goal
with a net against an end wall, and a black and white soccer ball. Its teams found the ball with
Edge Impulse models, and used HSV color only for the wall tape. Build Day's mission, from its
event page: "Which robocar can identify the goal and score first?"

So the color detector defaults to a white ball on the floor below the wall, and a model runner
lets a trained Edge Impulse model replace it on the day without touching anything else.

## Layout

```
qualcomm-build-day/
  .gitignore                 upstream/, venvs, generated samples, recordings and models
  README.md                  what is here and the commands that matter
  CLAUDE.md                  this repo's rules for future Claude sessions
  upstream/                  separate clone of the guide, read only, never in this history
  docs/
    SPEC.md                  this file
    NOTES.md  RUBRIC_PLAN.md  QUESTIONS.md  CHECKLIST.md  CALIBRATION_LOG.md
    SUBMISSION_README_TEMPLATE.md  EDGE_IMPULSE.md
  prep/                      uv project, Python 3.10
    pyproject.toml  uv.lock  .python-version
    requirements-board.txt   fallback only, see below
    robocar_config.json      every tunable number
    detector_presets.json    starting color ranges (white ball, red ball, white goal, tapes)
    detector.py  model_runner.py  stream.py  controller.py  runloop.py
    tune.py  demo.py  robocar_main_template.py
    tools/make_synthetic_video.py  tools/fake_camera.py  tools/fake_eim.py
    tests/
```

## Constraints

- Code runs on Python 3.10 and newer: no `tomllib`, `ExceptionGroup`, `typing.Self`, `StrEnum`
  or `datetime.UTC`. The dev venv is pinned to 3.10; the tests also run on 3.13, which is what
  the App Lab container runs.
- Runtime dependencies are numpy and OpenCV only; the model runner uses the standard library
  and numpy. pytest is a dev dependency.
- The dev venv has `opencv-python` 4.13 (GUI build, for `tune.py` and `demo.py --show`), matching
  the board's OpenCV 4.13. A test fails if `opencv-python` and `opencv-python-headless` are both
  installed in one environment.
- The board needs no Python installs: Arduino's App Lab image already has numpy and its own
  `opencv-python-headless` 4.13 build, pinned through `UV_CONSTRAINT`. On images up to
  `bricks/0.13.1`, listing `opencv-python-headless` in the app's `requirements.txt` makes the
  install fail (fixed in PR 458 on Sep 30). So the app gets no `requirements.txt`.
  `requirements-board.txt` (exact pins, `--only-binary=:all:`) is the fallback for when
  `import cv2` fails on the board.
- Modules are flat files so they can sit beside `main.py` in the app's `python/` folder.
- All thresholds, speeds and timings live in `robocar_config.json`.
- One clock everywhere: `time.monotonic()` seconds.
- Nothing in `prep/` sends motor commands except `robocar_main_template.py`, which only runs on
  the board.

## robocar_config.json

Sections, each loaded into a validated dataclass whose `from_dict` raises `ValueError` on a bad
value. Speeds and pulse lengths are placeholders until calibration.

- `run`: `mode` (`attempt`, `observe` or `latency`), `detector` (`color` or `model`), and the
  latency check's direction, speed and pulse length.
- `ball` and `goal`: color detector settings. `hsv_ranges` (OpenCV HSV, H 0 to 179; red needs
  two ranges because its hue wraps around 0), `roi_top_frac` and `roi_bottom_frac` (the rows to
  search), `blur_ksize`, `open_ksize`, `close_ksize`, `min_area_px`, `max_area_frac`, and a
  `shape`. A `round` shape (the ball) needs `min_fill_ratio` and, above
  `circularity_min_radius_px`, `min_circularity`. A `box` shape (the goal) needs an aspect ratio
  between `min_aspect` and `max_aspect` and a `min_fill_ratio` against its bounding box.
- `model`: the `.eim` path, `ball_labels` (`soccerball` from the guide, `soccer_ball` from the
  August dataset), `goal_labels`, `min_confidence`, and start and call timeouts.
- `stream`: `url`, `connect_timeout_s`, `read_timeout_s`, `stale_after_ms` (also the oldest frame
  the controller acts on), `max_identical_frames`, `reconnect_delay_s`, `skip_after_connect`
  (frames dropped after each connect, since the camera's two buffers may hold old pictures), and
  `loop_files`.
- `controller`: see the rules below. Pulse lengths must be 1 to `max_pulse_ms` ms, and
  `max_pulse_ms` itself is capped at 1000 in code, well under the firmware's 5000; config load
  enforces both.

## Modules

### detector.py

`ColorDetector(DetectorConfig)` with `detect(image_bgr, timestamp) -> Detection` and
`analyze(...) -> (Detection, mask)` for the tuner. Steps: blur, HSV, `inRange` per range ORed
together, zero the rows outside the search band, open then close with an elliptical kernel, find
external contours, keep candidates that pass size and shape, and pick the best quality times
area.

For a round shape, fill ratio is the blob's pixel count over the pixel count of its minimum
enclosing circle clipped to the frame, so a ball cut by the bottom edge still scores near 1, and
a box scores about 0.64 and is rejected by the 0.75 floor. Circularity (4πA/P²) is checked only
above `circularity_min_radius_px`, because tiny far balls are too pixelated for it, and it is
measured on the convex hull, because a black patch on a soccer ball's outline cuts a notch that
would otherwise sink the score. Quality is fill times circularity (fill alone for tiny blobs).

The ball's search band must start below the goal's base. JPEG works in 8 by 8 pixel blocks, so
the white goal's bottom bar smears brightness to the end of its block row, and the morphology
then bridges that smear to a far ball just below it. On the synthetic field the band starts at
0.57 of the frame height, the first block row below the goal; on the real field it is set with
`tune.py`.

`Detection` fields: `found`, `x`, `y`, `radius` (apparent, px), `width`, `height`, `quality`
(0 to 1), `timestamp`, `touches_bottom`, `candidates`. `ColorVision(ball_cfg, goal_cfg)` runs one
detector for each and returns a `Sighting(ball, goal, width, height)`.

### model_runner.py

`ModelVision(ModelConfig)` runs an Edge Impulse `.eim` model with only the standard library and
numpy, using the protocol of Edge Impulse's own Python SDK: start `model.eim SOCKET_PATH`, connect
a Unix socket, send JSON messages with an `id`, read replies that end in a zero byte, `hello`
first for the input size, channel count and resize mode, then `classify` with pixels packed as
`(R << 16) + (G << 8) + B` after the same resize (`squash`, `fit-shortest` or `fit-longest`).
Bounding boxes come back in the model's input pixels and are mapped back to the frame. It
returns the same `Sighting` as `ColorVision`. FOMO models give centers, not sizes, which is why
the controller can also judge closeness from the ball's height in the frame.

### stream.py

`open_stream(source, StreamConfig)`: an `http://` URL gives an `MjpegStream`, a webcam index or
a video file gives a `CaptureStream`, a recording folder gives a `FolderStream`. Each runs a
daemon thread that keeps only the newest frame, its arrival time and a sequence number.

Consumer API: `latest()`, `latest_seq()`, `wait_for_frame(newer_than, min_seq, timeout_s)`,
`status(now)` (ok flag, reason, frame age, counts), `close()`; usable as a context manager.

`MjpegStream` connects with `http.client` and `connect_timeout_s`, sets `read_timeout_s` on the
socket right after connecting, and reads with `read1()` so a frame is handed over as soon as it
arrives (a plain `read(n)` would hold each frame until the next one comes). The camera answers
with HTTP chunked encoding, which `http.client` decodes; the multipart parsing is ours
(`MjpegParser.feed(bytes) -> list[jpeg]`): boundary from the Content-Type header,
`Content-Length` when present, a boundary scan otherwise, and an SOI/EOI check that drops broken
JPEGs. A payload byte-identical to the previous one is not a new frame. On any error the reader
records the reason, waits `reconnect_delay_s` and reconnects. `close()` shuts the socket down so
a blocked read returns at once. JPEG decoding happens in the consumer, only for frames it uses.

### controller.py

Pure decision logic: no I/O, no clock calls, no hardware. `decide(obs, state, cfg, now) ->
(Decision, RunState)`, `new_run(now)`, `record_move_end(state, t, seq)`. Every `Decision`
carries an action, the `drive()` direction, speed and ms, and a readable reason.

"Close" means radius at least `close_radius_px`, or the ball's center below `close_y_frac` of
the frame height, or touching the bottom edge with radius at least `slow_radius_px`. "Near" (the
slow approach) means radius at least `slow_radius_px` or center below `slow_y_frac`.

| # | Observation | Decision |
|---|---|---|
| 1 | Stream reports a problem: no new frame for `stale_after_ms`, identical frames, or a reader error | STOP |
| 2 | No frame, or the newest frame is older than `stale_after_ms` | STOP |
| 3 | Run longer than `run_time_limit_s` | DONE |
| 4 | Frame arrived less than `settle_ms` after the last pulse, or fewer than `min_new_frames` new frames since it | WAIT |
| 5 | Ball missing, fewer than `miss_frames_to_end` frames in a row | WAIT |
| 6 | Ball missing `miss_frames_to_end` frames in a row | STOP "ball lost", or DONE "ball gone after a push" |
| 7 | `max_pushes` already done | DONE |
| 8 | Not close, ball outside the center band | STEER toward it with `steer_mode` |
| 9 | Not close, centered | FORWARD, slow pulse when near |
| 10 | Close, goal seen, ball outside the band | ROTATE toward the ball |
| 11 | Close, goal seen more than `goal_band_px` from the ball | ORBIT: strafe away from the goal's side |
| 12 | Close, goal seen behind the ball | PUSH |
| 13 | Close, goal not seen, ball outside the band | STEER toward it with `steer_mode` |
| 14 | Close, goal not seen, centered | PUSH, as if the goal were lined up |

Steering pulses grow from `steer_ms_min` at the band edge to `steer_ms_max` at the frame edge.
When close, rotation centers the ball without changing where the goal sits relative to it, and a
sideways step changes that relation: a near ball shifts more in the picture than the far goal,
so stepping right moves a goal that sits left of the ball toward the ball's line. STOP and DONE
both end the run; they differ only in the reason.

### runloop.py

`load_settings(path)`, `make_vision(settings)`, `open_camera(settings)`, `print_versions()`, and
the three modes, all taking any robot with `is_running()`, `drive(direction, speed, ms)` and
`stop()`:

- `run_attempt`: each pass checks `robot.is_running()`, waits for a fresh frame (newer than the
  last one, `settle_ms` past the last pulse and at least `min_new_frames` after it, checking the
  stream's health every 50 ms so a frozen camera ends the wait within `stale_after_ms`), observes,
  decides, logs one line, then calls `robot.stop()` on STOP or DONE, `robot.drive(...)` on a
  move, nothing on WAIT. Any exception is logged and followed by `robot.stop()` in its own guard,
  and the function returns, because App Lab's `App.run` shuts the whole app down when an error
  escapes the loop. Types in `passthrough` (the board's `ProgramStopped`) are re-raised so
  `run_program` reports a BOOT press as usual. A second guard refuses any pulse outside 1 to
  `max_pulse_ms` ms.
- `observe_only`: the guide's step 5. It never calls `drive()`, prints each sighting with the
  decision it would make, and runs until BOOT or the time limit.
- `measure_latency`: one short pulse with the wheels on the floor, then a log of how much each
  new frame differs from the one before, with arrival times, to set `settle_ms` from evidence.

### robocar_main_template.py

Reference only, never copied into `upstream/`. It is the guide's `main.py` with `motion_check()`
calling `runloop.run_mode(...)`: same imports, same startup `robot.stop()`, health and sensor
prints, the same `App.run(user_loop=lambda: robot.run_program(...))` and `finally:
robot.stop()`. It loads `robocar_config.json` from its own folder, prints the Python, numpy and
OpenCV versions, and opens the camera once at startup so frames are flowing when BOOT is
pressed.

### demo.py

`uv run python demo.py --source SOURCE [--config FILE] [--mode attempt|observe] [--detector
color|model] [--show] [--save-dir DIR] [--record DIR] [--once]`. It runs the same `runloop`
functions with a `DryRobot` that sends nothing: `drive()` prints the move and sleeps for the
pulse like the real `drive()`, so frames during a pulse are skipped as on the robot. After a run
ends it starts another after a short pause, as if BOOT were pressed again, unless `--once`.
`--record` saves raw frames with their arrival times for replay and tuning.

### tune.py

`uv run python tune.py --source SOURCE [--target ball|goal] [--preset NAME]`. Trackbars for two
HSV ranges (the second can be switched off), the search band, kernel sizes, minimum area and the
shape limits. Clicking the frame prints the HSV under the cursor. `s` saves that target's section
only (atomic write, other sections kept), `r` reloads, `p` pauses, `q` quits.

### tools

- `make_synthetic_video.py`: a 320×240, 15 fps MJPG AVI of the August field: room wall, dark
  field wall with blue tape, green floor, a white goal with a net, and a black and white ball in
  scripted scenes (left, centered and far, approaching, close with the goal behind, close with the
  goal off to one side, hidden, a white box with no ball, right). A JSON sidecar records the true
  positions per frame.
- `fake_camera.py`: serves a video, image folder or recording at `/stream` in the ESP32
  firmware's exact format (same boundary, part headers and chunked encoding), one client at a
  time like the real camera. Flags make it stall, repeat one JPEG, or drop the connection.
- `fake_eim.py`: a stand-in for an Edge Impulse model that speaks the same socket protocol and
  reports the brightest round blob as `soccerball`, so the runner is tested before a real model
  exists.

## Tests (pytest)

- Detector, on synthetic images saved through JPEG quality 80 like the camera: a ball is found
  within max(2 px, 10%) left, center and right, small to large, down to about 5 px radius; an
  empty floor is not found; a white box and a white bar are rejected; a ball cut by the bottom
  edge is still found; the room wall above the search band is ignored; a red ball near the hue
  wrap is found only with both ranges; the goal detector finds the goal and not the ball; bad
  config values raise.
- Model runner, against `fake_eim.py`: the handshake, the resize modes and the mapping of boxes
  back to frame pixels, plus a clean stop.
- Stream: the parser on the firmware's framing in random splits, one byte at a time, without
  `Content-Length`, with garbage first and with a broken JPEG; then live against
  `fake_camera.py`: newest frame wins, a stall is reported within `stale_after_ms` plus a margin,
  repeats are reported, a read timeout leads to a reconnect, and `close()` returns quickly.
- Controller: one table-driven test with a row per rule, config validation, and a sweep proving
  no moving decision ever has a pulse outside 1 to `max_pulse_ms`.
- Run loop and template, with a fake robot, fake camera and fake clock: stop on a lost ball, a
  stale feed and an exception; short bounded pulses only; `is_running()` on every pass; a BOOT
  press mid-run exits without another pulse; the template's wiring with the guide's real
  `robot_client.py` over a fake Bridge.
- End to end: the run loop over the synthetic video with a fake clock gives the expected
  decisions per scene.
- Environment: exactly one OpenCV distribution is installed.

## Assumptions the guide does not settle

- That Build Day uses the August ball, goal and field. Ask at check-in.
- Which App Lab image the boards run; the startup version print settles whether OpenCV imports.
- That the App Lab container reaches `192.168.5.1` once UNO Q Linux joins the camera network.
- Camera latency and frame rate: unmeasured; `measure_latency` measures them on the day.
- The camera faces forward unmirrored (the firmware sets `hmirror` and `vflip` to 0);
  `invert_steering` exists in case it does not.
- Rotation is weaker than straight driving at the same speed value: the sketch halves the wheel
  mix whenever rotation is involved, about 70% of a straight pulse's wheel output, so rotation
  has its own speed setting.

## Out of scope

- A trained model: the user trains it with their own Edge Impulse account.
- Any change to `upstream/`, and a ready-to-import app ZIP, until the rules on pre-written code
  are known. `NOTES.md` lists the copy steps instead.
- An ultrasonic "path clear" check: the ball itself trips the sensor when close.
- A GitHub remote or any push.
