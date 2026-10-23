# Build Day notes

The quick reference for Saturday. It condenses the event guide (`upstream/README.md` and
`upstream/robocar/README.md`, commit `8f40c4e`), Arduino's App Lab source (app-bricks-py at
`bricks/0.13.1`), and the organizers' August event, the Robot Soccer Cup. Read the guide itself
once end to end; come back here for the details.

## The kit

- An Arduino UNO Q on a Hiwonder miniAuto chassis, preassembled. Its mecanum wheels can drive,
  slide sideways and turn in place.
- An ESP32-S3 camera (GC2145 sensor) with its own Wi-Fi network and no Internet. It streams
  320 × 240 MJPEG at `http://192.168.5.1:81/stream`, with a preview page at
  `http://192.168.5.1:81/`. The network name is unique per robot,
  and the password comes with the robot.
- An ultrasonic distance sensor (I2C `0x77`), a four-channel line sensor (`0x78`), and the
  camera's BOOT button, read over I2C (`0x79`).
- The starter covers the motors (`sketch/sketch.ino`) and the camera firmware. You write the
  detector and the decision logic in `python/`.

## Setup, in order

1. Raise the wheels off the table, find the motor-power disconnect, and keep it within reach.
2. Plug the UNO Q in with a USB-C cable that carries data, and follow App Lab's quickstart.
3. Collect the camera's Wi-Fi name and password, and the robot's motor calibration, from the
   organizers. Find the BOOT button on the camera.
4. While the board still has Internet, run the starter once: import the prepared ZIP in App Lab
   (My Apps, then import), or `make flash` from a copy of `robocar/`. The first run downloads and
   compiles the sketch's Arduino libraries. Press BOOT: one 200 ms forward pulse, then a stop.
5. On the laptop, join the camera's Wi-Fi and open the preview page. Put the ball near, far, left
   and right to find a good camera angle. Close the page afterwards: the camera serves one
   stream at a time.
6. On the board, join the camera's Wi-Fi from its Linux side, with USB still connected:
   `adb shell`, then `sudo nmcli device wifi connect "SSID" password "PASS"`. The board saves the
   network and rejoins it after a reboot; `nmcli device wifi list` shows what is in range.
7. Check the stream from the app with the snippet in step 3 of the robocar guide.

## How a run works

- The app starts with the robot still, and prints the board's health and sensors.
- A short BOOT press starts a red, yellow, green countdown of about 1.2 seconds, then enables the
  program. `run_program` runs your routine once per press.
- `robot.stop()` stops the motors and ends the run; another BOOT press starts the next one.
  Pressing BOOT during a run disables the program, and the next `drive()` raises
  `ProgramStopped`, which `run_program` catches and reports.
- `robot.drive("stop", speed=0, ms=100)` stops the motors but keeps the run going.
- Keep the starter's `robot.run_program(...)`, its startup `robot.stop()` and its `finally`
  block; they provide this lifecycle.
- Holding BOOT for five seconds flips `hold_toggle`, which the track does not use.

## Driver API (`python/robot_client.py`)

| Call | What it does |
|---|---|
| `drive(direction, speed=150, ms=500)` | One timed move. Needs an enabled program, waits `ms / 1000 + 0.1` s, then checks the run state again |
| `stop()` | Stops the motors, turns obstacle avoidance off, and ends the run |
| `is_running()` | Reads `program_enabled`. Check it in any loop that doesn't call `drive()` |
| `read_sensors()` | JSON: `ultrasonic_mm` and `ultrasonic_cm` (`-1` means unknown), `battery_mv`, line bits, `program_enabled` |
| `drive_raw(m0, m1, m2, m3, ms=500)` | Sets each motor directly and returns at once, without the wait |
| `health()`, `led(on)`, `buzz()`, `servo(angle)` | Board identity, lights, beeper, and the gripper if fitted |

- Directions: `forward`, `backward`, `left` and `right` (sideways slides), `rotate_left`,
  `rotate_right`, `stop`. An unknown name makes no move and reports no error.
- Limits in the firmware: speed 0 to 255, raw motor values -255 to 255, duration 0 to 5000 ms.
  Duration 0 means continuous motion.
- At the same speed number, turning in place drives the wheels at about 70% of the power of a
  straight drive or a slide, because the sketch halves the wheel mix whenever rotation is
  involved. That is why `rotate_speed` (160) is higher than `strafe_speed` (120).
- Bridge calls give up after 10 seconds by default and raise `TimeoutError` (Arduino's
  `bridge.py`).

## Safety rules

- Duration 0 means "drive forever". Every pulse in the prep code is 1 to 1000 ms, enforced when
  the config loads and again before each `drive()`.
- BOOT is a software stop, and blocking firmware routines can delay it. The motor-power
  disconnect is the real stop.
- Never rely on a Python `finally` as the only stop: if the process dies it never runs. The
  firmware's timed stop at the end of each pulse is the backstop.
