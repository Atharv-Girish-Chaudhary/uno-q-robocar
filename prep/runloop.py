"""Look, decide, move: the loop behind one BOOT-started run, shared by the robot and the demo.

It works with any robot object that has is_running(), drive(direction, speed, ms) and stop():
the guide's MiniAutoRobot on the board, demo.py's DryRobot on the laptop, fakes in the tests.
Three modes, chosen by run.mode in robocar_config.json:

- attempt: the real thing. Short pulses, each decided from a fresh frame, ending on any doubt.
- observe: the guide's step 5. Never moves; prints what it sees and what it would do.
- latency: one short pulse with the wheels on the floor, then a log of how the picture changes,
  to set controller.settle_ms from evidence instead of a guess.
"""

from __future__ import annotations

import json
import sys
import threading
import time
from dataclasses import dataclass, field, fields
from importlib import metadata
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Type, Union

import cv2
import numpy as np

from controller import ControllerConfig, Decision, Observation, decide, new_run, observation_from, record_move_end
from detector import ColorVision, DetectorConfig, Sighting
from model_runner import ModelConfig
from stream import StreamConfig, open_stream

MODES = ("attempt", "observe", "latency")
DETECTORS = ("color", "model")
SECTIONS = ("run", "ball", "goal", "model", "stream", "controller")
Log = Callable[[str], None]


@dataclass(frozen=True)
class RunConfig:
    mode: str = "attempt"
    detector: str = "color"
    latency_direction: str = "rotate_left"
    latency_speed: int = 150
    latency_ms: int = 200

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "RunConfig":
        unknown = set(raw) - {f.name for f in fields(cls)}
        if unknown:
            raise ValueError(f"unknown run settings: {sorted(unknown)}")
        cfg = cls(**raw)
        if cfg.mode not in MODES:
            raise ValueError(f"run.mode must be one of {MODES}, got {cfg.mode!r}")
        if cfg.detector not in DETECTORS:
            raise ValueError(f"run.detector must be one of {DETECTORS}, got {cfg.detector!r}")
        if not 1 <= cfg.latency_ms <= 1000 or not 1 <= cfg.latency_speed <= 255:
            raise ValueError("the latency pulse needs 1 to 1000 ms and a speed of 1 to 255")
        return cfg


@dataclass(frozen=True)
class Settings:
    run: RunConfig
    ball: DetectorConfig
    goal: Optional[DetectorConfig]
    model: ModelConfig
    stream: StreamConfig
    controller: ControllerConfig
    path: Optional[Path] = None


def load_settings(source: Union[str, Path, Dict[str, Any]]) -> Settings:
    """Every section of robocar_config.json, validated. Paths in it are relative to the file."""
    path: Optional[Path] = None
    if isinstance(source, dict):
        raw = source
    else:
        path = Path(source)
        raw = json.loads(path.read_text())
    unknown = set(raw) - set(SECTIONS)
    if unknown:
        raise ValueError(f"unknown config sections: {sorted(unknown)}")
    base = path.parent if path else Path.cwd()
    stream = StreamConfig.from_dict(raw.get("stream", {}))
    return Settings(
        run=RunConfig.from_dict(raw.get("run", {})),
        ball=DetectorConfig.from_dict(raw["ball"]),
        goal=DetectorConfig.from_dict(raw["goal"]) if raw.get("goal") else None,
        model=ModelConfig.from_dict(raw.get("model", {}), base_dir=base),
        stream=stream,
        controller=ControllerConfig.from_dict(raw.get("controller", {}), stale_after_ms=stream.stale_after_ms),
        path=path,
    )


def make_vision(settings: Settings, model_command: Optional[Sequence[str]] = None) -> Any:
    """The color detectors, or the Edge Impulse model when run.detector is "model"."""
    if settings.run.detector == "model":
        from model_runner import ModelVision

        return ModelVision(settings.model, command=model_command)
    return ColorVision(settings.ball, settings.goal)


def open_camera(settings: Settings, source: Union[None, int, str, Path] = None) -> Any:
    """Start reading the camera named in the config, or another source for laptop testing."""
    return open_stream(settings.stream.url if source is None else source, settings.stream)


def print_versions(log: Log = print) -> None:
    """What the board actually runs; the first run on Oct 24 settled whether OpenCV imports."""
    builds = []
    for name in ("opencv-python", "opencv-python-headless"):
        try:
            builds.append(f"{name} {metadata.version(name)}")
        except metadata.PackageNotFoundError:
            pass
    log(f"python {sys.version.split()[0]} | numpy {np.__version__} | cv2 {cv2.__version__} ({', '.join(builds) or 'no pip build found'})")


@dataclass
class Step:
    """One pass of the loop, for the log line, the demo's display and the tests."""

    t: float
    frame: Any
    sighting: Optional[Sighting]
    observation: Observation
    decision: Decision


@dataclass
class RunSummary:
    ended_by: str = ""  # "decision", "boot" or "error"
    reason: str = ""
    steps: int = 0
    moves: int = 0
    pushes: int = 0
    log: List[Step] = field(default_factory=list)


