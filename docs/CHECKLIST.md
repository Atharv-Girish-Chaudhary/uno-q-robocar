# Checklist

## Before Saturday

Done on Oct 22:
- [x] uv 0.13.5 and adb (platform-tools 37.0.1) installed with Homebrew.
- [x] The guide cloned into `upstream/` for offline reading; its Makefile works with the Mac's make.
- [x] Prep code written and tested (`uv run pytest` in `prep/`).

Yours:
- [ ] Install Arduino App Lab and open it once (docs.arduino.cc/software/app-lab).
- [ ] Practice training one Edge Impulse model, following `EDGE_IMPULSE.md` (about an hour).
- [ ] Run the demo on your webcam in Warp, from `prep/`: `uv run python demo.py --source 0 --show`.
      Warp asks for camera access the first time.
- [ ] Read the robocar guide once, end to end (`upstream/robocar/README.md`, about 15 minutes).
- [ ] Pack the MacBook, its charger, and a USB-C cable that carries data, plus a spare cable.
- [ ] Check that your phone can run a hotspot, as backup Internet for the board's first run.
- [ ] Pack a tape measure and masking tape, for measuring pulses and marking start spots.
- [ ] Have `QUESTIONS.md` ready to ask at check-in.

## On the day, in order

1. Arrive by 9:30 AM; building starts at 10:00.
2. Ask the open questions (ball and goal, final run setup, pre-written code, Internet).
3. Safety setup: raise the wheels and find the motor-power disconnect.
4. Connect the UNO Q by USB and follow App Lab's quickstart. Collect the camera's Wi-Fi name and
   password, and the motor calibration.
5. While the board has Internet, run the starter once (it compiles the sketch's libraries), and
   press BOOT for the 200 ms test pulse.
6. Press BOOT during a pulse and check that it stops.
7. Camera: preview it from the laptop, find a good angle, then close the preview.
8. Join the camera's Wi-Fi from the board's Linux side (`NOTES.md` has the command), then run the
   guide's stream check from the app.
9. If pre-written code is allowed, copy the prep files into the app (`NOTES.md`), with
   `"mode": "observe"` first. Check the startup line: Python, numpy and cv2 versions.
10. Record real footage from the laptop (board app stopped) and tune the ball and the goal with
    `tune.py`; set the ball's search band to start just below the goal's base.
11. Watch-only test: ball left, center, right, far, near, then hidden. The printed detections
    should match.
12. Calibrate short moves with the wheels raised, then on the floor, and fill in
    `CALIBRATION_LOG.md`. Run `"mode": "latency"` once on the floor and set `settle_ms` from it.
13. Autonomous runs (`"mode": "attempt"`): wheels raised first, then on the floor from the
    supplied start arrangement. Change one setting at a time and write it down.
14. Optional: retrain the Edge Impulse model with this camera's footage and switch
    `"detector": "model"`.
15. Package: export the app from App Lab, fill in `SUBMISSION_README_TEMPLATE.md`, credit the
    guide, Arduino, Hiwonder, Edge Impulse and OpenCV.
