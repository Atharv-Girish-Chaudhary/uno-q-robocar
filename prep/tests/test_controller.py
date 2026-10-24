from dataclasses import replace

import numpy as np
import pytest

from controller import (
    DIRECTIONS,
    Action,
    ControllerConfig,
    Observation,
    RunState,
    decide,
    new_run,
    record_move_end,
)

NOW = 100.0
CFG = ControllerConfig()


def observe(**changes):
    """A healthy frame: ball found, small and centered, goal centered behind it."""
    values = dict(
        frame_time=NOW - 0.05,
        frame_seq=10,
        width=320,
        height=240,
        stream_ok=True,
        stream_reason="ok",
        ball_found=True,
        ball_x=160.0,
        ball_y=150.0,
        ball_radius=8.0,
        ball_touches_bottom=False,
        goal_found=True,
        goal_x=160.0,
    )
    values.update(changes)
    return Observation(**values)


def state(**changes):
    return replace(RunState(started_at=NOW - 1.0), **changes)


CLOSE = dict(ball_radius=45.0, ball_y=205.0)

# One row per rule in docs/SPEC.md: id, observation changes, state changes, config changes,
# expected action, expected drive() direction (None when nothing moves), words in the reason.
RULES = [
    ("1 stream problem", dict(stream_ok=False, stream_reason="no new frame for 500 ms"), {}, {}, Action.STOP, None, "camera feed problem"),
    ("2 no frame", dict(frame_time=None), {}, {}, Action.STOP, None, "no camera frame"),
    ("2 old frame", dict(frame_time=NOW - 0.5), {}, {}, Action.STOP, None, "ms old"),
    ("3 time limit", {}, dict(started_at=NOW - 31), {}, Action.DONE, None, "time limit"),
    ("4 too soon after a move", dict(frame_time=NOW - 0.01), dict(last_move_end=NOW - 0.05, move_end_seq=5), {}, Action.WAIT, None, "too soon"),
    ("4 not enough new frames", {}, dict(last_move_end=NOW - 0.5, move_end_seq=9), {}, Action.WAIT, None, "waiting for frame 11"),
    ("4 fresh after a move", {}, dict(last_move_end=NOW - 0.5, move_end_seq=8), {}, Action.FORWARD, "forward", "far"),
    ("5 first miss", dict(ball_found=False, ball_x=None), {}, {}, Action.WAIT, None, "1 of 2"),
    ("6 second miss", dict(ball_found=False, ball_x=None), dict(misses=1), {}, Action.STOP, None, "ball lost"),
    ("6 miss after a push", dict(ball_found=False, ball_x=None), dict(misses=1, pushes=1), {}, Action.DONE, None, "gone after 1 push"),
    ("6 one-frame rule", dict(ball_found=False, ball_x=None), {}, dict(miss_frames_to_end=1), Action.STOP, None, "ball lost"),
    ("7 push limit", {}, dict(pushes=3), {}, Action.DONE, None, "after 3 pushes"),
    ("8 far left, strafe", dict(ball_x=60.0), {}, {}, Action.STEER, "left", "slide"),
    ("8 far right, rotate mode", dict(ball_x=260.0), {}, dict(steer_mode="rotate"), Action.STEER, "rotate_right", "turn"),
    ("8 mirrored camera", dict(ball_x=60.0), {}, dict(invert_steering=True), Action.STEER, "right", "slide"),
    ("9 centered far", dict(ball_x=170.0), {}, {}, Action.FORWARD, "forward", "far"),
    ("9 near by size", dict(ball_radius=30.0), {}, {}, Action.FORWARD, "forward", "near"),
    ("9 near by height", dict(ball_radius=10.0, ball_y=170.0), {}, {}, Action.FORWARD, "forward", "near"),
    ("10 close, off center, goal seen", dict(ball_x=210.0, **CLOSE), {}, {}, Action.ROTATE, "rotate_right", "turn"),
    ("11 close, goal left of ball", dict(goal_x=80.0, **CLOSE), {}, {}, Action.ORBIT, "right", "step right"),
    ("11 close, goal right of ball", dict(goal_x=250.0, **CLOSE), {}, {}, Action.ORBIT, "left", "step left"),
    ("11 mirrored camera", dict(goal_x=80.0, **CLOSE), {}, dict(invert_steering=True), Action.ORBIT, "left", "step left"),
    ("12 close, goal behind", dict(goal_x=170.0, **CLOSE), {}, {}, Action.PUSH, "forward", "goal behind"),
    ("12 close by height, model-sized box", dict(ball_radius=13.0, ball_y=205.0), {}, {}, Action.PUSH, "forward", "goal behind"),
    ("12 close, cut by bottom edge", dict(ball_radius=30.0, ball_y=225.0, ball_touches_bottom=True), {}, {}, Action.PUSH, "forward", "goal behind"),
    ("13 close, no goal, off center", dict(ball_x=100.0, goal_found=False, goal_x=None, **CLOSE), {}, {}, Action.STEER, "left", "slide"),
    ("14 close, no goal, centered", dict(goal_found=False, goal_x=None, **CLOSE), {}, {}, Action.PUSH, "forward", "not in view"),
]