def format_step(step: Step, would: bool = False) -> str:
    o = step.observation
    if o.ball_found and o.ball_x is not None:
        ball = f"ball x={o.ball_x:3.0f} y={(o.ball_y or 0):3.0f} r={(o.ball_radius or 0):2.0f}"
    else:
        ball = "ball   --           "
    goal = f"goal x={o.goal_x:3.0f}" if o.goal_found and o.goal_x is not None else "goal   --"
    decision = ("would " if would else "") + step.decision.describe()
    return f"[{step.t:6.2f}s] frame {o.frame_seq:5d} | {ball} | {goal} | {decision}"


def _wait_fresh(
    camera: Any, newer_than: float, min_seq: int, timeout_s: float, clock: Callable[[], float]
) -> Any:
    """Wait for a fresh frame in short slices, giving up as soon as the stream reports a stall,
    so a frozen camera is noticed within stale_after_ms instead of after the whole timeout."""
    deadline = clock() + timeout_s
    while True:
        slice_s = min(0.05, max(0.0, deadline - clock()))
        frame = camera.wait_for_frame(newer_than=newer_than, min_seq=min_seq, timeout_s=slice_s)
        if frame is not None:
            return frame
        if clock() >= deadline or not camera.status(clock()).ok:
            return None


def _safe_stop(robot: Any, log: Log) -> None:
    try:
        robot.stop()
    except Exception as error:  # the motors' own timed stop is the backstop
        log(f"[ERROR] stop() failed too: {type(error).__name__}: {error}")


def run_attempt(
    robot: Any,
    camera: Any,
    vision: Any,
    cfg: ControllerConfig,
    clock: Callable[[], float] = time.monotonic,
    log: Log = print,
    passthrough: Tuple[Type[BaseException], ...] = (),
    on_step: Optional[Callable[[Step], None]] = None,
) -> RunSummary:
    """One attempt: short pulses decided from fresh frames, ending on any doubt.

    No exception escapes, except the types in `passthrough`: App Lab's App.run shuts the whole
    app down when an error leaves the loop, and then BOOT does nothing until the app restarts.
    """
    summary = RunSummary()
    start = clock()
    state = new_run(start)
    last = None
    try:
        while True:
            if not robot.is_running():
                summary.ended_by = "boot"
                summary.reason = "the program was disabled (BOOT pressed, or stop() called)"
                log(f"[RUN] {summary.reason}")
                return summary
            newer_than = last.arrival if last is not None else float("-inf")
            min_seq = last.seq + 1 if last is not None else 0
            if state.last_move_end is not None:
                newer_than = max(newer_than, state.last_move_end + cfg.settle_ms / 1000.0)
                min_seq = max(min_seq, state.move_end_seq + cfg.min_new_frames)
            timeout = (cfg.settle_ms + cfg.max_frame_age_ms) / 1000.0
            frame = _wait_fresh(camera, newer_than, min_seq, timeout, clock)
            sighting = None
            if frame is not None:
                image = frame.image
                if image is None:
                    log(f"[WARN] frame {frame.seq} could not be decoded; skipping it")
                    last = frame
                    continue
                sighting = vision.observe(image, frame.arrival)
                last = frame
            now = clock()
            status = camera.status(now)
            shown = frame if frame is not None else last
            obs = observation_from(
                sighting,
                shown.arrival if shown is not None else None,
                shown.seq if shown is not None else 0,
                status.ok,
                status.reason,
            )
            decision, state = decide(obs, state, cfg, now)
            summary.steps += 1
            step = Step(now - start, shown, sighting, obs, decision)
            summary.log.append(step)
            log(format_step(step))
            if on_step is not None:
                on_step(step)
            if decision.ends_run:
                summary.ended_by, summary.reason, summary.pushes = "decision", decision.reason, state.pushes
                _safe_stop(robot, log)
                return summary
            if decision.moves:
                if not 1 <= decision.ms <= cfg.max_pulse_ms:
                    raise ValueError(f"refusing a {decision.ms} ms pulse; pulses must be 1 to {cfg.max_pulse_ms} ms")
                robot.drive(decision.direction, speed=decision.speed, ms=decision.ms)
                summary.moves += 1
                state = record_move_end(state, clock(), camera.latest_seq())
            summary.pushes = state.pushes
    except passthrough:
        raise
    except Exception as error:
        summary.ended_by = "error"
        summary.reason = f"{type(error).__name__}: {error}"
        log(f"[ERROR] {summary.reason}; stopping the motors")
        _safe_stop(robot, log)
        return summary


