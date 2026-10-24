"""Pick the robot's next move from what the camera saw. Pure logic: no hardware, no clock.

The run loop calls decide() once per fresh frame. It returns a Decision (an action, the
drive() direction, speed and duration, and a readable reason) and the updated RunState. The
rules, in the order they are checked, are listed in docs/SPEC.md.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, replace
from enum import Enum
from typing import Any, Dict, Optional, Tuple

DIRECTIONS = ("forward", "backward", "left", "right", "rotate_left", "rotate_right", "stop")
STEER_MODES = ("strafe", "rotate")
FIRMWARE_MAX_MS = 5000
# The prep code's own ceiling, well under the firmware's: no setting can allow a pulse over 1 s.
PULSE_CAP_MS = 1000


class Action(str, Enum):
    STOP = "STOP"  # a fault: end the run
    DONE = "DONE"  # the attempt is over: end the run
    WAIT = "WAIT"  # hold still and look again
    STEER = "STEER"
    FORWARD = "FORWARD"
    ROTATE = "ROTATE"
    ORBIT = "ORBIT"
    PUSH = "PUSH"


MOVES = frozenset({Action.STEER, Action.FORWARD, Action.ROTATE, Action.ORBIT, Action.PUSH})
ENDS = frozenset({Action.STOP, Action.DONE})

PULSES = ("steer_ms_min", "steer_ms_max", "approach_ms", "slow_ms", "push_ms", "orbit_ms")
SPEEDS = ("strafe_speed", "rotate_speed", "approach_speed", "slow_speed", "push_speed")


@dataclass(frozen=True)
class ControllerConfig:
    center_band_px: float = 24
    invert_steering: bool = False
    steer_mode: str = "strafe"
    strafe_speed: int = 120
    rotate_speed: int = 160
    steer_ms_min: int = 80
    steer_ms_max: int = 220
    approach_speed: int = 110
    approach_ms: int = 200
    slow_radius_px: float = 28
    slow_y_frac: float = 0.65
    slow_speed: int = 90
    slow_ms: int = 150
    close_radius_px: float = 42
    close_y_frac: float = 0.82
    push_speed: int = 160
    push_ms: int = 350
    max_pushes: int = 3
    goal_band_px: float = 30
    orbit_ms: int = 150
    settle_ms: float = 120
    min_new_frames: int = 2
    miss_frames_to_end: int = 2
    run_time_limit_s: float = 30
    max_pulse_ms: int = 1000
    # Not set in the config file: the run loop copies it from stream.stale_after_ms, so the
    # stream and the controller can never disagree about what "stale" means.
    max_frame_age_ms: float = 400

    @classmethod
    def from_dict(
        cls, raw: Dict[str, Any], stale_after_ms: Optional[float] = None
    ) -> "ControllerConfig":
        if "max_frame_age_ms" in raw:
            raise ValueError("set stream.stale_after_ms instead of controller.max_frame_age_ms")
        known = {f.name for f in fields(cls)} - {"max_frame_age_ms"}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown controller settings: {sorted(unknown)}")
        cfg = cls(**raw)
        if stale_after_ms is not None:
            cfg = replace(cfg, max_frame_age_ms=float(stale_after_ms))
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if self.steer_mode not in STEER_MODES:
            raise ValueError(f"steer_mode must be one of {STEER_MODES}, got {self.steer_mode!r}")
        if not 1 <= self.max_pulse_ms <= PULSE_CAP_MS:
            raise ValueError(
                f"max_pulse_ms must be 1 to {PULSE_CAP_MS}: no pulse here may pass 1 s "
                f"(the firmware's own limit is {FIRMWARE_MAX_MS})"
            )
        for name in PULSES:
            ms = getattr(self, name)
            if not 1 <= ms <= self.max_pulse_ms:
                raise ValueError(
                    f"{name} is {ms} ms, but every pulse must be 1 to {self.max_pulse_ms} ms "
                    "(0 would mean drive forever)"
                )
        if self.steer_ms_min > self.steer_ms_max:
            raise ValueError("steer_ms_min can't be larger than steer_ms_max")
        for name in SPEEDS:
            if not 1 <= getattr(self, name) <= 255:
                raise ValueError(f"{name} must be 1 to 255")
        for name in ("slow_y_frac", "close_y_frac"):
            if not 0.0 < getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be in (0, 1]")
        for name in ("max_pushes", "min_new_frames", "miss_frames_to_end"):
            if getattr(self, name) < 1:
                raise ValueError(f"{name} must be at least 1")
        for name in ("center_band_px", "goal_band_px", "settle_ms", "slow_radius_px", "close_radius_px"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} can't be negative")
        if self.run_time_limit_s <= 0 or self.max_frame_age_ms <= 0:
            raise ValueError("run_time_limit_s and the stale limit must be positive")


@dataclass(frozen=True)
class Observation:
    """What the controller needs from one frame. Times are time.monotonic() seconds."""

    frame_time: Optional[float]
    frame_seq: int = 0
    width: int = 320
    height: int = 240
    stream_ok: bool = True
    stream_reason: str = ""
    ball_found: bool = False
    ball_x: Optional[float] = None
    ball_y: Optional[float] = None
    ball_radius: Optional[float] = None
    ball_touches_bottom: bool = False
    goal_found: bool = False
    goal_x: Optional[float] = None


def observation_from(
    sighting: Any, frame_time: Optional[float], frame_seq: int, stream_ok: bool, stream_reason: str
) -> Observation:
    """An Observation from any detector's Sighting (ball, goal, width, height)."""
    if sighting is None:
        return Observation(
            frame_time=frame_time, frame_seq=frame_seq, stream_ok=stream_ok, stream_reason=stream_reason
        )
    ball, goal = sighting.ball, sighting.goal
    return Observation(
        frame_time=frame_time,
        frame_seq=frame_seq,
        width=sighting.width,
        height=sighting.height,
        stream_ok=stream_ok,
        stream_reason=stream_reason,
        ball_found=bool(ball.found),
        ball_x=ball.x,
        ball_y=ball.y,
        ball_radius=ball.radius,
        ball_touches_bottom=bool(ball.touches_bottom),
        goal_found=bool(goal.found),
        goal_x=goal.x,
    )


