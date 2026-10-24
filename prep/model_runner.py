"""Run a trained Edge Impulse model (.eim) and report the ball and the goal like the color detector.

An .eim file is a self-contained program. This runner starts it with a socket path and talks to
it over that Unix socket with the same JSON messages as Edge Impulse's own Python SDK
(edge_impulse_linux/runner.py), using only the standard library and numpy:

1. start `model.eim SOCKET_PATH` and wait for the socket to appear;
2. send {"hello": 1, "id": 1} to learn the input size, channel count and resize mode;
3. for each frame, resize it the way the model was trained, pack every pixel as
   (R << 16) + (G << 8) + B, and send {"classify": [...], "id": n};
4. read each reply up to its closing zero byte. Bounding boxes come back in the model's input
   pixels; they are mapped back to frame pixels here.

FOMO models (the guide's choice) report object centers as small fixed-size boxes, so their
"radius" says nothing about distance; the controller also judges closeness by height in frame.
The organizers' model boxes each cone of the goal on its own, so the goal is reported at the
midpoint of the two most confident goal boxes, and one box alone counts as no goal.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import tempfile
import time
from dataclasses import dataclass, fields, replace
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

from detector import Detection, Sighting, midpoint

Box = Dict[str, Any]
Mapper = Callable[[float, float], Tuple[float, float]]


@dataclass(frozen=True)
class ModelConfig:
    path: str = "models/robocar.eim"
    ball_labels: Tuple[str, ...] = ("soccerball", "soccer_ball")
    goal_labels: Tuple[str, ...] = ("goal",)
    min_confidence: float = 0.45
    start_timeout_s: float = 15.0
    call_timeout_s: float = 2.0

    @classmethod
    def from_dict(cls, raw: Dict[str, Any], base_dir: Optional[Path] = None) -> "ModelConfig":
        """Settings from robocar_config.json; a relative model path is relative to base_dir."""
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown model settings: {sorted(unknown)}")
        values = dict(raw)
        for key in ("ball_labels", "goal_labels"):
            if key in values:
                values[key] = tuple(values[key])
        if base_dir is not None and "path" in values and not Path(values["path"]).is_absolute():
            values["path"] = str(Path(base_dir) / values["path"])
        cfg = cls(**values)
        if not 0.0 <= cfg.min_confidence <= 1.0:
            raise ValueError("min_confidence must be between 0 and 1")
        if cfg.start_timeout_s <= 0 or cfg.call_timeout_s <= 0:
            raise ValueError("the model timeouts must be positive")
        if not cfg.ball_labels:
            raise ValueError("ball_labels can't be empty")
        return cfg


class EimRunner:
    """One running .eim process and its socket connection."""

    def __init__(
        self,
        model_path: str,
        command: Optional[Sequence[str]] = None,
        start_timeout_s: float = 15.0,
        call_timeout_s: float = 2.0,
    ) -> None:
        self.model_path = model_path
        self.command = list(command) if command else [model_path]
        self.start_timeout_s = start_timeout_s
        self.call_timeout_s = call_timeout_s
        self.process: Optional[subprocess.Popen] = None
        self._sock: Optional[socket.socket] = None
        self._tempdir: Optional[str] = None
        self._log: Optional[Any] = None
        self._id = 0

    def start(self) -> Dict[str, Any]:
        own_model = self.command == [self.model_path]
        if own_model:
            _check_exists(self.model_path)
        self._tempdir = tempfile.mkdtemp(prefix="eim-")
        if own_model:
            self.command = [_runnable(self.model_path, self._tempdir)]
        socket_path = os.path.join(self._tempdir, "runner.sock")
        self._log = open(os.path.join(self._tempdir, "runner.log"), "wb")
        self.process = subprocess.Popen(
            self.command + [socket_path], stdout=self._log, stderr=subprocess.STDOUT
        )
        deadline = time.monotonic() + self.start_timeout_s
        while not os.path.exists(socket_path):
            if self.process.poll() is not None:
                raise RuntimeError(f"the model exited with code {self.process.returncode}: {self._log_tail()}")
            if time.monotonic() > deadline:
                self.stop()
                raise RuntimeError(f"the model did not open its socket within {self.start_timeout_s:g} s")
            time.sleep(0.05)
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(self.call_timeout_s)
        self._sock.connect(socket_path)
        return self.send({"hello": 1})

    @property
    def alive(self) -> bool:
        return self.process is not None and self.process.poll() is None and self._sock is not None

    def classify(self, features: List[int]) -> Dict[str, Any]:
        return self.send({"classify": features})

    def send(self, message: Dict[str, Any]) -> Dict[str, Any]:
        if self._sock is None:
            raise RuntimeError("the model is not running")
        self._id += 1
        message = dict(message, id=self._id)
        self._sock.sendall(json.dumps(message).encode("utf-8"))
        data = bytearray()
        while b"\x00" not in data:
            chunk = self._sock.recv(65536)
            if not chunk:
                raise ConnectionError(f"the model closed its socket: {self._log_tail()}")
            data += chunk
        text = bytes(data[: data.index(b"\x00")]).decode("utf-8")
        reply, _ = json.JSONDecoder().raw_decode(text[text.index("{") :])
        if reply.get("id") != self._id:
            raise RuntimeError(f"the model answered message {reply.get('id')}, expected {self._id}")
        if not reply.get("success", False):
            raise RuntimeError(f"the model reported an error: {reply.get('error', 'unknown')}")
        reply.pop("id", None)
        reply.pop("success", None)
        return reply

    def stop(self) -> None:
        if self._sock is not None:
            self._sock.close()
            self._sock = None
        if self.process is not None and self.process.poll() is None:
            self.process.send_signal(signal.SIGINT)  # what Edge Impulse's SDK sends
            try:
                self.process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self._log is not None:
            self._log.close()
            self._log = None
        if self._tempdir is not None:
            shutil.rmtree(self._tempdir, ignore_errors=True)
            self._tempdir = None

    def _log_tail(self) -> str:
        if self._tempdir is None:
            return ""
        try:
            if self._log is not None:
                self._log.flush()
            text = Path(self._tempdir, "runner.log").read_text(errors="replace").strip()
        except OSError:
            return ""
        return text[-300:] or "(no output)"


def _check_exists(path: str) -> None:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"no model at {path}; train one (docs/EDGE_IMPULSE.md) or set run.detector to color"
        )


def _runnable(path: str, tempdir: str) -> str:
    """The model as a file this process may start. The guide's `make flash` unzips the app with
    Python's zipfile, which drops the execute bit, so give it back: on the file itself when
    possible, otherwise on a copy in the runner's temporary folder."""
    if not os.access(path, os.X_OK):
        try:
            os.chmod(path, os.stat(path).st_mode | 0o111)
        except OSError:
            pass
    if os.access(path, os.X_OK):
        return path
    copy = os.path.join(tempdir, os.path.basename(path))
    shutil.copyfile(path, copy)
    os.chmod(copy, 0o755)
    return copy


