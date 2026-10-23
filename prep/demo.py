"""Run the robot's whole loop on a laptop: camera or video in, decisions out, no motors.

    uv run python tools/make_synthetic_video.py                  # once; writes samples/
    uv run python demo.py --source samples/synthetic_field.avi
    uv run python demo.py --source 0 --show                      # your webcam
    uv run python demo.py --source http://127.0.0.1:8081/stream   # tools/fake_camera.py
    uv run python demo.py --source http://192.168.5.1:81/stream   # the robot camera, on its Wi-Fi

Each line shows what the camera saw and what the robot would do. A DryRobot stands in for the
motors: drive() prints the move and waits as long as the real pulse would, so frames that arrive
during a pulse are skipped exactly as on the robot. When a run ends, the next one starts after a
short pause, as if BOOT were pressed again. Nothing here sends a motor command.
"""

from __future__ import annotations

import argparse
import threading
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Callable, List, Optional

import cv2
import numpy as np

from runloop import Settings, Step, load_settings, make_vision, open_camera, print_versions, run_mode
from stream import FrameRecorder

HERE = Path(__file__).resolve().parent


class DryRobot:
    """The MiniAutoRobot calls the run loop uses, with no hardware behind them."""

    def __init__(self, log: Callable[[str], None] = print, sleep: Callable[[float], None] = time.sleep) -> None:
        self.log, self.sleep = log, sleep
        self.enabled = False
        self.drives = 0

    def press_boot(self) -> None:
        self.enabled = True

    def is_running(self) -> bool:
        return self.enabled

    def drive(self, direction: str, speed: int = 150, ms: int = 500) -> None:
        if not self.enabled:
            raise RuntimeError("drive() called while the program is disabled")
        self.drives += 1
        self.log(f"{'':10s}(dry run: drive {direction} at speed {speed} for {ms} ms, nothing sent)")
        self.sleep(ms / 1000.0 + 0.1)  # the same wait as MiniAutoRobot.drive

    def stop(self) -> bool:
        self.enabled = False
        return True


def annotate(image: np.ndarray, step: Step, settings: Settings) -> np.ndarray:
    """The frame with the search band, the center band, the detections and the decision."""
    out = image.copy()
    h, w = out.shape[:2]
    gray, green, yellow, white = (150, 150, 150), (60, 220, 60), (40, 220, 240), (255, 255, 255)
    band = settings.controller.center_band_px
    for x in (int(w / 2 - band), int(w / 2 + band)):
        cv2.line(out, (x, 0), (x, h - 1), gray, 1)
    top = int(settings.ball.roi_top_frac * h)
    cv2.line(out, (0, top), (w - 1, top), (200, 120, 40), 1)
    sighting = step.sighting
    if sighting is not None and sighting.ball.found:
        b = sighting.ball
        cv2.circle(out, (int(b.x), int(b.y)), max(int(b.radius or 3), 3), green, 2)
    if sighting is not None and sighting.goal.found:
        g = sighting.goal
        half_w, half_h = (g.width or 20) / 2, (g.height or 10) / 2
        cv2.rectangle(out, (int(g.x - half_w), int(g.y - half_h)), (int(g.x + half_w), int(g.y + half_h)), yellow, 2)
    text = f"{step.decision.action.value} {step.decision.direction if step.decision.moves else ''}".strip()
    cv2.rectangle(out, (0, 0), (w - 1, 18), (0, 0, 0), -1)
    cv2.putText(out, text, (4, 13), cv2.FONT_HERSHEY_SIMPLEX, 0.45, white, 1, cv2.LINE_AA)
    return out


