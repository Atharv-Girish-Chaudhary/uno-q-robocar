# Robocar: a ball-pushing robot car with on-device AI

A robot car that finds a soccer ball with a vision model running on the robot itself, drives up
to it and pushes it toward a goal made of two yellow cones, with no cloud and no remote control. I
built its software for the Robocar track at Build Day with Qualcomm (October 24, 2026,
Northeastern University Silicon Valley), on an Arduino UNO Q. It took first place in the track,
with a 7.12 s run.

| At a glance | |
|---|---|
| Robot | Arduino UNO Q on a Hiwonder miniAuto chassis, with an ESP32-S3 camera streaming over Wi-Fi |
| Vision | An Edge Impulse FOMO model running on the board, about 6 ms a picture |
| Control | Python rules: one short motor pulse per fresh picture, every pulse 1 to 1000 ms |
| Result | First place in the Robocar track, with a 7.12 s run |
| Tests | 153, passing on Python 3.10 and 3.13 |

## The problem

The track asked one question, in the event page's words: "Which robocar can identify the goal and
score first?" Every team got the same kit and one day to make it drive itself; building ran from
10 AM to 4 PM, then the judges watched runs. Code written beforehand was allowed (I asked at
check-in), so I wrote and tested the detector, the camera reader and the decision logic on a
laptop in the two days before, against a fake camera and a synthetic field video. The day itself
went to the real robot: training the model, tuning, and floor runs.

The field was gray carpet, a small white soccer ball with black spots that looks cream in the
room's light, and a goal made of two yellow cones with a gap between them. A few facts about the
kit shaped the design:

- The camera is a separate board with its own Wi-Fi network, streaming 320 by 240 MJPEG (a video
  made of separate JPEG pictures). Every kit's camera uses the same Wi-Fi channel, and ten of them
  shared the room, so during the floor runs video arrived at about 2 pictures a second, with
  stalls of 1.5 to 2.5 s.
- The motor firmware reads a move's duration of 0 as "drive forever".
- The board's Python runs inside the container of Arduino App Lab (the tool that builds and runs
  apps on the board), with Python 3.13, numpy and OpenCV already installed. The camera's network
  has no Internet, so the code uses numpy and OpenCV and nothing else.

## How it works

The UNO Q holds two computers. The camera's video goes over Wi-Fi to the Linux side, a Qualcomm
chip, where the Python code finds the ball and picks a move. Bridge, Arduino's link between the
two, hands the move to the microcontroller, which runs the four mecanum wheels (wheels with angled
rollers, so the car can also slide sideways) and stops them on time. A BOOT button on the camera
starts and stops a run.

![The UNO Q's two computers: Python on the Linux side picks each move, the microcontroller runs the wheels and stops them on time, and Bridge carries moves between them](figs/robot-two-computers.svg)

Each pass of the loop takes the newest picture, finds the ball and the goal, picks one move and
sends it as one short pulse, then waits for new pictures that show where the move left it. Any
doubt, such as old video, a lost ball or an error, stops the run.

![One pass of the loop: look, find, decide, move, then wait for a fresh picture; any doubt stops the run](figs/run-loop.svg)

The code is in `prep/`:

| File | What it does |
|---|---|
| `stream.py` | Reads the camera's stream on a background thread and keeps only the newest picture, so the robot never works through a backlog. It flags a stall when no new picture comes for 3 s or the same one repeats 5 times. |
| `model_runner.py` | Runs the trained Edge Impulse model, an `.eim` file that is itself a small Linux program, and talks to it over a socket with only the standard library and numpy. The ball is the model's most confident ball box; the goal is the midpoint of its two most confident cone boxes, and one cone alone counts as no goal. |
| `detector.py` | The backup finder: color ranges in HSV (hue, saturation and value, where saturation is how strong a color is) plus shape checks for a round ball and a pair of cones. `tune.py` sets the ranges with sliders on live or recorded video. |
| `controller.py` | The decision rules as pure logic, with no hardware and no clock: 14 rules checked in order, and every move comes back with a plain reason. |
| `runloop.py` | Look, decide, move, wait. It also has a watch-only mode that prints what the robot would do, and a mode that measures the camera's delay. |
| `robocar_main_template.py` | The event guide's starter `main.py`, wired to the files above: one run per BOOT press. |
| `robocar_config.json` | Every threshold, speed and timing, so tuning on the day never meant editing code. |

Each decision prints one line in the app's log, with what the camera saw and why the robot moved,
such as `forward speed=110 ms=200: ball centered and far: approach`. Those lines are how every run
was read afterwards.

Safety lives in the same numbers. Every pulse is 1 to 1000 ms, checked when the settings load and
again before each `drive()` call, so a duration of 0 never goes out, and the firmware's own timed
stop ends each pulse even if Python dies. A run ends by itself after 45 s, after 8 pushes, or after
5 pictures in a row without the ball. Any error stops the motors and ends the run without crashing
the app, so the next BOOT press starts clean.

The robot acts only on a picture that arrived at least 120 ms after its last move ended, and only
once at least 2 new pictures have come in. With video at about 2 pictures a second that makes it
slow, one move every 1.5 to 2 s, but it never steers by a picture of where it used to be.

### The model

Edge Impulse, a web service for training small models that run on devices, trained a FOMO
detector (MobileNetV2 0.35, 96 by 96 pixel input). FOMO, short for "Faster Objects, More
Objects", marks where each object's center sits on a coarse grid instead of drawing a box around
it. Position is all the rules need, and it is fast on the board: about 6 ms a picture (3 to 9 ms
as measured on the board through `model_runner.py`).

It learned from the organizers' 353 photos of the room (281 for training, 72 for testing), labelled
`soccerball` and `goal`, with one box per cone. A check before training downloaded every picture
through Edge Impulse's public API, measured the color inside each box (the cones are a strong yellow
and the ball is not) and looked at each flagged picture by eye. It found about 50 labelling
mistakes, among them 20 pictures with a cone labelled as the ball, which would teach the model that
cones are balls. The organizers fixed most of them, and the model trained on the fixed set scored an
F1 of 96.9% on 57 pictures held back from training (goal 98%, ball 96.4%). F1 balances how many of
the model's detections were right against how many of the real objects it found. The separate test
set's score was not recorded. [docs/EDGE_IMPULSE.md](docs/EDGE_IMPULSE.md) has the settings and the
full check.

