# Rubric plan

The Robocar rubric totals 100 points. Each criterion gets a rating from 0 to 4: absent, partial,
basic, reliable, or consistently demonstrated. The guide doesn't say how a rating becomes points;
this plan assumed weight × rating ÷ 4, so a "reliable" 3 on ball detection is worth about 19 of 25.

![The 100 points to scale: half go to finding the ball and moving on fresh pictures](../figs/rubric-points.svg)

The judges are Aaishika Bhattacharya and Emre Gumus from Qualcomm Developer Relations, one per
track. They wrote the guide and the August Edge Impulse dataset.

The event page frames the mission as "which robocar can identify the goal and score first?"
The rubric has no speed criterion, so get the run reliable first, then shorten the waits and
lengthen the pulses.

## Ball detection (25)

- Judges want: the robot finds the ball across the agreed conditions and acts on it on its own.
- How this build shows it: the color detector looks for the white ball below the wall line, and
  checks size, fill and roundness, so boxes, bars and the goal are rejected. The model runner can
  swap in a trained Edge Impulse detector with no other change. Either one is tuned on site:
  `tune.py` for color, retraining with this robot's footage for the model.
- Show them: watch-only mode (`"mode": "observe"`) with the ball left, center, right, far, near
  and hidden, and the printed detections changing to match.
- Risk: a black and white ball is hard for color alone, especially in front of the white goal.
  Fallback: the trained model.

## Actions driven by perception (25)

- Judges want: fresh observations control short steering and approach movements.
- How this build shows it: every move is a pulse of 80 to 350 ms decided from a frame that
  arrived at least `settle_ms` after the previous pulse ended and is at least the second new frame
  since, because the camera's two frame buffers can still hold a picture taken before the move.
  Steering pulses grow with how far off center the ball is; the approach slows near the ball.
- Show them: the log, where each line prints what the camera saw beside the move chosen, and the
  latency check (`"mode": "latency"`) that measured `settle_ms` instead of guessing it.

## Goal-directed behavior (20)

- Judges want: the robot lines the ball up with the goal and scores under the challenge
  conditions.
- How this build shows it: steering slides sideways by default, so the robot keeps pointing the
  way it started (at the goal, in the guide's lined-up arrangement). Once the ball is close, the
  goal finder checks whether the goal is behind the ball. If it isn't, the robot turns to keep
  the ball centered and steps sideways around it, because the near ball shifts more in the
  picture than the far goal. It pushes when they line up, up to `max_pushes` times. If the goal
  is out of sight, it pushes as if lined up.
- Show them: a run from the lined-up start, then one with the ball a little off the line.
- Risk: stepping around the ball is the least tested behavior (no robot yet). Tune
  `goal_band_px` and `orbit_ms` on the day, or set `goal_band_px` very high to turn it off.

## Reliability and safe recovery (20)

- Judges want: the robot stops on a lost ball, stale video or errors, and restarts predictably.
- How this build shows it: the run ends with `robot.stop()` after 2 missed frames in a row; when
  no new frame arrives for `stale_after_ms` (400 ms), or the same JPEG repeats 5 times; and on any
  error, including a crashed model. No error escapes the loop, because App Lab shuts the whole app
  down when one does, and then BOOT does nothing. The camera reader reconnects on its own, so the
  next BOOT press starts a clean run.
- Show them: cover the ball (stop), unplug or switch off the camera mid-run (stop with the
  reason printed), then switch the camera back on and press BOOT again (a clean restart). Wait
  until the log shows fresh frames first: the board has to rejoin the camera's Wi-Fi, and BOOT
  itself is read through the camera.
- Evidence already: tests cover each of these against a fake camera that stalls, freezes and
  drops its connection; a frozen camera is reported within about 430 ms.

## Explanation and reproducibility (10)

- Judges want: source, launch instructions, calibration, results and credits let someone else
  repeat the demo.
- How this build shows it: `docs/SUBMISSION_README_TEMPLATE.md` to fill in, `docs/CALIBRATION_LOG.md`
  for the measured pulses and thresholds, and one settings file (`robocar_config.json`) holding
  every number. Recordings from the robot's camera (`demo.py --record`) let anyone replay a run.
- Show them: the README, the calibration log, and a recorded run replayed through `demo.py`.