@dataclass(frozen=True)
class RunState:
    started_at: float
    misses: int = 0
    pushes: int = 0
    steps: int = 0
    last_move_end: Optional[float] = None
    move_end_seq: int = 0


def new_run(now: float) -> RunState:
    return RunState(started_at=now)


def record_move_end(state: RunState, t: float, seq: int) -> RunState:
    """Note when a pulse ended and the newest frame number at that moment."""
    return replace(state, last_move_end=t, move_end_seq=seq)


@dataclass(frozen=True)
class Decision:
    action: Action
    reason: str
    direction: str = "stop"
    speed: int = 0
    ms: int = 0

    @property
    def moves(self) -> bool:
        return self.action in MOVES

    @property
    def ends_run(self) -> bool:
        return self.action in ENDS

    def describe(self) -> str:
        if self.moves:
            return f"{self.action.value:<7} {self.direction} speed={self.speed} ms={self.ms}: {self.reason}"
        return f"{self.action.value:<7} {self.reason}"


def is_close(obs: Observation, cfg: ControllerConfig) -> bool:
    radius = obs.ball_radius or 0.0
    low = obs.ball_y is not None and obs.ball_y >= cfg.close_y_frac * obs.height
    edge = obs.ball_touches_bottom and radius >= cfg.slow_radius_px
    return radius >= cfg.close_radius_px or low or edge


def is_near(obs: Observation, cfg: ControllerConfig) -> bool:
    radius = obs.ball_radius or 0.0
    low = obs.ball_y is not None and obs.ball_y >= cfg.slow_y_frac * obs.height
    return radius >= cfg.slow_radius_px or low


def _steer_ms(offset: float, half_width: float, cfg: ControllerConfig) -> int:
    """Longer pulses for a ball far off center, from steer_ms_min at the band to steer_ms_max."""
    span = max(half_width - cfg.center_band_px, 1.0)
    share = min(max((abs(offset) - cfg.center_band_px) / span, 0.0), 1.0)
    return int(round(cfg.steer_ms_min + share * (cfg.steer_ms_max - cfg.steer_ms_min)))


def _steer(offset: float, mode: str, half_width: float, cfg: ControllerConfig, action: Action) -> Decision:
    side = "right" if offset > 0 else "left"
    where = f"ball {abs(offset):.0f} px {side} of center (band {cfg.center_band_px:g})"
    if mode == "rotate":
        return Decision(
            action,
            f"{where}: turn toward it",
            direction=f"rotate_{side}",
            speed=cfg.rotate_speed,
            ms=_steer_ms(offset, half_width, cfg),
        )
    return Decision(
        action,
        f"{where}: slide toward it",
        direction=side,
        speed=cfg.strafe_speed,
        ms=_steer_ms(offset, half_width, cfg),
    )


