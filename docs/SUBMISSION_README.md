# [PROJECT NAME]: Robocar track, Build Day with Qualcomm 2026

The robot finds a soccer ball with an Edge Impulse model running on the Arduino UNO Q, drives up
to it in short moves, each one decided from a fresh camera picture, and pushes it toward a goal
made of two yellow cones. The same model is meant to find the cones as well, but from the robot's
low camera it never did, so the robot starts out facing the goal and pushes straight ahead.

## Team

- [TEAM NAME]
- [TEAM MEMBER NAMES]

## Source

- Repository or ZIP: [REPOSITORY LINK OR ZIP FILE NAME]
- `python/main.py`: the button-started run, from the guide's starter (in the repository:
  `prep/robocar_main_template.py`)
- `python/detector.py`, `python/model_runner.py`: finding the ball and the goal, by color or with
  the Edge Impulse model
- `python/stream.py`: reading the camera, newest picture only, stall detection
- `python/controller.py`, `python/runloop.py`: the decision rules and the look, decide, move loop
- `python/robocar_config.json`: every threshold, speed and timing
- `python/models/robocar.eim`: the trained model. It is git-ignored, so download your own from
  Edge Impulse (see Detection).
- `sketch/`: the guide's motor sketch, unchanged

In the repository the Python files live in `prep/`, with their tests in `prep/tests/`.

## How to run it

1. In a copy of the guide's robocar app, put `detector.py`, `model_runner.py`, `stream.py`,
   `controller.py`, `runloop.py` and `robocar_config.json` in `python/` beside `main.py`, replace
   `main.py` with the contents of `prep/robocar_main_template.py`, and put the model at
   `python/models/robocar.eim`. In the config's `run` section set `"detector": "model"` and
   `"mode": "attempt"`. Don't add a `requirements.txt`: the board's App Lab image already has
   numpy and OpenCV, and listing OpenCV there breaks the install.
2. Start the app once from App Lab while the board still has Internet. The first start downloads
   and compiles the sketch's libraries.
3. Join the camera's Wi-Fi from the board's shell, using your robot's own network name and
   password: `sudo nmcli device wifi connect "SSID" password "PASSWORD"`. After anything that
   restarts the camera, such as a battery swap, run `nmcli con up "SSID"` to bring the video back.
4. After a change to Python or settings, restart with `arduino-app-cli app stop`, then
   `arduino-app-cli app start --no-prepare`. This skips compiling the sketch and resetting the
   motor chip; only a changed sketch needs the full start. If the log shows "Request 'stop' timed
   out after 10s", the motor chip has gone silent: run `sudo reboot` on the board, then start the
   app again. The log keeps an earlier failed start above the new one, so read the newest "App is
   starting" block.
