"""Reference copy of the guide's robocar/python/main.py, wired to the prep modules.

Adapted from robocar/python/main.py in the Build Day guide, github.com/aaishikasb/uno-q-hackout,
which states no license: the lines kept from it belong to the guide's authors and are not covered
by this repository's MIT license.

Never copy this into upstream/. On the day, in your own copy of the robocar app, put
detector.py, model_runner.py, stream.py, controller.py, runloop.py and robocar_config.json in
python/ beside main.py, then use this file's contents as main.py. Don't add numpy or OpenCV to
python/requirements.txt: the App Lab image already has both (see docs/NOTES.md).

Kept from the guide: the startup robot.stop(), the health and sensor prints, run_program as
App.run's user loop, and the finally block. Changed: motion_check() runs one look, decide, move
attempt from runloop.py instead of a single forward pulse, and user_loop() wraps run_program so
that an error from its own Bridge calls can't end the app.
"""

import time
from pathlib import Path

from arduino.app_utils import App
from robot_client import MiniAutoRobot, ProgramStopped

import runloop

CONFIG_PATH = Path(__file__).with_name("robocar_config.json")

robot = MiniAutoRobot()
settings = runloop.load_settings(CONFIG_PATH)
runloop.print_versions()
# Start reading the camera now, so frames are already flowing when BOOT is pressed.
camera = runloop.open_camera(settings)
vision = runloop.make_vision(settings)


def motion_check() -> None:
    # Every drive() is a short, bounded pulse, decided from a frame taken after the last one;
    # robot.stop() follows a lost ball, a stale feed or any error. ProgramStopped (BOOT pressed
    # mid-pulse) goes back to run_program, which reports it and waits for the next press.
    runloop.run_mode(robot, camera, vision, settings, passthrough=(ProgramStopped,))


def user_loop() -> None:
    # run_program's own Bridge calls (is_running() while waiting for BOOT, stop() and
    # hold_toggle() after each run) have no guard. One timeout there would leave App.run, and
    # App Lab would shut the app down with BOOT dead until a restart.
    try:
        robot.run_program(motion_check)
    except Exception as error:
        print(f"[ERROR] {type(error).__name__}: {error}; stopping the motors and trying again")
        try:
            robot.stop()
        except Exception:
            pass  # the motor timer still ends any pulse
        time.sleep(settings.stream.reconnect_delay_s)


try:
    robot.stop()
    print(f"health  : {robot.health()}")
    print(f"sensors : {robot.read_sensors()}")
    print(f"mode    : {settings.run.mode}, {settings.run.detector} detector, camera {settings.stream.url}")
    print("Raise the wheels, then short-press the camera BOOT button to start a run.")
    App.run(user_loop=user_loop)
finally:
    robot.stop()
    camera.close()
    vision.close()
