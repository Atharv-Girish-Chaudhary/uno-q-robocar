# Checklist

## Before Saturday

Done on Oct 22:
- [x] uv 0.13.5 and adb (platform-tools 37.0.1) installed with Homebrew.
- [x] The guide cloned into `upstream/` for offline reading; its Makefile works with the Mac's make.
- [x] Prep code written and tested (`uv run pytest` in `prep/`).

Yours:
- [ ] Do the organizers' pre-work, `upstream/robocar/PREWORK.md` (about 30 minutes, no board
      needed). They added it on the evening of Oct 22 and ask for it before you connect the kit.
- [ ] Install Arduino App Lab and open it once (docs.arduino.cc/software/app-lab).
- [ ] Practice training one Edge Impulse model, following `EDGE_IMPULSE.md` (about an hour).
- [ ] Run the demo on your webcam in Warp, from `prep/`: `uv run python demo.py --source 0 --show`.
      Warp asks for camera access the first time.
- [ ] Read the robocar guide once, end to end (`upstream/robocar/README.md`, about 15 minutes).
- [ ] Pack the MacBook, its charger, and a USB-C cable that carries data (a longer one gives floor
      runs more room), plus a spare cable.
- [ ] Pack your phone and a cable for its hotspot. The venue has Wi-Fi, but campus networks
      often need a login page that a board without a screen can't open, and the hotspot also
      keeps the Mac online while its Wi-Fi is on the camera's network.
- [ ] Pack some sticky notes or paper to mark start spots. To measure pulses, a sheet of letter
      paper is 27.9 cm long, or use your phone's Measure app; ask the organizers for tape.
- [ ] Have `QUESTIONS.md` ready to ask at check-in.

## On the day, in order

1. Arrive by 9:30 AM; building starts at 10:00.
2. Ask the open questions in `QUESTIONS.md`: the ball and goal, the final run setup, pre-written
   code, which Wi-Fi the boards use, and how to hand in the project.
3. Safety setup: raise the wheels and find the motor-power disconnect.
4. Connect the UNO Q by USB and follow App Lab's board connection guide. Collect the camera's
   Wi-Fi name and password, and the motor calibration. If App Lab offers to update the board's
   software, ask the organizers first.
5. While the board has Internet, run the starter once (it compiles the sketch's libraries), and
   press BOOT for the 200 ms test pulse.
6. Still online, check that the app's Python can import OpenCV. If pre-written code is allowed,
   copy the prep files into the app (`NOTES.md`) with `"mode": "observe"` and read the startup
   line: Python, numpy and cv2 versions. If not, add `import cv2; print(cv2.__version__)` to the
   starter's `main.py` for one run. If the import fails, add `prep/requirements-board.txt` now,
   while the board can still download.
7. With the wheels raised, set the starter's test pulse to 1000 ms for one run, press BOOT once
   the wheels spin, and check that they stop at once; then set it back to 200 ms. Nobody can
   press BOOT inside a 200 ms pulse.
8. Camera: join the laptop to the camera's Wi-Fi (allow Local Network access if macOS asks),
   preview it, find a good angle, then close the preview. The laptop has no Internet while it is
   on that network.
9. Join the camera's Wi-Fi from the board's Linux side (`NOTES.md` has the command), then run the
   guide's stream check from the app.
10. Record real footage from the laptop (board app stopped) and tune the ball and the goal with
    `tune.py`; set the ball's search band to start just below the goal's base. Record the goal
    mouth up close too: the ball and the goal are both white and their search bands overlap
    there, so check that they stay apart.
11. Watch-only test: ball left, center, right, far, near, then hidden. The printed detections
    should match. Every robot's camera uses Wi-Fi channel 1, so if runs stop with "newest frame
    is N ms old" in the crowded room, raise `stream.stale_after_ms` a little, at most to 800.
12. Calibrate short moves with the wheels raised, then on the floor, and fill in
    `CALIBRATION_LOG.md`. The placeholder speeds give only about 24 to 33% wheel power, so expect
    to raise them if the robot barely moves. Run `"mode": "latency"` once on the floor and set
    `settle_ms` from it.
13. Autonomous runs (`"mode": "attempt"`): wheels raised first, then on the floor from the
    supplied start arrangement. Change one setting at a time and write it down. Keep watch-only
    runs short: each run holds every picture in memory, about 100 MB per 30 s at 15 frames a
    second.
14. Whenever the robot has to wait, such as while its battery charges, train a first Edge
    Impulse model from phone pictures, as an organizer advised (`EDGE_IMPULSE.md`, "On the
    day"). Test it in watch-only mode, retrain it with this camera's footage, and switch
    `"detector": "model"` once it finds the ball at least as well as the color detector.
15. Package: export the app from App Lab, copy `SUBMISSION_README_TEMPLATE.md` in as its
    `README.md` and fill it in, and credit the guide, Arduino, Hiwonder, Edge Impulse and OpenCV.

## After the event

What the prep installed outside this folder, and how to remove it. Nothing is removed
automatically.

- adb, from Homebrew's `android-platform-tools` (37 MB, for the whole Mac). Keep it if you will use
  an UNO Q again; otherwise:

  ```bash
  brew uninstall --cask android-platform-tools
  ```

- uv, from Homebrew (32 MB): keep it, it is your Python tool.
- Python 3.10, 3.11 and 3.12, downloaded by uv on Oct 22 (201 MB in uv's own Python folder).
  If no other project uses them:

  ```bash
  uv python uninstall 3.10 3.11 3.12
  ```

- uv's download cache (172 MB in uv's cache folder). Safe to clear, since uv downloads again when
  needed:

  ```bash
  uv cache clean
  ```

- `prep/.venv` (148 MB) lives inside this folder and goes with it.
