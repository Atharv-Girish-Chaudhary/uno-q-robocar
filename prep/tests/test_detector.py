import numpy as np
import pytest

from detector import ColorDetector, ColorVision, Detection, DetectorConfig, midpoint
from tools import make_synthetic_video as syn


def detector(presets, name, **overrides):
    raw = dict(presets[name])
    raw.update(overrides)
    return ColorDetector(DetectorConfig.from_dict(raw))


def tolerance(r):
    return max(2.0, 0.1 * r)


@pytest.mark.parametrize(
    "x, y, r",
    [
        (60, 150, 5),
        (60, 150, 7),
        (160, 150, 10),
        (260, 150, 7),
        (160, 175, 20),
        (100, 200, 32),
        (220, 200, 32),
    ],
)
def test_soccer_ball_found_within_tolerance(presets, rng, x, y, r):
    ball = detector(presets, "white_ball")
    for spin in (0.0, 0.7, 1.4):
        image = syn.scene_image(rng, ball=(x, y, r), goal_x=None, spin=spin)
        d = ball.detect(image, timestamp=12.5)
        assert d.found, f"ball at {(x, y, r)} spin {spin} not found"
        assert abs(d.x - x) <= tolerance(r)
        assert abs(d.y - y) <= tolerance(r)
        assert abs(d.radius - r) <= tolerance(r)
        assert d.timestamp == 12.5


def test_ball_cut_by_bottom_edge_still_found(presets, rng):
    ball = detector(presets, "white_ball")
    for spin in (0.0, 0.7, 1.4):
        d = ball.detect(syn.scene_image(rng, ball=(160, 232, 30), spin=spin))
        assert d.found and d.touches_bottom
        assert abs(d.x - 160) <= tolerance(30)


def test_empty_floor_and_goal_are_not_the_ball(presets, rng):
    ball = detector(presets, "white_ball")
    assert not ball.detect(syn.scene_image(rng)).found
    assert not ball.detect(syn.scene_image(rng, goal_x=160)).found


@pytest.mark.parametrize(
    "box", [(140, 160, 40, 40), (130, 170, 60, 12)], ids=["white square", "white bar"]
)
def test_white_shapes_that_are_not_round_are_rejected(presets, rng, box):
    ball = detector(presets, "white_ball")
    for _ in range(3):
        assert not ball.detect(syn.scene_image(rng, box=box)).found


def test_round_white_blob_above_the_search_band_is_ignored(presets, rng):
    image = syn.field()
    syn.draw_soccer_ball(image, 250, 106, 11)  # on the dark field wall, above the floor
    image = syn.jpeg_roundtrip(syn.add_noise(image, rng))
    assert not detector(presets, "white_ball").detect(image).found
    # Switching the band off finds it, so the band is what hides it.
    assert detector(presets, "white_ball", roi_top_frac=0.0).detect(image).found


def test_white_specks_are_too_small(presets, rng):
    image = syn.field()
    for _ in range(60):
        x, y = int(rng.integers(5, 315)), int(rng.integers(130, 235))
        image[y : y + 2, x : x + 2] = syn.WHITE
    image = syn.jpeg_roundtrip(syn.add_noise(image, rng))
    assert not detector(presets, "white_ball").detect(image).found


def red_ball_image(rng, hue):
    image = syn.field()
    syn.draw_red_ball(image, 160, 170, 18, hue)
    return syn.jpeg_roundtrip(syn.add_noise(image, rng))


@pytest.mark.parametrize("hue", [2, 177])
def test_red_ball_on_either_side_of_the_hue_wrap_needs_both_ranges(presets, rng, hue):
    both = detector(presets, "red_ball")
    assert both.detect(red_ball_image(rng, hue)).found
    low_only = dict(presets["red_ball"])
    low_only["hsv_ranges"] = low_only["hsv_ranges"][:1]
    high_only = dict(presets["red_ball"])
    high_only["hsv_ranges"] = high_only["hsv_ranges"][1:]
    other_side = high_only if hue < 90 else low_only
    assert not ColorDetector(DetectorConfig.from_dict(other_side)).detect(
        red_ball_image(rng, hue)
    ).found