### Built and tested before the robot

`demo.py` runs the whole loop with pretend motors, on a video file or a webcam. `tools/` draws a
synthetic field video and holds a fake camera that serves it as a stream, plus a stand-in for the
Edge Impulse model, so the model runner was tested before a real model existed. Two notebooks show
what the detector sees and how the robot decides, and each one checks itself against the real code.
153 tests pass on Python 3.10 and on 3.13, the board's version, including a run of the starter
template against the guide's real `robot_client.py` with a fake Bridge, and both notebooks top to
bottom.

## Results

The robot took first place in the Robocar track, with a 7.12 s run. The app's log, read afterwards,
shows the run that was most likely the judged one: two far moves and a near move to the ball,
pushes at 4.4 s and 5.9 s, then two more moves after the ball as it rolled off to the right, until
it left the picture at 10.4 s. A goal at 7.12 s fits between the second push and the ball leaving
the picture, though the log can't show the goal itself.

The winning run used bigger moves, set at 4:51 PM: each forward move got about 4 times the distance
(double the speed for double the time), and each push about 2.5 times, its speed reaching the top
value of 255. Bigger moves are faster and harder to control. The first run with them lost the ball
after 2 pushes, since each big move near the ball made it drop out of view, while the best run at
the old sizes drove to the ball and kept it against the front for all 8 pushes, ending on its push
limit at 23.1 s.

Over the day there were more than 20 floor runs, each logged with what it showed and what changed
after it: see the [runs table](docs/CALIBRATION_LOG.md) and the [time-stamped log](docs/NOTES.md).
The app was handed in at 3:45 PM, before the 4:00 PM deadline, as a ZIP in the organizers'
submissions repo ([pull request 8](https://github.com/aaishikasb/uno-q-hackout-submissions/pull/8)),
and a check right after showed that App Lab's own import accepts that same ZIP.

## Limits, and what caused them

### The robot never saw the goal

The model missed the cones, and the color backup would have missed them too, each for its own
measured reason. So every push went straight ahead "as if lined up", in the log's words, and the
robot had to start lined up with the gap.

The model learned the cones from the organizers' photos, taken from above, where each cone is a
round, deep-yellow disc. The robot's camera sits low and sees pale yellow triangles from the side.
On a recording with both cones in plain view, each about 30 px wide, the model returned the ball
and no cone box at all. Size was ruled out: after the model's resize the cones are about 12 px
wide, as in its training photos.

The color backup's yellow range came from the same photos, where the cones measure saturation 245
on OpenCV's 0 to 255 scale, so it accepted 200 and up. This camera shows them at about 90 (80 to
108). A range refit on the robot's own recording (hue 20 to 36, saturation from 65, brightness from
100) found both cones in all 29 frames that show them and in none of the other 76. It came after
the hand-in and never ran on the robot, and it needs a small code change as well: with the model
switched on, the color finder doesn't run at all.

Both failures are domain shift: the pictures a model, or a hand-set threshold, meets in use differ
from the ones it was built from.