5. Place the robot facing the goal, with the ball 50 cm to 1 m straight ahead and the two yellow
   cones behind the ball (in testing, about 2 m from the robot and a phone's length apart).
6. For a first test, raise the wheels, or set `"mode": "observe"` so the robot only watches and
   prints. Press the camera's BOOT button: after a red, yellow, green countdown of about 1.2 s
   the run starts. Press BOOT again to stop it. BOOT is only a software stop, so keep the
   motor-power switch within reach. Each decision prints in App Lab's log, with what the camera
   saw and why the robot moved.

## Camera settings

- Camera: Hiwonder ESP32-S3 (GC2145), 320 by 240 MJPEG at `http://192.168.5.1:81/stream`
- Network name: unique to each robot and supplied with it, along with the password (not listed
  here)
- Mounting and angle: the kit's camera as supplied, low on the chassis and facing forward,
  tilted down so the far edge of the carpet sits about 30% of the way down the picture
- Reader settings (the config's `stream` section): newest picture only, `read_timeout_s` 4.0,
  `stale_after_ms` 3000, `max_identical_frames` 5, the first 2 pictures after each connect
  dropped, and a reconnect 1 s after any error
- Measured rate: about 2 pictures a second during the floor runs, with stalls of 1.5 to 2.5 s
  every 5 s or so. The rate swung with the room's Wi-Fi, since this camera shared channel 1 with
  9 other teams' cameras.

## Detection

- Detector used: the Edge Impulse model. On the board, `robocar_config.json` says
  `"detector": "model"`. The config in the repository still says `"color"`, its one difference
  from the board's copy.
- Model: Edge Impulse project `robocar-cones`, trained on the organizers' pictures (public
  project 1144501: the room's carpet, ball and cones, photographed from above). FOMO MobileNetV2
  0.35, 96 by 96 input, labels `soccerball` and `goal` (one box per cone). F1 score 96.9% on 57
  held-back pictures (goal 98%, ball 96.4%). The test set's score was not recorded. The
  resize mode came out as Fit shortest axis, so the model sees the middle 240 of the camera's 320
  columns. The file to download is the Linux (AARCH64) `.eim`.
- On the board, `model_runner.py` runs the `.eim` with only the standard library and numpy; on
  the organizers' pictures it took 3 to 9 ms each. It ignores boxes under 0.45 confidence, keeps
  the most confident ball box, and puts the goal at the midpoint of the two most confident cone
  boxes. One cone alone counts as no goal.
- Color settings (the fallback, not used in today's runs): the ball is HSV (0, 0, 170) to (179,
  150, 255), searched from 0.57 of the picture's height down to the bottom, and must be round.
  Each cone is HSV (25, 200, 120) to (37, 255, 255), searched from 0.38 to 0.8 of the height, and
  the goal is the midpoint of the two best cones. OpenCV's hue runs from 0 to 179.

## Motor calibration

The speeds and pulse lengths are the plan's starting values. No pulse was measured in centimeters
or degrees today, so the table gives what the floor runs showed.

| Direction | Speed | Duration (ms) | Movement | Surface | Battery (mV) |
|---|---|---|---|---|---|
| forward (approach) | 110 | 200 | small: 5 of these and 1 slow move brought the ball from y=130 to y=210 in the picture | gray carpet | fresh pack |
| forward (slow, near the ball) | 90 | 150 | not measured | gray carpet | fresh pack |
| forward (push) | 160 | 350 | moved the robot and the ball together; the third push rolled the ball on | gray carpet | fresh pack |
| left or right (slide) | 120 | 80 to 220, longer the further off center | very little: 4 slides left never brought a ball at x=70 back to the center | gray carpet | fresh pack |
| rotate_left or rotate_right | 160 | 80 to 220 | not used today: the robot only turns once it sees the goal | | |

The pack was swapped for a fresh one just before the floor runs. It read about 11,550 on
`battery_mv`, which reads about 1.5 times too high on the UNO Q.

`settle_ms`: 120, the planned value. No latency check (`"mode": "latency"`) was recorded today, so
it is not a measured number. In practice the video set the pace: each move waits for at least 2
new pictures after the last move ended (`min_new_frames`), and moves came 0.5 to 2.5 s apart.

## Behavior

Each pass of the loop takes the newest picture, finds the ball and the goal, and picks one move
from these rules, checked in order:

1. If the camera has sent no new picture for 3 s, keeps sending the same picture (5 times), or
   the reader fails, the robot stops. It never acts on a picture older than 3 s.
2. After 45 s (`run_time_limit_s`) the run ends.
3. After each move it waits for a picture that arrived at least 120 ms after the move ended and
   is at least the second new one since (`settle_ms`, `min_new_frames`), so it never acts on a
   picture taken before the move.
4. While the ball is missing it holds still. On the 5th missed picture in a row
   (`miss_frames_to_end`) the run ends: "ball lost", or "ball gone" after a push.
5. After 8 pushes (`max_pushes`) the run ends.
6. If the ball is not close and sits more than 24 px from the center, the robot slides sideways
   toward it (speed 120, 80 to 220 ms, longer the further off center). Sliding keeps it facing
   the way it started, toward the goal.
7. If the ball is centered and not close, it drives forward: 200 ms at speed 110, or 150 ms at
   speed 90 once the ball is near.
8. Once the ball is close and both cones are in view, it turns to center the ball, steps sideways
   around the ball until the goal is within 30 px of the ball's line, and pushes when they line
   up (350 ms at speed 160).
9. Once the ball is close and the goal is not in view (one cone counts as none), it centers the
   ball with a slide and pushes straight, as if lined up. Every push today went this way, since
   the model never found the cones.

"Near" means the ball's center is below 0.65 of the picture's height, or its radius is at least
28 px. "Close" means below 0.82, or a radius of at least 42 px, or touching the bottom edge with a
radius of at least 28 px. FOMO reports the ball's position but no size, so with the model the
ball's height in the picture decides.

Any error stops the motors and ends the run without ending the app, so the next BOOT press starts
a clean run. Every move lasts 1 to 1000 ms; a duration of 0, which means "drive forever", is never
sent.

## Results

Before the floor runs, a watch-only run with the model (ball about 1 m ahead) found the ball on 73
of 86 checks in 21.7 s, and an attempt with the wheels raised made 13 moves in 14.3 s, each from a
fresh picture, until a second BOOT press stopped it.

All floor runs were in attempt mode with the model, on gray carpet. Runs 1 to 8 had a limit of 3
pushes and 30 s, and runs 9 to 14 had 8 pushes and 45 s. A run ended on the 2nd missed picture
in a row in runs 1 to 4, and on the 5th from run 5 on.

| Run | Start arrangement | Result | Time (s) | Notes |
|---|---|---|---|---|
| 1 | ball ahead, two cones behind | ended before any move: no ball in the first 2 pictures | 0.2 | likely the hand on BOOT |
| 2 | same | ended the same way | 0.2 | |
| 3 | same | slid right twice toward a far ball (x=210, y=50), then lost it and stopped | 1.5 | maybe another team's ball |
| 4 | same | 6 forward moves, 1 slide, then a slow approach as the ball got near (y 110 to 160) | 9.4 | cut off by an app stop while still going |
| 5 | ball 50 cm to 1 m ahead, two cones behind | 1 slide toward a far ball, 6 moves to the ball, 3 pushes, then done on the push limit | 14.7 | goal never seen, pushed straight; the ball stopped short of the cones |
| 6 | same | 1 slide toward a far ball, 8 moves to the ball, 2 pushes; the ball rolled left, 4 slides left, then "ball gone after 2 push(es)" | 22.1 | slides barely move it on carpet |
| 7 | same | slid right toward a far ball, then no ball for 5 pictures, stopped | 2.1 | |
| 8 | same | 1 slide toward a far ball, 8 moves to the ball, 3 pushes, then done on the push limit | 14.7 | the ball rolled ahead and left |
| 9 | lined up: robot, ball and the gap between the cones in one line | 2 pushes, then "ball gone after 2 push(es)" | 31.3 | |
| 10 | same | 4 pushes, following the ball when it rolled; then 8 slides that never re-centered it, stopped with BOOT | 17.9 | |
| 11 | same | 2 pushes; the ball rolled left, 3 slides, then "ball gone after 2 push(es)" | 7.3 | |
| 12 | same | no ball in the first 5 pictures | 0.5 | |
| 13 | same | the ball close and off to the left; 3 slides, then lost it | 2.6 | |
| 14 | same | 1 push, drove up again after the ball rolled ahead, 3 more pushes, then "ball gone after 4 push(es)" | 23.2 | |

The best runs drove up to the ball and kept pushing it: runs 5 and 8 pushed 3 times in 14.7 s,
and runs 10 and 14 pushed 4 times, following the ball after it rolled ahead. In run 5 the ball
stopped short of the cones, so the push limit went from 3 to 8 and the time limit from 30 s to
45 s. No run used more than 4 pushes: each ended when the ball rolled off to one side, where
sideways slides could not bring it back to the center. Goals scored: [GOALS SCORED].

Video of a run: [VIDEO LINK]

What went wrong and how it recovered:

- Runs 1 and 2 ended at 0.2 s, before any move, because the first 2 pictures had no ball. The BOOT
  button is on the camera, so the hand pressing it likely filled those pictures. Raising
  `miss_frames_to_end` from 2 to 5 fixed it: no run after the change ended in its first pictures.
- Balls far away near the top of the picture, probably other teams', pulled the robot sideways in
  4 of the last 5 runs. When it lost them, it stopped cleanly (runs 3 and 7).
- In run 6 the ball rolled off to the left after 2 pushes, slides failed to re-center it, and the
  run stopped with "ball gone after 2 push(es)".
- Stale video: at 2:21 PM the video had gaps of up to 1.5 s, which the first limit of 400 ms
  treated as a dead camera. The limit went to 1500 ms and then to 3000 ms, with a 4 s read
  timeout, to ride out the room's 2 s stalls. The read timeout has to be longer than the limit,
  or the reader reconnects first.
- Sometimes an app restart left the motor chip silent: its first call (`stop`) timed out after
  10 s. A board restart (`sudo reboot`) brought it back each time, most recently at 3:32 PM. The
  `--no-prepare` restart usually avoids this, but it happened once more at 3:28 PM.
- After a battery swap the camera restarted but the board kept a dead Wi-Fi link ("No route to
  host"); `nmcli con up` brought the video back at once.
- Stopping the app at 3:03 PM cut run 4 off mid-approach, so check the log for a run in progress
  before stopping the app.

### Known limits

- The model never found the cones from the robot's camera. It was trained on pictures taken from
  above, where the cones look like round discs, while the robot sees them low, from the side, and
  small at 2 m. So the robot cannot line the ball up with the goal, and it always pushes straight,
  as if lined up. Retraining with pictures from the robot's own camera is the likely fix.
- It sometimes chases other teams' balls far away near the top of the picture.
- The video runs at about 2 pictures a second with stalls of about 2 s, so a move comes only every
  1.5 to 2 s.
- Sideways slides move the robot very little on this carpet, so a ball that rolls off to one side
  is hard to re-center.
- The pulses were not measured in centimeters, and `settle_ms` was not measured with the latency
  check.

## Credits

- Event guide and starter code (the starter `main.py`, `robot_client.py`, the motor sketch and the
  camera firmware): the event guide, github.com/aaishikasb/uno-q-hackout
- Arduino UNO Q, App Lab and Arduino App CLI: Arduino
- miniAuto chassis and camera module: Hiwonder
- Model training: Edge Impulse. Training pictures: the organizers' Edge Impulse project 1144501
  (studio.edgeimpulse.com/public/1144501/live)
- OpenCV and numpy