def decide(obs: Observation, state: RunState, cfg: ControllerConfig, now: float) -> Tuple[Decision, RunState]:
    state = replace(state, steps=state.steps + 1)

    if not obs.stream_ok:
        return Decision(Action.STOP, f"camera feed problem: {obs.stream_reason}"), state
    if obs.frame_time is None:
        return Decision(Action.STOP, "no camera frame received"), state
    age_ms = (now - obs.frame_time) * 1000.0
    if age_ms > cfg.max_frame_age_ms:
        return (
            Decision(Action.STOP, f"newest frame is {age_ms:.0f} ms old (limit {cfg.max_frame_age_ms:.0f} ms)"),
            state,
        )
    if now - state.started_at > cfg.run_time_limit_s:
        return Decision(Action.DONE, f"time limit of {cfg.run_time_limit_s:g} s reached"), state

    if state.last_move_end is not None:
        if obs.frame_time < state.last_move_end + cfg.settle_ms / 1000.0:
            return Decision(Action.WAIT, "frame arrived too soon after the last move; waiting for a fresh one"), state
        needed = state.move_end_seq + cfg.min_new_frames
        if obs.frame_seq < needed:
            return (
                Decision(Action.WAIT, f"waiting for frame {needed}; the camera may still be sending older pictures"),
                state,
            )

    if not obs.ball_found or obs.ball_x is None:
        misses = state.misses + 1
        state = replace(state, misses=misses)
        if misses < cfg.miss_frames_to_end:
            return Decision(Action.WAIT, f"ball not seen ({misses} of {cfg.miss_frames_to_end}); holding still"), state
        if state.pushes > 0:
            return Decision(Action.DONE, f"ball gone after {state.pushes} push(es): attempt finished"), state
        return Decision(Action.STOP, f"ball lost for {misses} frames in a row"), state
    state = replace(state, misses=0)

    if state.pushes >= cfg.max_pushes:
        return (
            Decision(Action.DONE, f"attempt finished after {state.pushes} pushes; ball now at x={obs.ball_x:.0f}"),
            state,
        )

    sign = -1.0 if cfg.invert_steering else 1.0
    half = obs.width / 2.0
    offset = sign * (obs.ball_x - half)
    off_center = abs(offset) > cfg.center_band_px

    if not is_close(obs, cfg):
        if off_center:
            return _steer(offset, cfg.steer_mode, half, cfg, Action.STEER), state
        if is_near(obs, cfg):
            return (
                Decision(Action.FORWARD, "ball centered and near: slow approach", "forward", cfg.slow_speed, cfg.slow_ms),
                state,
            )
        return (
            Decision(Action.FORWARD, "ball centered and far: approach", "forward", cfg.approach_speed, cfg.approach_ms),
            state,
        )

    if obs.goal_found and obs.goal_x is not None:
        if off_center:
            # Turning re-centers the ball without changing where the goal sits relative to it.
            return _steer(offset, "rotate", half, cfg, Action.ROTATE), state
        goal_offset = sign * (obs.goal_x - obs.ball_x)
        if abs(goal_offset) > cfg.goal_band_px:
            # The near ball shifts more in the picture than the far goal, so stepping away from
            # the goal's side brings the goal back behind the ball.
            goal_side, step = ("left", "right") if goal_offset < 0 else ("right", "left")
            return (
                Decision(
                    Action.ORBIT,
                    f"goal {abs(goal_offset):.0f} px {goal_side} of the ball (band {cfg.goal_band_px:g}): step {step} around it",
                    step,
                    cfg.strafe_speed,
                    cfg.orbit_ms,
                ),
                state,
            )
        state = replace(state, pushes=state.pushes + 1)
        return (
            Decision(Action.PUSH, "ball close and centered, goal behind it: push", "forward", cfg.push_speed, cfg.push_ms),
            state,
        )

    if off_center:
        return _steer(offset, cfg.steer_mode, half, cfg, Action.STEER), state
    state = replace(state, pushes=state.pushes + 1)
    return (
        Decision(
            Action.PUSH,
            "ball close and centered, goal not in view: pushing as if lined up",
            "forward",
            cfg.push_speed,
            cfg.push_ms,
        ),
        state,
    )
