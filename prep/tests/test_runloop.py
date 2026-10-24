import threading
import time
from collections import defaultdict

import cv2
import numpy as np
import pytest

import runloop
from controller import Action, ControllerConfig
from detector import ColorVision, DetectorConfig
from runloop import RunConfig, load_settings, measure_latency, observe_only, run_attempt
from stream import FrameSource, StreamConfig
from tests.fakes import FakeClock, FakeProgramStopped, FakeRobot, PassThroughVision, ScriptedCamera, sight
from tools import make_synthetic_video as syn

CFG = ControllerConfig()
FPS = 15.0


def frames_every(clock, sightings, start=0.0, fps=FPS):
    return [(clock() + start + i / fps, s) for i, s in enumerate(sightings)]


def run(sightings, robot=None, vision=None, cfg=CFG, **kwargs):
    clock = FakeClock()
    camera = ScriptedCamera(clock, frames_every(clock, sightings), stale_after_ms=cfg.max_frame_age_ms)
    robot = robot or FakeRobot(clock)
    if robot.clock is None:
        robot.clock = clock
    lines = []
    summary = run_attempt(robot, camera, vision or PassThroughVision(), cfg, clock=clock, log=lines.append, **kwargs)
    return summary, robot, lines


def test_a_lost_ball_ends_the_run_with_a_stop():
    seen = [sight((160, 150, 8))] * 15
    gone = [sight(None)] * 15
    summary, robot, _ = run(seen + gone)
    assert summary.ended_by == "decision" and "ball lost" in summary.reason
    assert robot.stops == 1 and robot.drives  # it approached, then stopped
    assert all(d[0] == "forward" for d in robot.drives)


def test_a_stale_feed_ends_the_run_with_a_stop():
    summary, robot, _ = run([sight((160, 150, 8))] * 5)  # then the camera goes quiet
    assert summary.ended_by == "decision"
    assert "old" in summary.reason or "feed" in summary.reason
    assert robot.stops == 1


def test_an_error_is_caught_and_stops_the_motors():
    summary, robot, lines = run([sight((160, 150, 8))] * 20, vision=PassThroughVision(fail_at_call=3))
    assert summary.ended_by == "error" and "detector blew up" in summary.reason
    assert robot.stops == 1
    assert any(line.startswith("[ERROR]") for line in lines)


def test_a_failing_stop_is_survived():
    robot = FakeRobot(stop_fails=True)
    summary, robot, lines = run([sight(None)] * 5, robot=robot)
    assert summary.ended_by == "decision" and robot.stops == 1
    assert any("stop() failed" in line for line in lines)


def test_passthrough_exceptions_go_back_to_run_program():
    robot = FakeRobot(raise_after_drives=2)
    with pytest.raises(FakeProgramStopped):
        run([sight((160, 150, 8))] * 30, robot=robot, passthrough=(FakeProgramStopped,))
    assert len(robot.drives) == 2


def test_boot_mid_run_exits_without_another_pulse():
    robot = FakeRobot(disable_after_drives=2)
    summary, robot, _ = run([sight((160, 150, 8))] * 30, robot=robot)
    assert summary.ended_by == "boot" and len(robot.drives) == 2


def test_is_running_is_checked_on_every_pass():
    summary, robot, _ = run([sight((160, 150, 8))] * 10 + [sight(None)] * 5)
    assert robot.is_running_calls >= summary.steps


def test_every_decision_after_a_move_uses_a_frame_taken_after_it():
    clock = FakeClock()
    start = clock()
    camera = ScriptedCamera(clock, frames_every(clock, [sight((60 + 4 * i, 150, 8)) for i in range(40)]))
    robot = FakeRobot(clock)
    robot.camera = camera
    summary = run_attempt(robot, camera, PassThroughVision(), CFG, clock=clock, log=lambda line: None)
    assert len(robot.drive_ends) >= 3
    checked = 0
    for step in summary.log:
        decided_at = start + step.t
        earlier = [i for i, t in enumerate(robot.drive_ends) if t <= decided_at]
        if not earlier or step.decision.action is Action.STOP:
            continue
        i = earlier[-1]
        # A fresh frame: it arrived settle_ms after the pulse ended, and is at least
        # min_new_frames past the newest frame at that moment.
        assert step.observation.frame_time >= robot.drive_ends[i] + CFG.settle_ms / 1000.0
        assert step.observation.frame_seq >= robot.drive_end_seqs[i] + CFG.min_new_frames
        checked += 1
    assert checked >= 3