@pytest.mark.parametrize(
    "obs_changes, state_changes, cfg_changes, action, direction, words",
    [row[1:] for row in RULES],
    ids=[row[0] for row in RULES],
)
def test_rules(obs_changes, state_changes, cfg_changes, action, direction, words):
    cfg = replace(CFG, **cfg_changes)
    decision, _ = decide(observe(**obs_changes), state(**state_changes), cfg, NOW)
    assert decision.action is action, decision.describe()
    assert words in decision.reason
    if direction is None:
        assert not decision.moves and decision.ms == 0
    else:
        assert decision.moves and decision.direction == direction
        assert 1 <= decision.ms <= cfg.max_pulse_ms


def test_pulse_sizes_follow_the_config():
    forward, _ = decide(observe(), state(), CFG, NOW)
    assert (forward.speed, forward.ms) == (CFG.approach_speed, CFG.approach_ms)
    slow, _ = decide(observe(ball_radius=30.0), state(), CFG, NOW)
    assert (slow.speed, slow.ms) == (CFG.slow_speed, CFG.slow_ms)
    push, _ = decide(observe(**CLOSE), state(), CFG, NOW)
    assert (push.speed, push.ms) == (CFG.push_speed, CFG.push_ms)
    orbit, _ = decide(observe(goal_x=60.0, **CLOSE), state(), CFG, NOW)
    assert (orbit.speed, orbit.ms) == (CFG.strafe_speed, CFG.orbit_ms)
    turn, _ = decide(observe(ball_x=230.0, **CLOSE), state(), CFG, NOW)
    assert turn.speed == CFG.rotate_speed


def test_steering_pulse_grows_with_the_offset():
    edge_of_band, _ = decide(observe(ball_x=160.0 + CFG.center_band_px + 0.5), state(), CFG, NOW)
    frame_edge, _ = decide(observe(ball_x=319.0), state(), CFG, NOW)
    middle, _ = decide(observe(ball_x=240.0), state(), CFG, NOW)
    assert edge_of_band.ms == pytest.approx(CFG.steer_ms_min, abs=1)
    assert frame_edge.ms == pytest.approx(CFG.steer_ms_max, abs=2)
    assert CFG.steer_ms_min < middle.ms < CFG.steer_ms_max


def test_state_counts_pushes_and_misses():
    _, s = decide(observe(**CLOSE), state(), CFG, NOW)
    assert s.pushes == 1
    _, s = decide(observe(ball_found=False, ball_x=None), s, CFG, NOW)
    assert s.misses == 1
    _, s = decide(observe(), s, CFG, NOW)
    assert s.misses == 0 and s.steps == 3


def test_a_move_needs_a_fresh_frame_then_resumes():
    s = record_move_end(new_run(NOW - 1.0), NOW - 0.3, seq=20)
    waiting, _ = decide(observe(frame_seq=21), s, CFG, NOW)
    assert waiting.action is Action.WAIT
    going, _ = decide(observe(frame_seq=22), s, CFG, NOW)
    assert going.action is Action.FORWARD


def test_no_moving_decision_ever_has_a_bad_pulse():
    rng = np.random.default_rng(7)
    cfgs = [CFG, replace(CFG, steer_mode="rotate"), replace(CFG, invert_steering=True)]
    for _ in range(3000):
        found = bool(rng.random() < 0.9)
        obs = observe(
            ball_found=found,
            ball_x=float(rng.uniform(0, 320)) if found else None,
            ball_y=float(rng.uniform(120, 240)),
            ball_radius=float(rng.uniform(3, 60)),
            ball_touches_bottom=bool(rng.random() < 0.2),
            goal_found=bool(rng.random() < 0.7),
            goal_x=float(rng.uniform(0, 320)),
            frame_seq=int(rng.integers(0, 40)),
        )
        s = state(
            misses=int(rng.integers(0, 3)),
            pushes=int(rng.integers(0, 4)),
            last_move_end=None if rng.random() < 0.5 else NOW - float(rng.uniform(0, 0.5)),
            move_end_seq=int(rng.integers(0, 40)),
        )
        cfg = cfgs[int(rng.integers(0, len(cfgs)))]
        decision, _ = decide(obs, s, cfg, NOW)
        if decision.moves:
            assert decision.direction in DIRECTIONS and decision.direction != "stop"
            assert 1 <= decision.ms <= cfg.max_pulse_ms
            assert 1 <= decision.speed <= 255
        else:
            assert decision.ms == 0


def test_config_file_section_loads(config):
    cfg = ControllerConfig.from_dict(config["controller"], stale_after_ms=config["stream"]["stale_after_ms"])
    assert cfg.max_frame_age_ms == config["stream"]["stale_after_ms"]


@pytest.mark.parametrize(
    "change, words",
    [
        ({"approach_ms": 0}, "drive forever"),
        ({"push_ms": 1500}, "every pulse"),
        ({"max_pulse_ms": 9000}, "firmware"),
        ({"max_pulse_ms": 1001}, "1 to 1000"),
        ({"max_pulse_ms": 3000}, "1 to 1000"),
        ({"steer_mode": "spin"}, "steer_mode"),
        ({"steer_ms_min": 300, "steer_ms_max": 200}, "larger"),
        ({"push_speed": 300}, "1 to 255"),
        ({"miss_frames_to_end": 0}, "at least 1"),
        ({"close_y_frac": 1.5}, "(0, 1]"),
        ({"max_frame_age_ms": 100}, "stale_after_ms"),
        ({"spped": 100}, "unknown"),
    ],
)
def test_bad_settings_are_refused(change, words):
    with pytest.raises(ValueError, match=words.replace("(", r"\(").replace("]", r"\]")):
        ControllerConfig.from_dict(change)
