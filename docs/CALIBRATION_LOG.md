# Calibration log

Written before the event as tables to fill in on the day. Only the runs table at the end was
filled in: the pulse, camera timing, ball size and detector tables below were never measured, and
they are kept as the plan. The settings from the end of the day are in `prep/robocar_config.json`.

## Robot

Not filled in on the day.

- Robot or camera network name:
- Supplied motor calibration:
- Battery at the start (`battery_mv` from `read_sensors()`):

## Short pulses

Not measured on the day.

Start around 100 to 200 ms, wheels raised first, then on the floor. Find the lowest speed that
moves the robot reliably in each direction. Turning in place gets about 70% of the wheel power of
a straight move at the same speed number, so expect to need a higher speed for it.

| # | Time | Direction | Speed | Duration (ms) | Surface | Battery (mV) | Observed movement (cm or degrees) | Notes |
|---|---|---|---|---|---|---|---|---|
| 1 | | forward | 100 | 200 | | | | |
| 2 | | forward | | | | | | |
| 3 | | left (slide) | | | | | | |
| 4 | | right (slide) | | | | | | |
| 5 | | rotate_left | | | | | | |
| 6 | | rotate_right | | | | | | |
| 7 | | backward | | | | | | |
| 8 | | | | | | | | |

## Camera timing

Not measured on the day.

Run `"mode": "latency"` with the wheels on the floor, facing a still scene with some texture.

| # | Direction | Speed | Duration (ms) | Picture starts moving after (ms) | Still again after drive() returns (ms) | settle_ms chosen |
|---|---|---|---|---|---|---|
| 1 | rotate_left | 150 | 200 | | | |
| 2 | | | | | | |

## Ball size and height in the picture

Not measured on the day.

Place the ball straight ahead at measured distances. Read `r` and `y` from the watch-only log.
These set `slow_radius_px`, `close_radius_px`, `slow_y_frac` and `close_y_frac` (y divided by
240).

| Distance (cm) | Radius r (px) | Center y (px) | Touches the bottom edge? | Notes |
|---|---|---|---|---|
| 100 | | | | |
| 60 | | | | |
| 40 | | | | |
| 25 | | | | |
| 15 | | | | |

## Detector settings

Not measured on the day.

| Target | Preset started from | HSV ranges saved | Search band (top, bottom) | Lighting | Notes |
|---|---|---|---|---|---|
| ball | white_ball | | | | |
| goal | white_goal | | | | |

## Runs

Every run on the day that the app's log or the notes record, in order. All are in attempt mode
with the model as the detector, on gray carpet. Runs 1 to 14 match the numbering in the hand-in
README (`SUBMISSION_README.md`).

| # | Start arrangement | Mode | Settings changed | Result | Time to score (s) | Notes |
|---|---|---|---|---|---|---|
| 1 | ball ahead, two cones behind | attempt | none (model, miss limit 2) | ended at 0.2 s: no ball in the first 2 pictures | | likely the hand on BOOT |
| 2 | same | attempt | none | ended at 0.2 s, the same way | | |
| 3 | same | attempt | none | slid right twice toward a ball far right (x=210, y=50), lost it at 1.5 s | | maybe another team's ball |
| 4 | same | attempt | none | 6 forward moves, 1 slide, then a slow approach (ball y 110 to 160) | | cut off at 9.4 s by an app stop |
| 5 | ball 50 cm to 1 m ahead, two cones behind | attempt | `miss_frames_to_end` 2 to 5 | 1 slide toward a far ball, 6 moves to the ball, 3 pushes, done after 3 pushes at 14.7 s | | goal never seen, pushed straight; the ball stopped short of the cones |
| 6 | same | attempt | none | 1 slide toward a far ball, 8 moves to the ball, 2 pushes; the ball rolled left, 4 slides left, ball gone at 22.1 s | | slides barely move it on carpet |
| 7 | same | attempt | none | slid right toward a far ball, then no ball for 5 pictures, ended at 2.1 s | | |
| 8 | same | attempt | none | 1 slide toward a far ball, 8 moves to the ball, 3 pushes, done at 14.7 s | | the ball rolled ahead and left |
| 9 | lined up: robot, ball and the gap between the cones in one line | attempt | `max_pushes` 3 to 8, `run_time_limit_s` 30 to 45 | 2 pushes, then ball gone at 31.3 s | | |
| 10 | same | attempt | none | 4 pushes, following the ball when it rolled; then 8 slides that never re-centered it; stopped with BOOT at 17.9 s | | |
| 11 | same | attempt | none | 2 pushes; the ball rolled left, 3 slides, ball gone at 7.3 s | | |
| 12 | same | attempt | none | no ball in the first 5 pictures, ended at 0.5 s | | |
| 13 | same | attempt | none | the ball close and off to the left; 3 slides, then lost it at 2.6 s | | |
| 14 | same | attempt | none | 1 push, drove up again after the ball rolled ahead, 3 more pushes, ball gone at 23.2 s | | one of runs 9 to 14 put the ball between the cones, seen at the field; the log can't show which |
| 15 | lined up | attempt | none | 4 pushes, 2 slides toward a far ball, then 12 slides left that never re-centered the ball; ball gone at 36.7 s | | just before 4:00 PM |
| 16 | not recorded | attempt | `steer_mode` strafe to rotate, `center_band_px` 24 to 40 | stopped at once: no picture, since a flat battery had taken the camera's network down | | 4:11 PM |
| 17 | not recorded, after a reboot | attempt | none (the `python/go` stopgap now on the board) | stopped at 0.6 s with no ball in view | | 4:34 PM, started from the laptop |
| 18 | lined up | attempt | none | 4 pushes, turned toward balls, ball gone at 18.4 s | | started with BOOT |
| 19 | ball only, no cones | attempt | none | 4 forward moves that left the ball at y=150, 2 slow, 2 pushes, ball gone at 12.9 s | | started from the laptop; the ball sat in the blind spot |
| 20 | retry for the judges | attempt | none | 7 moves to the ball, then all 8 pushes, the ball kept at the front; done on the push limit at 23.1 s | | best run at these move sizes |
| 21 | retry for the judges | attempt | none | 4 forward moves, then stopped with BOOT at about 5 s | | |
| 22 | ball near at the start | attempt | approach 220/400 ms, slow 180/300 ms, push 255/550 ms (4x the speed times time) | 2 pushes and 2 near moves, ball out of view three times, ball gone at 10.8 s | | big moves near the ball lose it |
| 23 | not recorded | attempt | none | 2 far moves, then stopped with BOOT | | |
| 24 | the judged run | attempt | none (the faster moves) | 2 far moves, a near move, pushes at 4.4 s and 5.9 s, 2 near moves, ball out of view at 10.4 s, ball gone at 10.9 s; first place in the track | 7.12 | the time is the one reported at the field; the log, read at 5:05 PM, can't show the goal |
