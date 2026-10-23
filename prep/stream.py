"""Read camera frames in a background thread, keeping only the newest one.

Three sources share one interface:

- MjpegStream reads the robot camera's MJPEG stream (http://192.168.5.1:81/stream). It parses
  the multipart JPEG parts itself, because cv2.VideoCapture buffers frames and hands out old
  ones.
- CaptureStream wraps cv2.VideoCapture for a laptop webcam or a video file.
- FolderStream replays a recording made by FrameRecorder (demo.py --record).

A consumer asks for the newest frame, or waits for one that arrived after a given time, and
calls status() to learn whether the feed has stalled: no new frame for stale_after_ms, the same
JPEG bytes over and over, or a reader error.
"""

from __future__ import annotations

import csv
import hashlib
import http.client
import socket
import threading
import time
from dataclasses import dataclass, fields
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlsplit

import cv2
import numpy as np

JPEG_SOI = b"\xff\xd8"
JPEG_EOI = b"\xff\xd9"


@dataclass(frozen=True)
class StreamConfig:
    url: str = "http://192.168.5.1:81/stream"
    connect_timeout_s: float = 3.0
    read_timeout_s: float = 1.0
    stale_after_ms: float = 400.0
    max_identical_frames: int = 5
    reconnect_delay_s: float = 1.0
    skip_after_connect: int = 2
    loop_files: bool = False

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "StreamConfig":
        known = {f.name for f in fields(cls)}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown stream settings: {sorted(unknown)}")
        cfg = cls(**raw)
        for name in ("connect_timeout_s", "read_timeout_s", "stale_after_ms"):
            if getattr(cfg, name) <= 0:
                raise ValueError(f"{name} must be positive")
        if cfg.reconnect_delay_s < 0 or cfg.max_identical_frames < 0 or cfg.skip_after_connect < 0:
            raise ValueError("reconnect_delay_s, max_identical_frames and skip_after_connect can't be negative")
        return cfg


class Frame:
    """One frame: its sequence number, arrival time (time.monotonic), and the picture.

    Camera frames hold JPEG bytes and decode on first use, so frames the consumer skips cost
    nothing."""

    __slots__ = ("seq", "arrival", "jpeg", "_image", "_decoded")

    def __init__(
        self, seq: int, arrival: float, jpeg: Optional[bytes] = None, image: Optional[np.ndarray] = None
    ) -> None:
        self.seq = seq
        self.arrival = arrival
        self.jpeg = jpeg
        self._image = image
        self._decoded = image is not None

    @property
    def image(self) -> Optional[np.ndarray]:
        if not self._decoded:
            if self.jpeg is not None:
                self._image = cv2.imdecode(np.frombuffer(self.jpeg, dtype=np.uint8), cv2.IMREAD_COLOR)
            self._decoded = True
        return self._image

    def __repr__(self) -> str:
        return f"Frame(seq={self.seq}, arrival={self.arrival:.3f})"


@dataclass(frozen=True)
class StreamStatus:
    ok: bool
    reason: str
    age_ms: Optional[float]
    frames: int
    identical_run: int
    reconnects: int
    finished: bool = False


def parse_boundary(content_type: str) -> Optional[bytes]:
    """The multipart boundary from a Content-Type header, without quotes or a leading '--'."""
    for part in content_type.split(";"):
        key, _, value = part.strip().partition("=")
        if key.lower() == "boundary" and value:
            value = value.strip().strip('"')
            if value.startswith("--"):
                value = value[2:]
            return value.encode("latin-1")
    return None