def prepare(
    image_bgr: np.ndarray, width: int, height: int, channels: int, resize_mode: str
) -> Tuple[List[int], Mapper]:
    """Pixels packed the way Edge Impulse expects, and a function mapping model pixels to frame pixels."""
    frame_h, frame_w = image_bgr.shape[:2]
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    if resize_mode == "fit-shortest":
        aspect = width / height
        if frame_w / frame_h > aspect:
            crop_w, crop_h = int(frame_h * aspect), frame_h
        else:
            crop_w, crop_h = frame_w, int(frame_w / aspect)
        x0, y0 = (frame_w - crop_w) // 2, (frame_h - crop_h) // 2
        resized = cv2.resize(rgb[y0 : y0 + crop_h, x0 : x0 + crop_w], (width, height), interpolation=cv2.INTER_AREA)
        sx, sy = crop_w / width, crop_h / height

        def mapper(x: float, y: float) -> Tuple[float, float]:
            return x0 + x * sx, y0 + y * sy

    elif resize_mode == "fit-longest":
        scale = min(width / frame_w, height / frame_h)
        new_w, new_h = int(frame_w * scale), int(frame_h * scale)
        left, top = (width - new_w) // 2, (height - new_h) // 2
        resized = np.zeros((height, width, 3), dtype=np.uint8)
        resized[top : top + new_h, left : left + new_w] = cv2.resize(rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)

        def mapper(x: float, y: float) -> Tuple[float, float]:
            return (x - left) / scale, (y - top) / scale

    else:  # "squash", and the SDK's default when a model does not report its mode
        resized = cv2.resize(rgb, (width, height), interpolation=cv2.INTER_AREA)
        sx, sy = frame_w / width, frame_h / height

        def mapper(x: float, y: float) -> Tuple[float, float]:
            return x * sx, y * sy

    pixels = resized.astype(np.uint32)
    if channels == 1:
        gray = cv2.cvtColor(resized, cv2.COLOR_RGB2GRAY).astype(np.uint32)
        packed = gray * 0x010101
    else:
        packed = (pixels[..., 0] << 16) | (pixels[..., 1] << 8) | pixels[..., 2]
    return packed.flatten().tolist(), mapper


