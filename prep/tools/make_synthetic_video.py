"""Draw synthetic pictures of the August Robot Soccer Cup field, and write a test video.

The field: a light room wall at the top, a dark field wall with a blue tape stripe, a green
floor, a small white goal with a net at the foot of the wall, and a black and white soccer ball
on the floor. Every frame gets fresh camera-like noise. The video plays scripted scenes and a
JSON sidecar records where the ball and the goal really are in each frame.

    uv run python tools/make_synthetic_video.py              # writes samples/synthetic_field.avi
"""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

WIDTH, HEIGHT, FPS = 320, 240, 15
WALL_TOP, WALL_BOTTOM = 90, 125
TAPE_ROWS = (100, 108)
ROOM = (214, 218, 222)
WALL = (40, 40, 42)
TAPE_BLUE = (170, 90, 30)
FLOOR = (64, 150, 66)
WHITE = (238, 240, 240)
NET = (200, 204, 204)
BLACK = (28, 28, 30)

Ball = Tuple[float, float, float]


def field(tape: Tuple[int, int, int] = TAPE_BLUE) -> np.ndarray:
    """An empty field, without noise."""
    img = np.empty((HEIGHT, WIDTH, 3), dtype=np.uint8)
    img[:WALL_TOP] = ROOM
    img[WALL_TOP:WALL_BOTTOM] = WALL
    img[TAPE_ROWS[0] : TAPE_ROWS[1]] = tape
    img[WALL_BOTTOM:] = FLOOR
    return img


def draw_goal(img: np.ndarray, cx: float, width: int = 72, height: int = 36) -> None:
    """A white goal with a net, standing on the floor at the foot of the wall."""
    base = WALL_BOTTOM + 6
    top = base - height
    x0, x1 = int(round(cx - width / 2)), int(round(cx + width / 2))
    for x in range(x0, x1, 6):
        cv2.line(img, (x, top), (x, base), NET, 1)
    for y in range(top, base, 6):
        cv2.line(img, (x0, y), (x1, y), NET, 1)
    cv2.rectangle(img, (x0, top), (x1, base), WHITE, 3)


def draw_soccer_ball(img: np.ndarray, cx: float, cy: float, r: float, spin: float = 0.0) -> None:
    """A white ball with black pentagon patches: one in the middle, five around it."""
    center = (int(round(cx)), int(round(cy)))
    cv2.circle(img, center, int(round(r)), WHITE, -1, cv2.LINE_AA)
    patches = [(0.0, 0.0)]
    for k in range(5):
        a = spin + k * 2 * math.pi / 5
        patches.append((0.68 * r * math.cos(a), 0.68 * r * math.sin(a)))
    size = 0.22 * r
    for dx, dy in patches:
        pts = []
        for k in range(5):
            a = spin + math.pi / 2 + k * 2 * math.pi / 5
            pts.append((cx + dx + size * math.cos(a), cy + dy + size * math.sin(a)))
        poly = np.array([[int(round(px)), int(round(py))] for px, py in pts], dtype=np.int32)
        cv2.fillPoly(img, [poly], BLACK, cv2.LINE_AA)


def draw_red_ball(img: np.ndarray, cx: float, cy: float, r: float, hue: int) -> None:
    """A plain ball of one OpenCV hue (0 to 179), for the two-range red test."""
    hsv = np.uint8([[[hue, 215, 205]]])
    bgr = tuple(int(v) for v in cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR)[0, 0])
    cv2.circle(img, (int(round(cx)), int(round(cy))), int(round(r)), bgr, -1, cv2.LINE_AA)


def draw_box(
    img: np.ndarray, x0: int, y0: int, w: int, h: int, color: Tuple[int, int, int] = WHITE
) -> None:
    cv2.rectangle(img, (x0, y0), (x0 + w, y0 + h), color, -1)


def add_noise(img: np.ndarray, rng: np.random.Generator, sigma: float = 5.0) -> np.ndarray:
    noisy = img.astype(np.int16) + rng.normal(0.0, sigma, img.shape).astype(np.int16)
    return np.clip(noisy, 0, 255).astype(np.uint8)