class MjpegParser:
    """Turns the bytes of a multipart MJPEG body into complete JPEG payloads.

    Feed it chunks of any size, split anywhere. With a known boundary it reads each part's
    headers and uses Content-Length when present, otherwise it cuts at the next boundary.
    Without a boundary it falls back to scanning for JPEG start and end markers. Payloads
    that don't start and end like a JPEG are dropped and counted."""

    MAX_BUFFER = 2_000_000

    def __init__(self, boundary: Optional[bytes] = None) -> None:
        self.delimiter = b"--" + boundary if boundary else None
        self.dropped = 0
        self._buf = bytearray()
        self._state = "seek"
        self._length: Optional[int] = None

    def feed(self, data: bytes) -> List[bytes]:
        self._buf += data
        out: List[bytes] = []
        while True:
            payload = self._next() if self.delimiter else self._next_by_markers()
            if payload is None:
                break
            if payload.startswith(JPEG_SOI) and payload.endswith(JPEG_EOI):
                out.append(payload)
            else:
                self.dropped += 1
        if len(self._buf) > self.MAX_BUFFER:
            self._buf.clear()
            self._state = "seek"
            self.dropped += 1
        return out

    def _next(self) -> Optional[bytes]:
        assert self.delimiter is not None
        if self._state == "seek":
            at = self._buf.find(self.delimiter)
            if at < 0:
                # Keep a tail in case the delimiter is split across chunks.
                keep = len(self.delimiter) - 1
                if len(self._buf) > keep:
                    del self._buf[: len(self._buf) - keep]
                return None
            del self._buf[: at + len(self.delimiter)]
            self._state = "headers"
        if self._state == "headers":
            end = self._buf.find(b"\r\n\r\n")
            if end < 0:
                return None
            self._length = None
            for line in bytes(self._buf[:end]).split(b"\r\n"):
                name, _, value = line.partition(b":")
                if name.strip().lower() == b"content-length":
                    try:
                        self._length = int(value.strip())
                    except ValueError:
                        self._length = None
            del self._buf[: end + 4]
            self._state = "body"
        if self._length is not None:
            if len(self._buf) < self._length:
                return None
            payload = bytes(self._buf[: self._length])
            del self._buf[: self._length]
        else:
            at = self._buf.find(self.delimiter)
            if at < 0:
                return None
            payload = bytes(self._buf[:at]).rstrip(b"\r\n")
            del self._buf[:at]
        self._state = "seek"
        return payload

    def _next_by_markers(self) -> Optional[bytes]:
        start = self._buf.find(JPEG_SOI)
        if start < 0:
            del self._buf[: max(0, len(self._buf) - 1)]
            return None
        end = self._buf.find(JPEG_EOI, start + 2)
        if end < 0:
            del self._buf[:start]
            return None
        payload = bytes(self._buf[start : end + 2])
        del self._buf[: end + 2]
        return payload


class FrameSource:
    """Base class: a daemon thread publishes frames; consumers read the newest one."""

    def __init__(self, cfg: StreamConfig) -> None:
        self.cfg = cfg
        self._cond = threading.Condition()
        self._closed = threading.Event()
        self._latest: Optional[Frame] = None
        self._seq = 0
        self._last_digest: Optional[bytes] = None
        self._identical_run = 0
        self._error = ""
        self._reconnects = 0
        self._finished = False
        self._started = False
        self._thread = threading.Thread(target=self._run_safely, name=type(self).__name__, daemon=True)

    def start(self) -> "FrameSource":
        if not self._started:
            self._started = True
            self._thread.start()
        return self

    def __enter__(self) -> "FrameSource":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _run(self) -> None:
        raise NotImplementedError

    def _run_safely(self) -> None:
        try:
            self._run()
        except BaseException as error:  # the reader must never die without saying why
            self._set_error(f"reader stopped: {_describe(error)}")

    def _set_error(self, reason: str, reconnect: bool = False) -> None:
        with self._cond:
            self._error = reason
            if reconnect:
                self._reconnects += 1
            self._cond.notify_all()

    def _publish(self, jpeg: Optional[bytes] = None, image: Optional[np.ndarray] = None) -> bool:
        """Record a new frame. Byte-identical repeats don't count as new; they only grow a run."""
        payload = jpeg if jpeg is not None else (image.tobytes() if image is not None else b"")
        digest = hashlib.blake2b(payload, digest_size=8).digest()
        arrival = time.monotonic()
        with self._cond:
            if digest == self._last_digest:
                self._identical_run += 1
                self._cond.notify_all()
                return False
            self._last_digest = digest
            self._identical_run = 0
            self._seq += 1
            self._latest = Frame(self._seq, arrival, jpeg=jpeg, image=image)
            self._error = ""
            self._cond.notify_all()
            return True

    def latest(self) -> Optional[Frame]:
        with self._cond:
            return self._latest

    def latest_seq(self) -> int:
        with self._cond:
            return self._seq

    def wait_for_frame(
        self, newer_than: float = float("-inf"), min_seq: int = 0, timeout_s: float = 1.0
    ) -> Optional[Frame]:
        """The newest frame once one arrives after `newer_than` with seq >= `min_seq`, or None."""
        deadline = time.monotonic() + max(0.0, timeout_s)
        with self._cond:
            while True:
                frame = self._latest
                if frame is not None and frame.arrival > newer_than and frame.seq >= min_seq:
                    return frame
                remaining = deadline - time.monotonic()
                if remaining <= 0 or self._closed.is_set() or self._finished:
                    return None
                self._cond.wait(remaining)

    def status(self, now: Optional[float] = None) -> StreamStatus:
        now = time.monotonic() if now is None else now
        with self._cond:
            frame, error = self._latest, self._error
            identical, finished = self._identical_run, self._finished
            frames, reconnects = self._seq, self._reconnects
        age_ms = None if frame is None else max(0.0, (now - frame.arrival) * 1000.0)

        def result(ok: bool, reason: str) -> StreamStatus:
            return StreamStatus(ok, reason, age_ms, frames, identical, reconnects, finished)

        if self._closed.is_set():
            return result(False, "stream closed")
        if finished:
            return result(False, "end of video")
        if self._started and not self._thread.is_alive():
            return result(False, error or "reader stopped")
        if self.cfg.max_identical_frames and identical >= self.cfg.max_identical_frames:
            return result(False, f"{identical} identical frames in a row: the picture is frozen")
        if frame is None:
            return result(False, f"no frame yet ({error})" if error else "no frame yet")
        if age_ms is not None and age_ms > self.cfg.stale_after_ms:
            detail = f" ({error})" if error else ""
            return result(False, f"no new frame for {age_ms:.0f} ms{detail}")
        return result(True, "ok")

    def close(self) -> None:
        self._closed.set()
        self._interrupt()
        with self._cond:
            self._cond.notify_all()
        if self._started and threading.current_thread() is not self._thread:
            self._thread.join(timeout=2.0)

    def _interrupt(self) -> None:
        """Unblock the reader thread; subclasses close their socket or capture here."""