class Display:
    """Shows and/or saves the annotated frames; q in the window ends the demo."""

    def __init__(self, settings: Settings, show: bool, save_dir: Optional[Path]) -> None:
        self.settings, self.show, self.save_dir = settings, show, save_dir
        self.quit = False
        if save_dir is not None:
            save_dir.mkdir(parents=True, exist_ok=True)

    def __call__(self, step: Step) -> None:
        if step.frame is None or step.frame.image is None:
            return
        picture = annotate(step.frame.image, step, self.settings)
        if self.save_dir is not None:
            cv2.imwrite(str(self.save_dir / f"{step.frame.seq:06d}.jpg"), picture)
        if self.show:
            cv2.imshow("demo (q quits)", picture)
            if cv2.waitKey(1) & 0xFF == ord("q"):
                self.quit = True


class Recording(threading.Thread):
    """Saves every new frame, not only the ones the loop decides on, for replay and tuning."""

    def __init__(self, camera: Any, folder: Path) -> None:
        super().__init__(daemon=True)
        self.camera, self.recorder = camera, FrameRecorder(folder)
        self.done = threading.Event()

    def run(self) -> None:
        seq = 0
        while not self.done.is_set():
            frame = self.camera.wait_for_frame(min_seq=seq + 1, timeout_s=0.3)
            if frame is not None:
                self.recorder.add(frame)
                seq = frame.seq

    def stop(self) -> None:
        self.done.set()
        self.join(timeout=1.0)
        self.recorder.close()


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Dry-run the robocar loop on a camera or video.")
    parser.add_argument("--source", required=True, help="webcam index, video file, recording folder or http:// URL")
    parser.add_argument("--config", default=str(HERE / "robocar_config.json"))
    parser.add_argument("--mode", choices=("attempt", "observe"), help="override run.mode")
    parser.add_argument("--detector", choices=("color", "model"), help="override run.detector")
    parser.add_argument("--show", action="store_true", help="show the annotated frames in a window")
    parser.add_argument("--save-dir", type=Path, help="save the annotated frames here")
    parser.add_argument("--record", type=Path, help="save every raw frame here, with arrival times")
    parser.add_argument("--loop", action="store_true", help="play a video file or recording on repeat")
    parser.add_argument("--once", action="store_true", help="stop after the first run")
    parser.add_argument("--runs", type=int, default=0, help="stop after this many runs (0: until the source ends)")
    parser.add_argument("--restart-s", type=float, default=1.0, help="pause between runs, like waiting for BOOT")
    args = parser.parse_args(argv)

    settings = load_settings(args.config)
    if args.mode:
        settings = replace(settings, run=replace(settings.run, mode=args.mode))
    if args.detector:
        settings = replace(settings, run=replace(settings.run, detector=args.detector))
    if args.loop:
        settings = replace(settings, stream=replace(settings.stream, loop_files=True))

    print_versions()
    camera = open_camera(settings, args.source)
    # On the robot the camera starts long before the first BOOT press; here, wait for it.
    if camera.wait_for_frame(timeout_s=settings.stream.connect_timeout_s + 2.0) is None:
        print(f"no frames from {args.source}: {camera.status().reason}")
        camera.close()
        return 1
    vision = make_vision(settings)
    robot = DryRobot()
    display = Display(settings, args.show, args.save_dir) if (args.show or args.save_dir) else None
    recording = Recording(camera, args.record) if args.record else None
    if recording is not None:
        recording.start()
    runs = 0
    try:
        while True:
            robot.press_boot()
            runs += 1
            print(f"--- run {runs}: BOOT pressed ({settings.run.mode}, {settings.run.detector} detector) ---")
            summary = run_mode(robot, camera, vision, settings, on_step=display)
            print(f"--- run {runs} ended by {summary.ended_by}: {summary.reason} "
                  f"({summary.moves} moves, {summary.pushes} pushes) ---")
            if args.once or (args.runs and runs >= args.runs) or camera.status().finished:
                break
            if display is not None and display.quit:
                break
            time.sleep(args.restart_s)
    except KeyboardInterrupt:
        print("stopped by Ctrl+C")
    finally:
        if recording is not None:
            recording.stop()
            print(f"recorded {recording.recorder.count} frames to {args.record}")
        camera.close()
        vision.close()
        if args.show:
            cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