def jpeg_roundtrip(img: np.ndarray, quality: int = 80) -> np.ndarray:
    """Encode and decode like the camera does (it streams JPEG at quality 80)."""
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    if not ok:
        raise RuntimeError("JPEG encoding failed")
    return cv2.imdecode(buf, cv2.IMREAD_COLOR)


def scene_image(
    rng: np.random.Generator,
    ball: Optional[Ball] = None,
    goal_x: Optional[float] = None,
    box: Optional[Tuple[int, int, int, int]] = None,
    spin: float = 0.0,
) -> np.ndarray:
    """One noisy, JPEG-compressed frame of the field."""
    img = field()
    if goal_x is not None:
        draw_goal(img, goal_x)
    if box is not None:
        draw_box(img, *box)
    if ball is not None:
        draw_soccer_ball(img, *ball, spin=spin)
    return jpeg_roundtrip(add_noise(img, rng))


@dataclass(frozen=True)
class Scene:
    name: str
    seconds: float
    ball: Optional[Callable[[float], Ball]]
    goal_x: Optional[float] = 160.0
    box: Optional[Tuple[int, int, int, int]] = None


def _lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


SCENES: List[Scene] = [
    Scene("left_far", 1.4, lambda t: (70.0, 145.0, 7.0)),
    Scene("moving_to_center", 1.0, lambda t: (_lerp(70, 160, t), 145.0, 7.0)),
    Scene("approach", 1.6, lambda t: (160.0, _lerp(145, 205, t), _lerp(7, 44, t))),
    Scene("close_goal_behind", 1.0, lambda t: (160.0, 208.0, 45.0)),
    Scene("close_goal_left", 1.0, lambda t: (160.0, 208.0, 45.0), goal_x=80.0),
    Scene("hidden", 1.0, None),
    Scene("white_box_no_ball", 1.0, None, box=(140, 160, 40, 40)),
    Scene("right_far", 1.4, lambda t: (250.0, 145.0, 7.0)),
]


def render(seed: int = 7) -> Tuple[List[np.ndarray], List[Dict[str, object]]]:
    """All frames of the scripted video, plus the truth for each frame."""
    rng = np.random.default_rng(seed)
    frames: List[np.ndarray] = []
    truth: List[Dict[str, object]] = []
    for scene in SCENES:
        count = int(round(scene.seconds * FPS))
        for i in range(count):
            t = i / max(count - 1, 1)
            ball = scene.ball(t) if scene.ball else None
            frames.append(scene_image(rng, ball, scene.goal_x, scene.box, spin=0.3 * len(frames)))
            truth.append(
                {
                    "frame": len(truth),
                    "time_s": round(len(truth) / FPS, 4),
                    "scene": scene.name,
                    "ball": None if ball is None else [round(v, 2) for v in ball],
                    "goal_x": scene.goal_x,
                }
            )
    return frames, truth


def write_video(path: Path, frames: List[np.ndarray], fps: int = FPS) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fourcc = cv2.VideoWriter_fourcc(*"MJPG")
    writer = cv2.VideoWriter(str(path), cv2.CAP_OPENCV_MJPEG, fourcc, fps, (WIDTH, HEIGHT))
    if not writer.isOpened():
        raise RuntimeError(f"could not open a video writer for {path}")
    writer.set(cv2.VIDEOWRITER_PROP_QUALITY, 90)
    try:
        for frame in frames:
            writer.write(frame)
    finally:
        writer.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--out", default="samples/synthetic_field.avi", help="video file to write")
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()
    out = Path(args.out)
    frames, truth = render(args.seed)
    write_video(out, frames)
    out.with_suffix(".json").write_text(json.dumps({"fps": FPS, "frames": truth}, indent=1))
    print(f"wrote {len(frames)} frames ({len(frames) / FPS:.1f} s) to {out} and its .json truth")


if __name__ == "__main__":
    main()
