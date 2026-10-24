"""A stand-in for an Edge Impulse .eim model, to test model_runner.py before a real model exists.

Run as `python tools/fake_eim.py SOCKET_PATH`, the way an .eim is started. It listens on that
Unix socket and speaks the same protocol: it answers "hello" like a 96x96 RGB FOMO model with the
labels goal and soccerball, and answers "classify" by reporting the brightest round blob in the
lower part of the picture as a soccerball box, in model pixels, plus any boxes given with
--boxes (the goal's cones in the tests). Every reply ends with a zero byte.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
from typing import Any, Dict, List

import numpy as np


def find_ball(features: List[int], width: int, height: int) -> List[Dict[str, Any]]:
    packed = np.asarray(features, dtype=np.uint32).reshape(height, width)
    r, g, b = (packed >> 16) & 0xFF, (packed >> 8) & 0xFF, packed & 0xFF
    lo = np.minimum(np.minimum(r, g), b).astype(np.int32)
    hi = np.maximum(np.maximum(r, g), b).astype(np.int32)
    white = (lo > 150) & (hi - lo < 70)
    white[: height // 2] = False  # the ball lies on the floor, below the wall
    ys, xs = np.nonzero(white)
    if len(xs) < 3:
        return []
    cx, cy = float(xs.mean()), float(ys.mean())
    return [{"label": "soccerball", "value": 0.9, "x": int(round(cx - 4)), "y": int(round(cy - 4)), "width": 8, "height": 8}]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("socket_path")
    parser.add_argument("--width", type=int, default=96)
    parser.add_argument("--height", type=int, default=96)
    parser.add_argument("--channels", type=int, default=3)
    parser.add_argument("--resize-mode", default="squash")
    parser.add_argument("--labels", default="goal,soccerball")
    parser.add_argument("--die-after", type=int, help="exit after this many classify calls")
    parser.add_argument(
        "--boxes",
        default="[]",
        help='more boxes for every answer, as JSON [["goal", x, y, confidence], ...] in model pixels; each is 8 by 8 like FOMO\'s',
    )
    args = parser.parse_args()
    extra = [
        {"label": label, "value": float(value), "x": int(x), "y": int(y), "width": 8, "height": 8}
        for label, x, y, value in json.loads(args.boxes)
    ]

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(args.socket_path)
    server.listen(1)
    conn, _ = server.accept()
    decoder = json.JSONDecoder()
    buffer = ""
    classified = 0
    try:
        while True:
            data = conn.recv(65536)
            if not data:
                return
            buffer += data.decode("utf-8")
            while buffer.strip():
                try:
                    message, end = decoder.raw_decode(buffer.lstrip())
                except json.JSONDecodeError:
                    break  # wait for the rest of the message
                buffer = buffer.lstrip()[end:]
                reply: Dict[str, Any] = {"id": message.get("id"), "success": True}
                if "hello" in message:
                    reply["model_parameters"] = {
                        "image_input_width": args.width,
                        "image_input_height": args.height,
                        "image_channel_count": args.channels,
                        "image_resize_mode": args.resize_mode,
                        "labels": args.labels.split(","),
                        "model_type": "constrained_object_detection",
                    }
                    reply["project"] = {"name": "fake model for tests", "id": 0}
                elif "classify" in message:
                    if args.die_after is not None and classified >= args.die_after:
                        os._exit(3)
                    classified += 1
                    boxes = find_ball(message["classify"], args.width, args.height) + extra
                    reply["result"] = {"bounding_boxes": boxes}
                    reply["timing"] = {"dsp": 0, "classification": 1, "anomaly": 0}
                else:
                    reply = {"id": message.get("id"), "success": False, "error": "unknown message"}
                conn.sendall(json.dumps(reply).encode("utf-8") + b"\x00")
    except KeyboardInterrupt:
        pass
    finally:
        conn.close()
        server.close()
        try:
            os.unlink(args.socket_path)
        except OSError:
            pass


if __name__ == "__main__":
    sys.exit(main())