### A blind spot right in front

The camera can't see the ground right against the robot's front. In a ball-only run, after the
second push the ball stayed against the robot, below the bottom of the picture, and the rule "ball
gone after a push means finished" ended the run at 12.9 s with the ball still there. The planned fix
is a rule: when the ball vanishes right after a close, centered push, push again up to twice before
calling it gone.

### Sideways slides barely move it on carpet

Slides were meant to re-center the ball without turning away from the goal. On this carpet they
barely moved the robot: in one run, 12 slides in a row over 15 s left the ball 70 to 90 px left of
center until it was lost. At 4:06 PM steering switched to turning in place, with a wider center
band (40 px instead of 24).

### App restarts sometimes silenced the motor chip

Five times during the day, restarting the app left the microcontroller silent: the first Bridge
call, `stop`, timed out after 10 s. Each time only a board reboot brought it back. Starting the app
with `--no-prepare`, which skips recompiling the motor code and resetting the chip, worked 4 times
out of 6. The root cause is still open. Separately, after a flat battery and a battery swap, the
chip couldn't read the BOOT button or the line sensor over I2C (a two-wire bus) until another
reboot.

### Smaller limits

The video's 2 pictures a second set the pace, so a move came only every 1.5 to 2 s. Balls far away
near the top of the picture, probably other teams', pulled the robot sideways in 4 of 5 runs in
one stretch. The model sees only the middle 240 of the camera's 320 columns. The pulse sizes were
never measured in centimeters, and the camera's delay was never measured with the latency mode.

## What I would do next

- Retrain the model on the robot's own pictures, with cones seen from the side in this camera's
  colors, and measure it on robot frames before and after: a small, real experiment on domain
  shift.
- Take the ball from the model and the goal from the refit color range, with the small code change
  that lets both finders run.
- Push again when the ball sits in the blind spot, instead of calling the run finished.
- Ignore far balls by taking the one lowest in the picture, which is the nearest.
- Use the big moves only while the ball is far.
- Measure the camera's delay with the latency mode, and find why restarts silence the motor chip.

## Run it

From `prep/`, with [uv](https://docs.astral.sh/uv/) (a Python project manager) installed. The
tests, on the project's Python 3.10:

```bash
uv run pytest
```

The same tests on Python 3.13, in a throwaway environment:

```bash
uv run --isolated --python 3.13 pytest
```

A dry run of the whole loop on a synthetic field video, then the color tuner on it:

```bash
uv run python tools/make_synthetic_video.py
```

```bash
uv run python demo.py --source samples/synthetic_field.avi
```

```bash
uv run python tune.py --source samples/synthetic_field.avi --loop
```

Two of the tests need the organizers' guide cloned into `upstream/`
(`git clone https://github.com/aaishikasb/uno-q-hackout upstream`); without it they are skipped.
To run it on the robot, follow "How to run it" in [the hand-in README](docs/SUBMISSION_README.md).
The trained model is not in the repo, and [docs/EDGE_IMPULSE.md](docs/EDGE_IMPULSE.md) says how to
train one. The repo's `robocar_config.json` starts on the color finder (`"detector": "color"`);
the board ran the model (`"detector": "model"`).

## Where things are

- `prep/`: the code, its tests, the notebooks and the laptop tools, as a uv project on Python 3.10.
- [docs/NOTES.md](docs/NOTES.md): the day's time-stamped log, then the reference notes for the
  board.
- [docs/CALIBRATION_LOG.md](docs/CALIBRATION_LOG.md): every floor run in one table.
- [docs/EDGE_IMPULSE.md](docs/EDGE_IMPULSE.md): the model, its training settings and the dataset
  check.
- [docs/SPEC.md](docs/SPEC.md): the design: the constraints, the settings file, each module and the
  tests.
- [docs/SUBMISSION_README.md](docs/SUBMISSION_README.md): the README handed in with the app.
- [docs/REPO_GUIDE.md](docs/REPO_GUIDE.md): a file-by-file guide to this repo and to the
  organizers' event guide, including what the guide's own docs leave out.
- `GAME_PLAN.html`: the plan page used on the day. Open it in a browser, since GitHub shows HTML as
  code.
- `figs/`: the diagrams, as SVG files.

## Credits

The event guide and its starter code (the starter `main.py`, `robot_client.py`, the motor sketch
and the camera firmware): [aaishikasb/uno-q-hackout](https://github.com/aaishikasb/uno-q-hackout).
The Arduino UNO Q and App Lab: Arduino. The miniAuto chassis and camera: Hiwonder. Model training:
Edge Impulse, on the organizers' public project 1144501. OpenCV and numpy.
