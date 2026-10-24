"""Run robocar_main_template.py the way App Lab would, against the guide's real robot_client.py.

Only the board is faked: `arduino.app_utils` gets a Bridge that plays the MCU (it tracks
program_enabled and records every call) and an App whose run() presses BOOT twice. The guide's
robot_client.py is loaded straight from upstream/ (never copied); the test skips without it.
"""

import importlib.util
import json
import runpy
import sys
import threading
import types
from dataclasses import replace
from pathlib import Path

import cv2
import numpy as np
import pytest

import runloop
from controller import DIRECTIONS
from detector import DetectorConfig
from stream import FrameSource, StreamConfig
from tools import make_synthetic_video as syn

PREP = Path(__file__).resolve().parents[1]
ROBOT_CLIENT = PREP.parent / "upstream" / "robocar" / "python" / "robot_client.py"


class FakeBoard:
    """The MCU end of the Bridge."""

    def __init__(self, disable_after_drives):
        self.enabled = False
        self.calls = []
        self.disable_after_drives = disable_after_drives
        self.drives = 0
        self.failing_reads = 0

    def call(self, method, *params, timeout=10):
        self.calls.append((method, params))
        if method == "read_sensors" and self.failing_reads > 0:
            self.failing_reads -= 1
            raise TimeoutError("Bridge call 'read_sensors' timed out")  # the MCU didn't answer
        if method == "read_sensors":
            return json.dumps({"program_enabled": self.enabled, "hold_toggle": False, "ultrasonic_mm": -1, "battery_mv": 7600})
        if method == "health":
            return json.dumps({"robot": "hiwonder_miniauto", "mcu": "uno_q", "bridge": True, "serial": True})
        if method == "stop":
            self.enabled = False
            return True
        if method == "drive":
            self.drives += 1
            if self.drives >= self.disable_after_drives:
                self.enabled = False  # BOOT pressed during this pulse
            return True
        return True


class FakeApp:
    def __init__(self, board, camera, idle_timeouts=0):
        self.board, self.camera = board, camera
        self.presses = 0
        self.idle_timeouts = idle_timeouts

    def run(self, user_loop):
        if self.idle_timeouts:
            # Waiting for BOOT, run_program's own is_running() call times out on the Bridge.
            self.board.failing_reads = self.idle_timeouts
            user_loop()
        for hide_ball in (False, True):
            self.camera.hide_ball = hide_ball
            # Let frames of the new scene arrive first; the robot always acts on the newest one.
            self.camera.wait_for_frame(min_seq=self.camera.latest_seq() + 2, timeout_s=1.0)
            self.board.enabled = True  # a BOOT press
            self.presses += 1
            user_loop()
            user_loop()  # run_program runs the routine only once per press


class LiveCamera(FrameSource):
    """Real-time synthetic frames: the ball centered and far, or no ball at all."""

    def __init__(self):
        super().__init__(StreamConfig(stale_after_ms=400))
        rng = np.random.default_rng(11)
        self.with_ball = [syn.scene_image(rng, ball=(160, 150, 8), goal_x=160, spin=k) for k in range(8)]
        self.without_ball = [syn.scene_image(rng, goal_x=160) for _ in range(8)]
        self.hide_ball = False
        self.closed_by_template = False

    def _run(self):
        i = 0
        while not self._closed.wait(1 / 30):
            frames = self.without_ball if self.hide_ball else self.with_ball
            self._publish(image=frames[i % len(frames)])
            i += 1

    def close(self):
        self.closed_by_template = True
        super().close()


def run_template(monkeypatch, capsys, board, camera, app):
    app_utils = types.ModuleType("arduino.app_utils")
    app_utils.App = app
    app_utils.Bridge = board
    arduino = types.ModuleType("arduino")
    arduino.app_utils = app_utils
    monkeypatch.setitem(sys.modules, "arduino", arduino)
    monkeypatch.setitem(sys.modules, "arduino.app_utils", app_utils)

    monkeypatch.setattr(sys, "dont_write_bytecode", True)  # write nothing into upstream/
    spec = importlib.util.spec_from_file_location("robot_client", ROBOT_CLIENT)
    robot_client = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(robot_client)
    monkeypatch.setitem(sys.modules, "robot_client", robot_client)
    monkeypatch.setattr(runloop, "open_camera", lambda settings, source=None: camera)
    real_load_settings = runloop.load_settings

    def august_settings(path):
        # The synthetic pictures show August's field, so the template gets August's ball and goal
        # presets in place of the live config's, which tune.py rewrites on the day.
        presets = json.loads((PREP / "detector_presets.json").read_text())
        return replace(
            real_load_settings(path),
            ball=DetectorConfig.from_dict(presets["white_ball"]),
            goal=DetectorConfig.from_dict(presets["white_goal"]),
        )

    monkeypatch.setattr(runloop, "load_settings", august_settings)

    runpy.run_path(str(PREP / "robocar_main_template.py"), run_name="__main__")
    return capsys.readouterr().out


@pytest.mark.skipif(not ROBOT_CLIENT.exists(), reason="needs the guide cloned into upstream/")
def test_template_runs_the_loop_inside_the_guides_lifecycle(monkeypatch, capsys):
    board = FakeBoard(disable_after_drives=2)
    camera = LiveCamera().start()
    app = FakeApp(board, camera)
    out = run_template(monkeypatch, capsys, board, camera, app)

    methods = [m for m, _ in board.calls]
    assert methods[0] == "stop"  # the startup stop, before anything can move
    assert "health  :" in out and "python 3." in out and "cv2 4." in out
    assert app.presses == 2
    drives = [params for m, params in board.calls if m == "drive"]
    assert len(drives) == 2
    for direction, speed, ms in drives:
        assert direction in DIRECTIONS and 1 <= ms <= 1000 and 1 <= speed <= 255
    # Press 1 ended by BOOT mid-pulse (ProgramStopped, reported by run_program); press 2 saw no
    # ball and stopped. Every run ends in stop(), and the finally block closed the camera.
    assert "program stopped" in out
    assert "ball lost" in out
    assert methods[-1] == "stop" and methods.count("stop") >= 4
    assert camera.closed_by_template


@pytest.mark.skipif(not ROBOT_CLIENT.exists(), reason="needs the guide cloned into upstream/")
def test_a_bridge_timeout_while_waiting_for_boot_does_not_end_the_app(monkeypatch, capsys):
    # Without the template's guard, this TimeoutError would leave App.run and shut the app down.
    board = FakeBoard(disable_after_drives=2)
    camera = LiveCamera().start()
    app = FakeApp(board, camera, idle_timeouts=1)
    out = run_template(monkeypatch, capsys, board, camera, app)

    assert "[ERROR] TimeoutError" in out
    # The app kept going: both later BOOT presses ran, with the same bounded pulses.
    assert app.presses == 2
    drives = [params for m, params in board.calls if m == "drive"]
    assert len(drives) == 2 and all(1 <= ms <= 1000 for _, _, ms in drives)
    assert camera.closed_by_template