- `stop` or `x` in the serial monitor stops the motors but does not end the Python program,
  which can send another move.
- The serial motor tests (`1` to `4`, `dir_sweep`, `dir_scan`, `combo_scan`, `pwm_combo`) move the
  wheels and some freeze the main loop: supervised and with the wheels raised only.
- Never turn on the old obstacle demo (`F|1|&`): a failed distance reading makes it drive forward.
- Only one App Lab app runs at a time.

## Python on the board (verified in Arduino's source)

- App Lab runs the app's Python in a container built on `python:3.13-slim-trixie` (Debian 13).
  numpy and Arduino's own build of `opencv-python-headless` 4.13 are already installed, and the
  image pins that exact OpenCV build through `UV_CONSTRAINT`.
- `python/requirements.txt` is installed with `uv pip install` into `/app/.cache/.venv`, and only
  when the file changes. A failed install is retried at every start, and the app starts anyway.
- So this build ships no `requirements.txt`. Listing `opencv-python-headless` there breaks the
  install on images up to `bricks/0.13.1` (Sep 29); Arduino fixed it on Sep 30 (PR 458). The
  template prints the Python, numpy and OpenCV versions at startup, which settles it.
- If `import cv2` does fail on Saturday, `prep/requirements-board.txt` has exact pins with Linux
  ARM wheels for Python 3.10 to 3.13 (checked with `uv pip compile --python-platform
  aarch64-unknown-linux-gnu`). Add them while the board still has Internet.
- If an error escapes `App.run`'s loop, App Lab shuts the app down and BOOT does nothing until it
  is restarted. The prep loop catches every error, stops the motors and returns.
- The container sits on its own Docker network. If the camera answers from `adb shell` but not
  from the app, run `ip route` on the board and check that the camera's subnet is not hidden.

Offline wheels were not built, because this build needs no Python downloads. If a board ever
lacks OpenCV and the venue has no Internet, this downloads the Python 3.13 set (about 55 MB) on
the laptop; reference it in `requirements.txt` with `--no-index` and
`--find-links /app/python/wheels` (an absolute path, since relative ones depend on uv's version):

```bash
uvx pip download numpy==2.2.6 opencv-python-headless==4.13.0.92 -d wheels --only-binary=:all: --implementation cp --python-version 3.13 --abi cp313 --platform manylinux_2_28_aarch64 --platform manylinux2014_aarch64
```

## Moving the prep code into the app (only if pre-written code is allowed)

1. In your own copy of the robocar app (an imported ZIP in App Lab, or a copy of
   `upstream/robocar/` outside `upstream/`), put these files in `python/` beside `main.py`:
   `detector.py`, `model_runner.py`, `stream.py`, `controller.py`, `runloop.py`,
   `robocar_config.json`, and `models/robocar.eim` if you use a trained model.
2. Replace `main.py` with the contents of `prep/robocar_main_template.py`.
3. Don't add a `requirements.txt` (see above).
4. Start with `"mode": "observe"` in the config's `run` section, so the robot only watches and
   prints, then switch to `"attempt"`.

## Laptop commands (from `prep/`)

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
uv run python tools/fake_camera.py --source samples/synthetic_field.avi --loop
```

```bash
uv run python demo.py --source http://127.0.0.1:8081/stream
```

```bash
uv run python tune.py --source samples/synthetic_field.avi --loop
```

On the day, with the laptop on the camera's Wi-Fi and the board's app stopped, record real
footage for tuning and replay:

```bash
uv run python demo.py --source http://192.168.5.1:81/stream --mode observe --record recordings/run1
```

## Board commands (from a copy of `robocar/`)

| Command | What it does |
|---|---|
| `make devices` | List connected boards |
| `make flash` | Copy the app to the board, compile and upload the sketch, start Python |
| `make logs` | Follow Python output, including `print()` and errors (Ctrl+C leaves it running) |
| `make monitor` | The MCU serial monitor at 9600 baud |
| `make stop` | Stop this app (not a motor-power cutoff) |
| `make package` | Build `build/uno-q-robocar.zip` for App Lab import |

With several boards connected, add `SERIAL=...` from `make devices`. If another app is running:
`adb -d shell`, then `TMPDIR=/tmp arduino-app-cli app list` and `TMPDIR=/tmp arduino-app-cli app
stop APP_ID`. Your Mac's built-in `make` (GNU Make 3.81) runs this Makefile; tested on Oct 22.

## What the August event tells us

- Field: green floor, dark walls with red tape on one side and blue on the other, a small white
  goal with a net against an end wall, and a black and white soccer ball. Source: the organizers'
  public Edge Impulse dataset of 321 onboard-camera images, and their earlier repo.
- Its teams found the ball and goal with Edge Impulse models (FOMO, and in one case YOLO-Pro), and
  used HSV color only to tell the red side from the blue side.
- One team found that plain `cv2.VideoCapture` lagged by "tens of seconds" because old frames
  piled up; a background thread that keeps only the newest frame fixed it. `stream.py` does the
  same.
