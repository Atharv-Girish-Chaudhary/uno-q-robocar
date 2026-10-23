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
| 1 | lined up | attempt | | | | |
| 2 | | | | | | |