def test_goal_detector_finds_the_goal_and_not_the_ball(presets, rng):
    vision = ColorVision(
        DetectorConfig.from_dict(presets["white_ball"]),
        DetectorConfig.from_dict(presets["white_goal"]),
    )
    for goal_x, ball in [(200, (100, 150, 7)), (80, (160, 208, 45)), (160, (240, 190, 25))]:
        seen = vision.observe(syn.scene_image(rng, ball=ball, goal_x=goal_x), timestamp=3.0)
        assert seen.goal.found and abs(seen.goal.x - goal_x) <= 3
        assert seen.ball.found and abs(seen.ball.x - ball[0]) <= tolerance(ball[2])
        assert (seen.width, seen.height) == (syn.WIDTH, syn.HEIGHT)


def test_goal_detector_ignores_a_lone_ball(presets, rng):
    goal = detector(presets, "white_goal")
    assert not goal.detect(syn.scene_image(rng, ball=(160, 170, 20))).found


def test_midpoint_spans_both_cones():
    left = Detection(found=True, x=100.0, y=140.0, width=30.0, height=50.0, quality=0.6, timestamp=1.0)
    right = Detection(found=True, x=240.0, y=150.0, width=20.0, height=30.0, quality=0.9, timestamp=1.0, touches_bottom=True)
    for a, b in ((left, right), (right, left)):  # either order
        goal = midpoint(a, b)
        assert goal.found and (goal.x, goal.y) == (170.0, 145.0)
        assert (goal.width, goal.height) == (165.0, 50.0)  # from 85 to 250, and the taller cone
        assert goal.quality == 0.6 and goal.touches_bottom and goal.timestamp == 1.0


def test_mask_is_empty_outside_the_search_band(presets, rng):
    ball = detector(presets, "white_ball", roi_top_frac=0.6, roi_bottom_frac=0.9)
    mask = ball.mask(syn.scene_image(rng, ball=(160, 200, 40)))
    h = mask.shape[0]
    assert not mask[: int(0.6 * h)].any()
    assert not mask[int(0.9 * h) :].any()


def test_every_preset_and_the_config_sections_load(presets, config):
    for name, raw in presets.items():
        DetectorConfig.from_dict(raw)
    DetectorConfig.from_dict(config["ball"])
    DetectorConfig.from_dict(config["goal"])


def test_config_round_trips(presets):
    cfg = DetectorConfig.from_dict(presets["red_ball"])
    assert DetectorConfig.from_dict(cfg.to_dict()) == cfg


@pytest.mark.parametrize(
    "change, message",
    [
        ({"close_ksize": 4}, "odd"),
        ({"hsv_ranges": [{"lower": [10, 0, 0], "upper": [5, 255, 255]}]}, "lower <= upper"),
        ({"hsv_ranges": [{"lower": [0, 0, 0], "upper": [180, 255, 255]}]}, "lower <= upper"),
        ({"hsv_ranges": []}, "at least one"),
        ({"shape": "triangle"}, "shape"),
        ({"roi_top_frac": 0.8, "roi_bottom_frac": 0.5}, "search band"),
        ({"min_fill_ratio": 1.5}, "between 0 and 1"),
        ({"colour": "red"}, "unknown"),
    ],
)
def test_bad_settings_are_refused(presets, change, message):
    raw = dict(presets["white_ball"])
    raw.update(change)
    with pytest.raises(ValueError, match=message):
        DetectorConfig.from_dict(raw)


def test_detector_handles_a_blank_frame():
    ball = ColorDetector(DetectorConfig.from_dict(
        {"hsv_ranges": [{"lower": [0, 0, 150], "upper": [179, 90, 255]}]}
    ))
    blank = np.zeros((240, 320, 3), dtype=np.uint8)
    d = ball.detect(blank, timestamp=1.0)
    assert not d.found and d.candidates == 0
