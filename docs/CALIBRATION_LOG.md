# Calibration log

Fill this in on the day. Every number here ends up in `robocar_config.json`.

## Robot

- Robot or camera network name:
- Supplied motor calibration:
- Battery at the start (`battery_mv` from `read_sensors()`):

## Short pulses

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

Run `"mode": "latency"` with the wheels on the floor, facing a still scene with some texture.

| # | Direction | Speed | Duration (ms) | Picture starts moving after (ms) | Still again after drive() returns (ms) | settle_ms chosen |
|---|---|---|---|---|---|---|
| 1 | rotate_left | 150 | 200 | | | |
| 2 | | | | | | |

## Ball size and height in the picture

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

| Target | Preset started from | HSV ranges saved | Search band (top, bottom) | Lighting | Notes |
|---|---|---|---|---|---|
| ball | white_ball | | | | |
| goal | white_goal | | | | |

## Runs

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
| 9 | lined up, 6 runs | attempt | `max_pushes` 3 to 8, `run_time_limit_s` 30 to 45 | best two pushed 4 times (18 s, stopped with BOOT; 23.2 s, ball gone); two pushed twice; two ended in the first 3 s | | slides never re-centered a ball 30 px left |
