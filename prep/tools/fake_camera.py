"""Serve frames as an MJPEG stream in the robot camera's exact format, for testing.

The ESP32-S3 firmware (upstream/robocar/camera/HiwonderCamStream/HiwonderCamStream.ino) answers
GET /stream with multipart/x-mixed-replace and the boundary 123456789000000000000987654321.
Each frame goes out as "\\r\\n--BOUNDARY\\r\\n", then "Content-Type: image/jpeg\\r\\n
Content-Length: N\\r\\n\\r\\n", then the JPEG, all inside HTTP/1.1 chunked encoding, and it serves
one client at a time. This server does the same, and can also stall, repeat one JPEG, or drop
the connection, to exercise the stream reader's fault handling.

    uv run python tools/fake_camera.py --source samples/synthetic_field.avi --loop
    uv run python demo.py --source http://127.0.0.1:8081/stream
"""

from __future__ import annotations

import argparse
import http.server
import threading
import time
from pathlib import Path
from typing import List, Optional, Sequence

import cv2

BOUNDARY = "123456789000000000000987654321"
CONTENT_TYPE = f"multipart/x-mixed-replace;boundary={BOUNDARY}"
PART_BOUNDARY = f"\r\n--{BOUNDARY}\r\n".encode()
PART_HEADER = "Content-Type: image/jpeg\r\nContent-Length: {}\r\n\r\n"
PART_HEADER_NO_LENGTH = "Content-Type: image/jpeg\r\n\r\n"


class FakeCamera:
    """A one-client MJPEG server. Use as a context manager, or start() and stop()."""

    def __init__(
        self,
        frames: Sequence[bytes],
        fps: float = 15.0,
        host: str = "127.0.0.1",
        port: int = 0,
        loop: bool = True,
        stall_after: Optional[int] = None,
        repeat_after: Optional[int] = None,
        drop_after: Optional[int] = None,
        content_length: bool = True,
    ) -> None:
        if not frames:
            raise ValueError("the fake camera needs at least one JPEG frame")
        self.frames = list(frames)
        self.fps = fps
        self.loop = loop
        self.stall_after = stall_after
        self.repeat_after = repeat_after
        self.drop_after = drop_after
        self.content_length = content_length
        self.connections = 0
        self.stopping = threading.Event()
        # HTTPServer (not the threading variant) handles one request at a time, so a second
        # viewer waits with no answer, the way the real camera behaves.
        self.server = http.server.HTTPServer((host, port), self._handler_class())
        self._thread: Optional[threading.Thread] = None

    @property
    def url(self) -> str:
        host, port = self.server.server_address[:2]
        return f"http://{host}:{port}/stream"

    def start(self) -> "FakeCamera":
        self._thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self._thread.start()
        return self

    def stop(self) -> None:
        self.stopping.set()
        self.server.shutdown()
        self.server.server_close()
        if self._thread is not None:
            self._thread.join(timeout=2.0)

    def __enter__(self) -> "FakeCamera":
        return self.start()

    def __exit__(self, *exc: object) -> None:
        self.stop()

    def _handler_class(self) -> type:
        camera = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args: object) -> None:
                pass

            def do_GET(self) -> None:  # noqa: N802 (http.server's naming)
                if self.path == "/":
                    body = b"<html><body><img src='/stream'></body></html>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(body)))
                    self.end_headers()
                    self.wfile.write(body)
                    return
                if self.path != "/stream":
                    self.send_error(404)
                    return
                camera.connections += 1
                self.send_response(200)
                self.send_header("Content-Type", CONTENT_TYPE)
                self.send_header("Transfer-Encoding", "chunked")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                try:
                    camera._serve(self)
                except (BrokenPipeError, ConnectionResetError):
                    pass
                self.close_connection = True

        return Handler

    def _serve(self, handler: http.server.BaseHTTPRequestHandler) -> None:
        period = 1.0 / self.fps
        sent = 0
        index = 0
        frozen: Optional[bytes] = None
        due = time.monotonic()
        while not self.stopping.is_set():
            if self.drop_after is not None and sent >= self.drop_after:
                return
            if self.stall_after is not None and sent >= self.stall_after:
                self.stopping.wait(0.05)
                continue
            if index >= len(self.frames):
                if not self.loop:
                    _chunk(handler, b"")
                    return
                index = 0
            jpeg = self.frames[index]
            if self.repeat_after is not None and sent >= self.repeat_after:
                frozen = frozen or self.frames[max(0, index - 1)]
                jpeg = frozen
            header = PART_HEADER.format(len(jpeg)) if self.content_length else PART_HEADER_NO_LENGTH
            _chunk(handler, PART_BOUNDARY)
            _chunk(handler, header.encode())
            _chunk(handler, jpeg)
            handler.wfile.flush()
            sent += 1
            index += 1
            due += period
            self.stopping.wait(max(0.0, due - time.monotonic()))


def _chunk(handler: http.server.BaseHTTPRequestHandler, data: bytes) -> None:
    """One piece of HTTP/1.1 chunked encoding, the way the firmware's httpd_resp_send_chunk sends it."""
    handler.wfile.write(f"{len(data):X}\r\n".encode() + data + b"\r\n")


def frames_from(source: str, quality: int = 80) -> List[bytes]:
    """JPEG frames from a video file, a folder of .jpg files, or 'synthetic'."""
    if source == "synthetic":
        from tools import make_synthetic_video as syn

        images, _ = syn.render()
        return [_encode(img, quality) for img in images]
    path = Path(source)
    if path.is_dir():
        return [p.read_bytes() for p in sorted(path.glob("*.jpg"))]
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        cap = cv2.VideoCapture(str(path), cv2.CAP_OPENCV_MJPEG)
    frames = []
    while True:
        ok, img = cap.read()
        if not ok:
            break
        frames.append(_encode(img, quality))
    cap.release()
    return frames


def _encode(image, quality: int) -> bytes:
    ok, buf = cv2.imencode(".jpg", image, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return buf.tobytes()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve a video as the robot camera's MJPEG stream.")
    parser.add_argument("--source", default="synthetic", help="video file, folder of .jpg, or 'synthetic'")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8081)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--loop", action="store_true", help="start over at the end")
    parser.add_argument("--stall-after", type=int, help="stop sending after N frames, connection open")
    parser.add_argument("--repeat-after", type=int, help="send the same JPEG forever after N frames")
    parser.add_argument("--drop-after", type=int, help="close the connection after N frames")
    args = parser.parse_args()
    frames = frames_from(args.source)
    camera = FakeCamera(
        frames,
        fps=args.fps,
        host=args.host,
        port=args.port,
        loop=args.loop,
        stall_after=args.stall_after,
        repeat_after=args.repeat_after,
        drop_after=args.drop_after,
    )
    print(f"serving {len(frames)} frames at {camera.url} (Ctrl+C to stop)")
    try:
        camera.server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        camera.stopping.set()
        camera.server.server_close()


if __name__ == "__main__":
    main()
