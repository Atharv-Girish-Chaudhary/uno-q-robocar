"""Tune the color detector with sliders, on a webcam, a video, a recording or the robot's camera.

    uv run python tune.py --source samples/synthetic_field.avi --loop
    uv run python tune.py --source http://192.168.5.1:81/stream     # stop the board's app first
    uv run python tune.py --source recordings/run1 --target goal

Windows: "frame" (the picture with the detection drawn on it), "mask" (the pixels that match)
and "controls" (the sliders). Click the frame to print the HSV value under the cursor.
Keys: s saves this target's section of robocar_config.json (the rest of the file is kept),
r reloads it, p pauses, q quits. The detector is the same one the robot runs.
"""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import cv2
import numpy as np

from detector import ColorDetector, DetectorConfig, HsvRange

HERE = Path(__file__).resolve().parent
RANGE_KEYS = ("H{} low", "H{} high", "S{} low", "S{} high", "V{} low", "V{} high")
RANGE_MAX = (179, 179, 255, 255, 255, 255)
# name, slider maximum
SLIDERS: List[Tuple[str, int]] = (
    [(k.format(1), m) for k, m in zip(RANGE_KEYS, RANGE_MAX)]
    + [("range 2 on", 1)]
    + [(k.format(2), m) for k, m in zip(RANGE_KEYS, RANGE_MAX)]
    + [
        ("band top %", 100),
        ("band bottom %", 100),
        ("blur", 15),
        ("open", 15),
        ("close", 31),
        ("min area", 2000),
        ("min fill %", 100),
        ("min round %", 100),
        ("round from r", 40),
        ("min aspect x10", 100),
        ("max aspect x10", 800),
    ]
)


def to_sliders(cfg: DetectorConfig) -> Dict[str, int]:
    values: Dict[str, int] = {}
    ranges = list(cfg.hsv_ranges)
    for i in (1, 2):
        r = ranges[i - 1] if i <= len(ranges) else ranges[0]
        lows_highs = (r.lower[0], r.upper[0], r.lower[1], r.upper[1], r.lower[2], r.upper[2])
        for key, v in zip(RANGE_KEYS, lows_highs):
            values[key.format(i)] = int(v)
    values["range 2 on"] = 1 if len(ranges) > 1 else 0
    values["band top %"] = int(round(cfg.roi_top_frac * 100))
    values["band bottom %"] = int(round(cfg.roi_bottom_frac * 100))
    values["blur"], values["open"], values["close"] = cfg.blur_ksize, cfg.open_ksize, cfg.close_ksize
    values["min area"] = int(round(cfg.min_area_px))
    values["min fill %"] = int(round(cfg.min_fill_ratio * 100))
    values["min round %"] = int(round(cfg.min_circularity * 100))
    values["round from r"] = int(round(cfg.circularity_min_radius_px))
    values["min aspect x10"] = int(round(cfg.min_aspect * 10))
    values["max aspect x10"] = int(round(cfg.max_aspect * 10))
    return values


def _odd(k: int) -> int:
    return k + 1 if k > 1 and k % 2 == 0 else k


def from_sliders(values: Dict[str, int], base: DetectorConfig) -> DetectorConfig:
    """A valid config from slider positions: even kernels become odd, crossed ends are swapped."""

    def hsv_range(i: int) -> HsvRange:
        v = [values[k.format(i)] for k in RANGE_KEYS]
        pairs = [tuple(sorted(v[j : j + 2])) for j in (0, 2, 4)]
        return HsvRange((pairs[0][0], pairs[1][0], pairs[2][0]), (pairs[0][1], pairs[1][1], pairs[2][1]))

    ranges = [hsv_range(1)] + ([hsv_range(2)] if values["range 2 on"] else [])
    top, bottom = sorted((values["band top %"], values["band bottom %"]))
    if top == bottom:
        bottom = min(100, top + 1) if top < 100 else 100
        top = min(top, bottom - 1)
    lo_aspect, hi_aspect = sorted((max(values["min aspect x10"], 1), max(values["max aspect x10"], 1)))
    cfg = replace(
        base,
        hsv_ranges=tuple(ranges),
        roi_top_frac=top / 100.0,
        roi_bottom_frac=bottom / 100.0,
        blur_ksize=_odd(values["blur"]),
        open_ksize=_odd(values["open"]),
        close_ksize=_odd(values["close"]),
        min_area_px=float(max(values["min area"], 1)),
        min_fill_ratio=values["min fill %"] / 100.0,
        min_circularity=values["min round %"] / 100.0,
        circularity_min_radius_px=float(values["round from r"]),
        min_aspect=lo_aspect / 10.0,
        max_aspect=hi_aspect / 10.0,
    )
    cfg.validate()
    return cfg