def observe_only(
    robot: Any,
    camera: Any,
    vision: Any,
    cfg: ControllerConfig,
    clock: Callable[[], float] = time.monotonic,
    log: Log = print,
    passthrough: Tuple[Type[BaseException], ...] = (),
    on_step: Optional[Callable[[Step], None]] = None,
) -> RunSummary:
    """Watch and report, motors off: what the robot sees and the decision it would make."""
    summary = RunSummary()
    start = clock()
    last = None
    try:
        while robot.is_running():
            if clock() - start > cfg.run_time_limit_s:
                summary.ended_by, summary.reason = "decision", "time limit reached"
                break
            newer_than = last.arrival if last is not None else float("-inf")
            frame = _wait_fresh(camera, newer_than, 0, cfg.max_frame_age_ms / 1000.0, clock)
            sighting = None
            if frame is not None and frame.image is not None:
                sighting = vision.observe(frame.image, frame.arrival)
                last = frame
            now = clock()
            status = camera.status(now)
            shown = frame if frame is not None else last
            obs = observation_from(
                sighting, shown.arrival if shown else None, shown.seq if shown else 0, status.ok, status.reason
            )
            decision, _ = decide(obs, new_run(now), cfg, now)  # a fresh state: each frame on its own
            summary.steps += 1
            step = Step(now - start, shown, sighting, obs, decision)
            summary.log.append(step)
            log("[WATCH] " + format_step(step, would=True))
            if on_step is not None:
                on_step(step)
        else:
            summary.ended_by, summary.reason = "boot", "the program was disabled"
    except passthrough:
        raise
    except Exception as error:
        summary.ended_by, summary.reason = "error", f"{type(error).__name__}: {error}"
        log(f"[ERROR] {summary.reason}")
    _safe_stop(robot, log)
    return summary


def measure_latency(
    robot: Any,
    camera: Any,
    run_cfg: RunConfig,
    clock: Callable[[], float] = time.monotonic,
    log: Log = print,
    passthrough: Tuple[Type[BaseException], ...] = (),
    watch_s: float = 1.5,
    baseline_s: float = 0.5,
) -> RunSummary:
    """One short pulse, then how much each new frame differs from the one before it.

    Run it with the wheels on the floor, facing a still scene with some texture. The frames
    that change are the ones taken while the robot moved; the first unchanged frame after the
    pulse tells you how long controller.settle_ms needs to be."""
    summary = RunSummary()
    samples: List[Tuple[float, int, float]] = []
    done = threading.Event()

    def collect() -> None:
        previous = None
        seq = camera.latest_seq()
        while not done.is_set():
            frame = camera.wait_for_frame(min_seq=seq + 1, timeout_s=0.2)
            if frame is None or frame.image is None:
                continue
            seq = frame.seq
            small = cv2.resize(cv2.cvtColor(frame.image, cv2.COLOR_BGR2GRAY), (80, 60)).astype(np.float32)
            if previous is not None:
                samples.append((frame.arrival, frame.seq, float(np.mean(np.abs(small - previous)))))
            previous = small

    collector = threading.Thread(target=collect, daemon=True)
    try:
        collector.start()
        time.sleep(baseline_s)  # a baseline of still frames
        t0 = clock()
        robot.drive(run_cfg.latency_direction, speed=run_cfg.latency_speed, ms=run_cfg.latency_ms)
        t_return = clock()
        time.sleep(watch_s)
    except passthrough:
        done.set()
        raise
    except Exception as error:
        summary.ended_by, summary.reason = "error", f"{type(error).__name__}: {error}"
        log(f"[ERROR] {summary.reason}")
    finally:
        done.set()
        collector.join(timeout=1.0)
        _safe_stop(robot, log)
    if summary.ended_by == "error":
        return summary
    before = [d for t, _, d in samples if t < t0]
    noise = float(np.median(before)) if before else 0.0
    threshold = max(3.0 * noise, 2.0)
    log(f"[LATENCY] pulse {run_cfg.latency_direction} speed {run_cfg.latency_speed} for {run_cfg.latency_ms} ms; still-scene noise {noise:.1f}")
    for t, seq, diff in samples:
        mark = "moving" if diff > threshold else ""
        log(f"[LATENCY] {1000 * (t - t0):7.0f} ms  frame {seq:5d}  change {diff:5.1f}  {mark}")
    moving = [t for t, _, d in samples if t >= t0 and d > threshold]
    summary.ended_by = "decision"
    if not moving:
        summary.reason = "no movement seen: put the wheels on the floor and face a still, textured scene"
    else:
        still_after = [t for t, _, d in samples if t > moving[-1] and d <= threshold]
        settle = (still_after[0] if still_after else moving[-1]) - t_return
        summary.reason = (
            f"picture starts moving {1000 * (moving[0] - t0):.0f} ms after the command and is still "
            f"again {1000 * max(settle, 0):.0f} ms after drive() returns; set controller.settle_ms to "
            f"about {1000 * max(settle, 0) + 30:.0f}"
        )
    log(f"[LATENCY] {summary.reason}")
    return summary


def run_mode(
    robot: Any,
    camera: Any,
    vision: Any,
    settings: Settings,
    passthrough: Tuple[Type[BaseException], ...] = (),
    log: Log = print,
    on_step: Optional[Callable[[Step], None]] = None,
) -> RunSummary:
    mode = settings.run.mode
    if mode == "observe":
        return observe_only(robot, camera, vision, settings.controller, log=log, passthrough=passthrough, on_step=on_step)
    if mode == "latency":
        return measure_latency(robot, camera, settings.run, log=log, passthrough=passthrough)
    return run_attempt(robot, camera, vision, settings.controller, log=log, passthrough=passthrough, on_step=on_step)
