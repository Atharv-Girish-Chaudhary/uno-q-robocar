"""Find the ball or the goal in one camera picture by color and shape.

One detector class serves both targets with different settings from robocar_config.json:
a "round" shape for the ball and a "box" shape for the goal. Steps: blur, convert to HSV,
threshold each color range, keep only the search band of rows, clean up with morphology, then
pick the best contour that passes the size and shape checks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Any, Dict, Optional, Tuple

import cv2
import numpy as np

HSV_LIMITS = (179, 255, 255)
SHAPES = ("round", "box")


@dataclass(frozen=True)
class HsvRange:
    """One OpenCV HSV range (H 0 to 179, S and V 0 to 255), lower and upper inclusive."""

    lower: Tuple[int, int, int]
    upper: Tuple[int, int, int]

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "HsvRange":
        lower = tuple(int(v) for v in raw["lower"])
        upper = tuple(int(v) for v in raw["upper"])
        if len(lower) != 3 or len(upper) != 3:
            raise ValueError(f"an HSV range needs three values per end, got {raw}")
        for lo, hi, top in zip(lower, upper, HSV_LIMITS):
            if not 0 <= lo <= hi <= top:
                raise ValueError(
                    f"HSV range {list(lower)} to {list(upper)} must keep 0 <= lower <= upper "
                    f"<= {list(HSV_LIMITS)}"
                )
        return cls(lower, upper)  # type: ignore[arg-type]

    def to_dict(self) -> Dict[str, Any]:
        return {"lower": list(self.lower), "upper": list(self.upper)}


@dataclass(frozen=True)
class DetectorConfig:
    hsv_ranges: Tuple[HsvRange, ...]
    shape: str = "round"
    roi_top_frac: float = 0.0
    roi_bottom_frac: float = 1.0
    blur_ksize: int = 5
    open_ksize: int = 3
    close_ksize: int = 5
    min_area_px: float = 20.0
    max_area_frac: float = 0.5
    min_fill_ratio: float = 0.75
    min_circularity: float = 0.65
    circularity_min_radius_px: float = 6.0
    min_aspect: float = 1.2
    max_aspect: float = 6.0

    @classmethod
    def from_dict(cls, raw: Dict[str, Any]) -> "DetectorConfig":
        known = {name for name in cls.__dataclass_fields__}
        unknown = set(raw) - known
        if unknown:
            raise ValueError(f"unknown detector settings: {sorted(unknown)}")
        ranges = tuple(HsvRange.from_dict(r) for r in raw.get("hsv_ranges", []))
        values = {k: v for k, v in raw.items() if k != "hsv_ranges"}
        cfg = cls(hsv_ranges=ranges, **values)
        cfg.validate()
        return cfg

    def validate(self) -> None:
        if not self.hsv_ranges:
            raise ValueError("a detector needs at least one HSV range")
        if self.shape not in SHAPES:
            raise ValueError(f"shape must be one of {SHAPES}, got {self.shape!r}")
        if not 0.0 <= self.roi_top_frac < self.roi_bottom_frac <= 1.0:
            raise ValueError("the search band needs 0 <= roi_top_frac < roi_bottom_frac <= 1")
        for name in ("blur_ksize", "open_ksize", "close_ksize"):
            k = getattr(self, name)
            if k < 0 or (k > 1 and k % 2 == 0):
                raise ValueError(f"{name} must be 0, 1 or an odd number, got {k}")
        if self.min_area_px < 1:
            raise ValueError("min_area_px must be at least 1")
        if not 0.0 < self.max_area_frac <= 1.0:
            raise ValueError("max_area_frac must be in (0, 1]")
        for name in ("min_fill_ratio", "min_circularity"):
            if not 0.0 <= getattr(self, name) <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1")
        if not 0.0 < self.min_aspect <= self.max_aspect:
            raise ValueError("the box shape needs 0 < min_aspect <= max_aspect")

    def to_dict(self) -> Dict[str, Any]:
        out: Dict[str, Any] = {"hsv_ranges": [r.to_dict() for r in self.hsv_ranges]}
        for name in self.__dataclass_fields__:
            if name != "hsv_ranges":
                out[name] = getattr(self, name)
        return out


@dataclass(frozen=True)
class Detection:
    """What one detector saw in one frame. Positions and sizes are in frame pixels."""

    found: bool
    x: Optional[float] = None
    y: Optional[float] = None
    radius: Optional[float] = None
    width: Optional[float] = None
    height: Optional[float] = None
    quality: float = 0.0
    timestamp: Optional[float] = None
    touches_bottom: bool = False
    candidates: int = 0

    @classmethod
    def missing(cls, timestamp: Optional[float], candidates: int = 0) -> "Detection":
        return cls(found=False, timestamp=timestamp, candidates=candidates)


@dataclass(frozen=True)
class Sighting:
    """The ball and the goal as seen in one frame of the given size."""

    ball: Detection
    goal: Detection
    width: int
    height: int


def _kernel(size: int) -> Optional[np.ndarray]:
    if size <= 1:
        return None
    return cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (size, size))


class ColorDetector:
    def __init__(self, cfg: DetectorConfig) -> None:
        cfg.validate()
        self.cfg = cfg
        self._open = _kernel(cfg.open_ksize)
        self._close = _kernel(cfg.close_ksize)
        self._ranges = [
            (np.array(r.lower, dtype=np.uint8), np.array(r.upper, dtype=np.uint8))
            for r in cfg.hsv_ranges
        ]

    def mask(self, image_bgr: np.ndarray) -> np.ndarray:
        """The cleaned-up binary mask of pixels that match the color, inside the search band."""
        c = self.cfg
        blurred = image_bgr
        if c.blur_ksize > 1:
            blurred = cv2.GaussianBlur(image_bgr, (c.blur_ksize, c.blur_ksize), 0)
        hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
        mask = np.zeros(hsv.shape[:2], dtype=np.uint8)
        for lower, upper in self._ranges:
            mask |= cv2.inRange(hsv, lower, upper)
        self._apply_band(mask)
        if self._open is not None:
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, self._open)
        if self._close is not None:
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, self._close)
        # Closing can grow a blob back over the band edge, so cut it again.
        self._apply_band(mask)
        return mask

    def _apply_band(self, mask: np.ndarray) -> None:
        h = mask.shape[0]
        top = int(round(self.cfg.roi_top_frac * h))
        bottom = int(round(self.cfg.roi_bottom_frac * h))
        if top > 0:
            mask[:top] = 0
        if bottom < h:
            mask[bottom:] = 0

    def detect(self, image_bgr: np.ndarray, timestamp: Optional[float] = None) -> Detection:
        return self.analyze(image_bgr, timestamp)[0]

    def analyze(
        self, image_bgr: np.ndarray, timestamp: Optional[float] = None
    ) -> Tuple[Detection, np.ndarray]:
        mask = self.mask(image_bgr)
        h, w = mask.shape
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        max_area = self.cfg.max_area_frac * w * h
        best: Optional[Detection] = None
        best_score = -1.0
        for contour in contours:
            bx, by, bw, bh = cv2.boundingRect(contour)
            if bw * bh < self.cfg.min_area_px:
                continue
            pixels = _filled_pixels(contour, bx, by, bw, bh)
            if pixels < self.cfg.min_area_px or pixels > max_area:
                continue
            if self.cfg.shape == "round":
                candidate = self._round(contour, pixels, w, h, timestamp)
            else:
                candidate = self._box(pixels, bx, by, bw, bh, h, timestamp)
            if candidate is None:
                continue
            score = candidate.quality * pixels
            if score > best_score:
                best, best_score = candidate, score
        if best is None:
            return Detection.missing(timestamp, candidates=len(contours)), mask
        return replace(best, candidates=len(contours)), mask

    def _round(
        self, contour: np.ndarray, pixels: int, w: int, h: int, timestamp: Optional[float]
    ) -> Optional[Detection]:
        c = self.cfg
        (cx, cy), r = cv2.minEnclosingCircle(contour)
        fill = min(1.0, pixels / max(_circle_pixels_in_frame(cx, cy, r, w, h), 1))
        if fill < c.min_fill_ratio:
            return None
        quality = fill
        if r >= c.circularity_min_radius_px:
            # Measured on the convex hull: a black patch on the outline of a soccer ball cuts a
            # notch that would otherwise sink the score. A box keeps its corners, and its low
            # fill ratio has already rejected it.
            hull = cv2.convexHull(contour)
            perimeter = cv2.arcLength(hull, True)
            circularity = 0.0
            if perimeter > 0:
                circularity = min(1.0, 4.0 * math.pi * cv2.contourArea(hull) / perimeter**2)
            if circularity < c.min_circularity:
                return None
            quality = fill * circularity
        _, by, _, bh = cv2.boundingRect(contour)
        return Detection(
            found=True,
            x=float(cx),
            y=float(cy),
            radius=float(r),
            width=float(2 * r),
            height=float(2 * r),
            quality=float(quality),
            timestamp=timestamp,
            touches_bottom=by + bh >= h,
        )

    def _box(
        self,
        pixels: int,
        bx: int,
        by: int,
        bw: int,
        bh: int,
        h: int,
        timestamp: Optional[float],
    ) -> Optional[Detection]:
        c = self.cfg
        aspect = bw / bh if bh else 0.0
        if not c.min_aspect <= aspect <= c.max_aspect:
            return None
        fill = pixels / float(bw * bh)
        if fill < c.min_fill_ratio:
            return None
        return Detection(
            found=True,
            x=bx + bw / 2.0,
            y=by + bh / 2.0,
            radius=max(bw, bh) / 2.0,
            width=float(bw),
            height=float(bh),
            quality=float(min(1.0, fill)),
            timestamp=timestamp,
            touches_bottom=by + bh >= h,
        )


def _filled_pixels(contour: np.ndarray, bx: int, by: int, bw: int, bh: int) -> int:
    local = np.zeros((bh, bw), dtype=np.uint8)
    cv2.drawContours(local, [contour], -1, 255, thickness=cv2.FILLED, offset=(-bx, -by))
    return int(cv2.countNonZero(local))


def _circle_pixels_in_frame(cx: float, cy: float, r: float, w: int, h: int) -> int:
    """Pixels of the filled circle that lie inside the frame, so edge-cut balls still score."""
    x0, x1 = max(0, int(math.floor(cx - r)) - 1), min(w, int(math.ceil(cx + r)) + 2)
    y0, y1 = max(0, int(math.floor(cy - r)) - 1), min(h, int(math.ceil(cy + r)) + 2)
    if x1 <= x0 or y1 <= y0:
        return 0
    local = np.zeros((y1 - y0, x1 - x0), dtype=np.uint8)
    center = (int(round(cx)) - x0, int(round(cy)) - y0)
    cv2.circle(local, center, int(round(r)), 255, thickness=-1)
    return int(cv2.countNonZero(local))


class ColorVision:
    """Runs one color detector for the ball and, when configured, one for the goal."""

    def __init__(self, ball: DetectorConfig, goal: Optional[DetectorConfig] = None) -> None:
        self.ball = ColorDetector(ball)
        self.goal = ColorDetector(goal) if goal is not None else None

    def observe(self, image_bgr: np.ndarray, timestamp: Optional[float] = None) -> Sighting:
        h, w = image_bgr.shape[:2]
        ball = self.ball.detect(image_bgr, timestamp)
        goal = self.goal.detect(image_bgr, timestamp) if self.goal else Detection.missing(timestamp)
        return Sighting(ball=ball, goal=goal, width=w, height=h)

    def close(self) -> None:
        """Nothing to release; present so the run loop can treat every vision the same."""