class MjpegStream(FrameSource):
    """The robot camera's stream: connect, parse multipart JPEGs, reconnect on any error."""

    def __init__(self, url: str, cfg: StreamConfig) -> None:
        super().__init__(cfg)
        parts = urlsplit(url)
        if parts.scheme != "http" or not parts.hostname:
            raise ValueError(f"expected an http:// camera URL, got {url!r}")
        self.url = url
        self._host = parts.hostname
        self._port = parts.port or 80
        self._path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        self._sock_lock = threading.Lock()
        self._sock: Optional[socket.socket] = None

    def _run(self) -> None:
        while not self._closed.is_set():
            try:
                self._read_once()
                reason = "the camera ended the stream"
            except (OSError, http.client.HTTPException, ValueError) as error:
                reason = _describe(error)
                if isinstance(error, TimeoutError) and self.latest_seq() == 0:
                    reason += " (is another viewer holding the camera's only stream?)"
            if self._closed.is_set():
                return
            self._set_error(reason, reconnect=True)
            self._closed.wait(self.cfg.reconnect_delay_s)

    def _read_once(self) -> None:
        conn = http.client.HTTPConnection(self._host, self._port, timeout=self.cfg.connect_timeout_s)
        try:
            conn.connect()
            assert conn.sock is not None
            # From here on a silent camera times out after read_timeout_s, not the connect timeout.
            conn.sock.settimeout(self.cfg.read_timeout_s)
            with self._sock_lock:
                self._sock = conn.sock
            if self._closed.is_set():
                return
            conn.request("GET", self._path, headers={"Accept": "multipart/x-mixed-replace"})
            response = conn.getresponse()
            if response.status != 200:
                raise ValueError(f"the camera answered HTTP {response.status}")
            content_type = response.getheader("Content-Type", "")
            if "multipart" not in content_type.lower():
                raise ValueError(f"expected an MJPEG stream, got Content-Type {content_type!r}")
            parser = MjpegParser(parse_boundary(content_type))
            skip = self.cfg.skip_after_connect
            while not self._closed.is_set():
                # read1 returns as soon as some bytes arrive; read(n) would wait for n bytes and
                # hold the end of every frame until the next frame came in.
                chunk = response.read1(65536)
                if not chunk:
                    return
                for jpeg in parser.feed(chunk):
                    if skip > 0:
                        skip -= 1  # the camera's two frame buffers may hold old pictures
                        continue
                    self._publish(jpeg=jpeg)
        finally:
            with self._sock_lock:
                self._sock = None
            conn.close()

    def _interrupt(self) -> None:
        with self._sock_lock:
            sock = self._sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