def test_observe_mode_never_drives():
    clock = FakeClock()
    camera = ScriptedCamera(clock, frames_every(clock, [sight((60, 150, 8))] * 200))
    robot = FakeRobot(clock)
    cfg = ControllerConfig(run_time_limit_s=3)
    lines = []
    summary = observe_only(robot, camera, PassThroughVision(), cfg, clock=clock, log=lines.append)
    assert robot.drives == [] and summary.steps > 10
    assert all(line.startswith("[WATCH]") for line in lines)
    assert "would STEER" in lines[0]


def test_settings_load_from_the_config_file():
    settings = load_settings(runloop.Path(__file__).resolve().parents[1] / "robocar_config.json")
    assert settings.controller.max_frame_age_ms == settings.stream.stale_after_ms
    assert settings.model.path.endswith("models/robocar.eim")
    assert settings.run.mode == "attempt" and settings.run.detector == "color"
    with pytest.raises(ValueError, match="unknown config sections"):
        load_settings({"ball": {"hsv_ranges": [{"lower": [0, 0, 0], "upper": [1, 1, 1]}]}, "motors": {}})
    with pytest.raises(ValueError, match="run.mode"):
        RunConfig.from_dict({"mode": "race"})


class ShiftingCamera(FrameSource):
    """A real-time camera whose picture shifts while `moving` is set, for the latency check."""

    def __init__(self) -> None:
        super().__init__(StreamConfig(stale_after_ms=1000))
        rng = np.random.default_rng(3)
        self.texture = (rng.random((240, 400)) * 255).astype(np.uint8)
        self.moving = threading.Event()
        self.offset = 0

    def _run(self) -> None:
        while not self._closed.wait(0.02):
            if self.moving.is_set():
                self.offset += 6
            view = self.texture[:, self.offset % 80 : self.offset % 80 + 320]
            self._publish(image=cv2.cvtColor(np.ascontiguousarray(view), cv2.COLOR_GRAY2BGR))


class MovingRobot(FakeRobot):
    def __init__(self, camera):
        super().__init__()
        self.camera = camera

    def drive(self, direction, speed=150, ms=500):
        super().drive(direction, speed, ms)
        self.camera.moving.set()
        threading.Timer(ms / 1000.0, self.camera.moving.clear).start()
        time.sleep(ms / 1000.0 + 0.1)


def test_latency_mode_measures_how_long_the_picture_moves():
    with ShiftingCamera().start() as camera:
        robot = MovingRobot(camera)
        lines = []
        summary = measure_latency(robot, camera, RunConfig(latency_ms=200), log=lines.append, watch_s=0.5, baseline_s=0.3)
    assert len(robot.drives) == 1 and robot.drives[0][2] == 200
    assert "settle_ms" in summary.reason, summary.reason
    assert robot.stops == 1


# End to end: the run loop over the synthetic field video


def test_synthetic_video_decisions_scene_by_scene(config, presets):
    images, truth = syn.render()
    settings = load_settings(config)
    # The video shows August's field, so it gets August's presets, not the live config's ball and
    # goal, which tune.py rewrites on the day.
    vision = ColorVision(DetectorConfig.from_dict(presets["white_ball"]), DetectorConfig.from_dict(presets["white_goal"]))
    clock = FakeClock()
    camera = ScriptedCamera(clock, frames_every(clock, images), stale_after_ms=settings.stream.stale_after_ms)
    robot = FakeRobot(clock)
    seen = defaultdict(set)
    summaries = []
    while not camera.ended and len(summaries) < 60:
        robot.press_boot()  # each run starts like a fresh BOOT press
        summary = run_attempt(robot, camera, vision, settings.controller, clock=clock, log=lambda line: None)
        summaries.append(summary)
        for step in summary.log:
            scene = truth[step.observation.frame_seq - 1]["scene"] if step.observation.frame_seq else "none"
            seen[scene].add((step.decision.action, step.decision.direction))

    # The first run follows the ball from the left all the way through the goal scenes.
    first = [step.decision.action for step in summaries[0].log]
    for action in (Action.STEER, Action.FORWARD, Action.PUSH, Action.ORBIT):
        assert action in first, f"{action} missing from the first run: {first}"
    assert summaries[0].ended_by == "decision" and "ball gone after" in summaries[0].reason

    assert (Action.STEER, "left") in seen["left_far"]
    assert (Action.FORWARD, "forward") in seen["moving_to_center"] | seen["approach"]
    assert (Action.PUSH, "forward") in seen["close_goal_behind"]
    assert (Action.ORBIT, "right") in seen["close_goal_left"]
    assert not any(a in (Action.FORWARD, Action.PUSH) for a, _ in seen["white_box_no_ball"])
    assert (Action.STEER, "right") in seen["right_far"]
    # and every pulse was short and bounded (FakeRobot checks each one as it comes)
    assert robot.drives and all(1 <= ms <= settings.controller.max_pulse_ms for _, _, ms in robot.drives)