def dump_config(data: Any, indent: int = 0) -> str:
    """JSON with short lists and HSV ranges kept on one line, like the hand-written file."""
    pad = "  " * indent
    if isinstance(data, dict):
        if not data:
            return "{}"
        inner = ",\n".join(f'{pad}  {json.dumps(k)}: {dump_config(v, indent + 1)}' for k, v in data.items())
        return "{\n" + inner + f"\n{pad}}}"
    if isinstance(data, list):
        if all(not isinstance(v, (dict, list)) for v in data) or all(
            isinstance(v, dict) and all(not isinstance(x, dict) for x in v.values()) for v in data
        ):
            return json.dumps(data, separators=(", ", ": "))
        return "[\n" + ",\n".join(f"{pad}  {dump_config(v, indent + 1)}" for v in data) + f"\n{pad}]"
    return json.dumps(data)


def save_section(path: Path, section: str, cfg: DetectorConfig) -> None:
    """Replace one section of the config file, keeping the others, with an atomic write."""
    data = json.loads(path.read_text())
    data[section] = cfg.to_dict()
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".tune-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(dump_config(data) + "\n")
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def main(argv: Optional[List[str]] = None) -> int:
    from stream import StreamConfig, open_stream

    parser = argparse.ArgumentParser(description="Tune the color detector with sliders.")
    parser.add_argument("--source", required=True, help="webcam index, video file, recording folder or http:// URL")
    parser.add_argument("--config", default=str(HERE / "robocar_config.json"))
    parser.add_argument("--target", choices=("ball", "goal"), default="ball")
    parser.add_argument("--preset", help="start from a preset in detector_presets.json")
    parser.add_argument("--loop", action="store_true", help="play a video file or recording on repeat")
    args = parser.parse_args(argv)

    config_path = Path(args.config)

    def load() -> DetectorConfig:
        if args.preset:
            presets = json.loads((HERE / "detector_presets.json").read_text())
            return DetectorConfig.from_dict(presets[args.preset])
        return DetectorConfig.from_dict(json.loads(config_path.read_text())[args.target])

    cfg = load()
    stream_cfg = StreamConfig.from_dict(json.loads(config_path.read_text()).get("stream", {}))
    camera = open_stream(args.source, replace(stream_cfg, loop_files=args.loop, max_identical_frames=0))
    cv2.namedWindow("controls", cv2.WINDOW_NORMAL)
    cv2.namedWindow("frame")
    cv2.namedWindow("mask")

    def set_sliders(c: DetectorConfig) -> None:
        for name, value in to_sliders(c).items():
            cv2.setTrackbarPos(name, "controls", value)

    for name, top in SLIDERS:
        cv2.createTrackbar(name, "controls", 0, top, lambda _v: None)
    set_sliders(cfg)
    state: Dict[str, Any] = {"image": None}

    def on_click(event: int, x: int, y: int, *_: Any) -> None:
        image = state["image"]
        if event == cv2.EVENT_LBUTTONDOWN and image is not None:
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            patch = hsv[max(0, y - 2) : y + 3, max(0, x - 2) : x + 3].reshape(-1, 3)
            print(f"HSV at ({x}, {y}): {tuple(int(v) for v in hsv[y, x])}, 5x5 median {tuple(int(v) for v in np.median(patch, axis=0))}")

    cv2.setMouseCallback("frame", on_click)
    paused = False
    print(__doc__.split("\n\n")[2])
    try:
        while True:
            if not paused:
                frame = camera.latest()
                if frame is not None and frame.image is not None:
                    state["image"] = frame.image
            image = state["image"]
            values = {name: cv2.getTrackbarPos(name, "controls") for name, _ in SLIDERS}
            try:
                cfg = from_sliders(values, cfg)
            except ValueError as error:
                print(f"slider settings refused: {error}")
            if image is not None:
                detection, mask = ColorDetector(cfg).analyze(image, None)
                shown = image.copy()
                h = shown.shape[0]
                for frac in (cfg.roi_top_frac, cfg.roi_bottom_frac):
                    cv2.line(shown, (0, int(frac * h)), (shown.shape[1] - 1, int(frac * h)), (200, 120, 40), 1)
                if detection.found:
                    if cfg.shape == "round":
                        cv2.circle(shown, (int(detection.x), int(detection.y)), max(int(detection.radius), 3), (60, 220, 60), 2)
                    else:
                        hw, hh = detection.width / 2, detection.height / 2
                        cv2.rectangle(shown, (int(detection.x - hw), int(detection.y - hh)), (int(detection.x + hw), int(detection.y + hh)), (40, 220, 240), 2)
                    label = f"found q={detection.quality:.2f} r={detection.radius:.0f}"
                else:
                    label = f"not found ({detection.candidates} blobs)"
                cv2.putText(shown, label, (4, 14), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)
                cv2.imshow("frame", shown)
                cv2.imshow("mask", mask)
            key = cv2.waitKey(30) & 0xFF
            if key == ord("q"):
                break
            if key == ord("p"):
                paused = not paused
            if key == ord("r"):
                cfg = load()
                set_sliders(cfg)
                print("reloaded")
            if key == ord("s"):
                save_section(config_path, args.target, cfg)
                print(f"saved the {args.target} section of {config_path}")
    finally:
        camera.close()
        cv2.destroyAllWindows()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