class CaptureStream(FrameSource):
    """A webcam index or a video file through cv2.VideoCapture. Files play at their own rate."""

    def __init__(self, source: Union[int, str], cfg: StreamConfig) -> None:
        super().__init__(cfg)
        self.source = source
        self._is_file = not isinstance(source, int)

    def _run(self) -> None:
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened() and self._is_file:
            cap = cv2.VideoCapture(str(self.source), cv2.CAP_OPENCV_MJPEG)
        if not cap.isOpened():
            raise RuntimeError(f"could not open {self.source!r}")
        try:
            fps = cap.get(cv2.CAP_PROP_FPS) if self._is_file else 0.0
            period = 1.0 / fps if fps and fps > 0 else 1.0 / 15.0
            due = time.monotonic()
            while not self._closed.is_set():
                ok, image = cap.read()
                if not ok:
                    if self._is_file and self.cfg.loop_files:
                        cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                        continue
                    if self._is_file:
                        with self._cond:
                            self._finished = True
                            self._cond.notify_all()
                        return
                    raise RuntimeError("the webcam stopped delivering frames")
                self._publish(image=image)
                if self._is_file:
                    due += period
                    self._closed.wait(max(0.0, due - time.monotonic()))
        finally:
            cap.release()


class FolderStream(FrameSource):
    """Replays a recording folder (frames.csv plus JPEG files) with its original timing."""

    def __init__(self, folder: Path, cfg: StreamConfig) -> None:
        super().__init__(cfg)
        self.folder = Path(folder)
        index = self.folder / FrameRecorder.INDEX
        if not index.exists():
            raise ValueError(f"{self.folder} has no {FrameRecorder.INDEX}; is it a recording?")
        with index.open(newline="") as fh:
            self._rows = [(float(r["arrival_s"]), r["file"]) for r in csv.DictReader(fh)]

    def _run(self) -> None:
        while not self._closed.is_set():
            start = time.monotonic()
            for arrival_s, name in self._rows:
                if self._closed.wait(max(0.0, start + arrival_s - time.monotonic())):
                    return
                self._publish(jpeg=(self.folder / name).read_bytes())
            if not self.cfg.loop_files:
                with self._cond:
                    self._finished = True
                    self._cond.notify_all()
                return


class FrameRecorder:
    """Saves each new frame as a JPEG with its arrival time, for replay and tuning later."""

    INDEX = "frames.csv"

    def __init__(self, folder: Union[str, Path]) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self._index = (self.folder / self.INDEX).open("w", newline="")
        self._writer = csv.writer(self._index)
        self._writer.writerow(["seq", "arrival_s", "file"])
        self._t0: Optional[float] = None
        self._last_seq = 0
        self.count = 0

    def add(self, frame: Frame) -> None:
        if frame.seq <= self._last_seq:
            return
        self._last_seq = frame.seq
        if self._t0 is None:
            self._t0 = frame.arrival
        data = frame.jpeg
        if data is None:
            image = frame.image
            if image is None:
                return
            ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                return
            data = buf.tobytes()
        name = f"{frame.seq:06d}.jpg"
        (self.folder / name).write_bytes(data)
        self._writer.writerow([frame.seq, f"{frame.arrival - self._t0:.4f}", name])
        self.count += 1

    def close(self) -> None:
        self._index.close()


def open_stream(source: Union[int, str, Path], cfg: Optional[StreamConfig] = None) -> FrameSource:
    """Start the right reader for a camera URL, a webcam index, a video file or a recording."""
    cfg = cfg or StreamConfig()
    if isinstance(source, int) or (isinstance(source, str) and source.isdigit()):
        reader: FrameSource = CaptureStream(int(source), cfg)
    elif str(source).startswith("http://"):
        reader = MjpegStream(str(source), cfg)
    elif Path(source).is_dir():
        reader = FolderStream(Path(source), cfg)
    elif Path(source).is_file():
        reader = CaptureStream(str(source), cfg)
    else:
        raise ValueError(f"no camera URL, webcam, video or recording at {source!r}")
    return reader.start()


def _describe(error: BaseException) -> str:
    if isinstance(error, TimeoutError):
        return "timed out waiting for the camera"
    if isinstance(error, ConnectionRefusedError):
        return "connection refused (is the camera on, and is this machine on its Wi-Fi?)"
    text = str(error)
    return f"{type(error).__name__}: {text}" if text else type(error).__name__