class ModelVision:
    """Same interface as detector.ColorVision: observe(image, timestamp) -> Sighting."""

    def __init__(self, cfg: ModelConfig, command: Optional[Sequence[str]] = None) -> None:
        self.cfg = cfg
        self._command = command
        self.runner: Optional[EimRunner] = None
        self.info: Dict[str, Any] = {}
        self._start()

    def _start(self) -> None:
        self.runner = EimRunner(self.cfg.path, self._command, self.cfg.start_timeout_s, self.cfg.call_timeout_s)
        try:
            self.info = self.runner.start()
        except BaseException:
            self.runner.stop()
            raise
        params = self.info.get("model_parameters", {})
        self.input_w = int(params["image_input_width"])
        self.input_h = int(params["image_input_height"])
        self.channels = int(params.get("image_channel_count", 3))
        self.resize_mode = str(params.get("image_resize_mode", "squash"))
        self.labels = list(params.get("labels", []))
        if self.labels and not set(self.cfg.ball_labels) & set(self.labels):
            print(f"[WARN] none of the ball labels {list(self.cfg.ball_labels)} is in the model's labels {self.labels}")

    def observe(self, image_bgr: np.ndarray, timestamp: Optional[float] = None) -> Sighting:
        if self.runner is None or not self.runner.alive:
            # One restart attempt per frame after a crash; a second failure raises to the run loop.
            if self.runner is not None:
                self.runner.stop()
            self._start()
        assert self.runner is not None
        frame_h, frame_w = image_bgr.shape[:2]
        features, mapper = prepare(image_bgr, self.input_w, self.input_h, self.channels, self.resize_mode)
        try:
            result = self.runner.classify(features).get("result", {})
        except (OSError, RuntimeError, ValueError):
            self.runner.stop()
            raise
        boxes = result.get("bounding_boxes", []) or []
        ball = self._best(boxes, self.cfg.ball_labels, mapper, frame_h, timestamp)
        goal = self._pair(boxes, self.cfg.goal_labels, mapper, frame_h, timestamp)
        return Sighting(ball=ball, goal=goal, width=frame_w, height=frame_h)

    def _best(
        self, boxes: List[Box], labels: Sequence[str], mapper: Mapper, frame_h: int, timestamp: Optional[float]
    ) -> Detection:
        found = self._matches(boxes, labels, mapper, frame_h, timestamp)
        return found[0] if found else Detection.missing(timestamp, candidates=len(boxes))

    def _pair(
        self, boxes: List[Box], labels: Sequence[str], mapper: Mapper, frame_h: int, timestamp: Optional[float]
    ) -> Detection:
        """The goal: the gap between its two most confident cones. With one cone in view there is
        no gap to aim at, so the goal counts as not seen."""
        found = self._matches(boxes, labels, mapper, frame_h, timestamp)
        if len(found) < 2:
            return Detection.missing(timestamp, candidates=len(boxes))
        return replace(midpoint(found[0], found[1]), candidates=len(boxes))

    def _matches(
        self, boxes: List[Box], labels: Sequence[str], mapper: Mapper, frame_h: int, timestamp: Optional[float]
    ) -> List[Detection]:
        """The boxes with one of the labels and enough confidence, in frame pixels, most confident first."""
        found = []
        for box in boxes:
            if box.get("label") not in labels or float(box.get("value", 0)) < self.cfg.min_confidence:
                continue
            x0, y0 = mapper(float(box["x"]), float(box["y"]))
            x1, y1 = mapper(float(box["x"]) + float(box["width"]), float(box["y"]) + float(box["height"]))
            w, h = max(x1 - x0, 1.0), max(y1 - y0, 1.0)
            found.append(
                Detection(
                    found=True,
                    x=(x0 + x1) / 2.0,
                    y=(y0 + y1) / 2.0,
                    radius=max(w, h) / 2.0,
                    width=w,
                    height=h,
                    quality=float(box["value"]),
                    timestamp=timestamp,
                    touches_bottom=y1 >= frame_h - 1,
                    candidates=len(boxes),
                )
            )
        # sorted() keeps the model's order among equal confidences, so a tie goes to the first box.
        return sorted(found, key=lambda d: d.quality, reverse=True)

    def close(self) -> None:
        if self.runner is not None:
            self.runner.stop()
            self.runner = None
