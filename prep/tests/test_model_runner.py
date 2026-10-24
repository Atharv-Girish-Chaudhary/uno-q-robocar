import json
import os
import sys
from pathlib import Path

import numpy as np
import pytest

import model_runner
from model_runner import EimRunner, ModelConfig, ModelVision, prepare
from tools import make_synthetic_video as syn

FAKE = str(Path(__file__).resolve().parents[1] / "tools" / "fake_eim.py")


def fake_command(*extra):
    return [sys.executable, FAKE, *extra]


def vision(*extra, **cfg):
    return ModelVision(ModelConfig(path="unused.eim", **cfg), command=fake_command(*extra))


def test_handshake_reports_the_model_input():
    v = vision()
    try:
        params = v.info["model_parameters"]
        assert (v.input_w, v.input_h, v.channels) == (96, 96, 3)
        assert params["labels"] == ["goal", "soccerball"]
    finally:
        v.close()


@pytest.mark.parametrize("mode", ["squash", "fit-shortest", "fit-longest"])
def test_ball_box_maps_back_to_frame_pixels(rng, mode):
    v = vision("--resize-mode", mode)
    try:
        for x, y, r in [(200, 180, 20), (90, 200, 25), (160, 170, 15)]:
            seen = v.observe(syn.scene_image(rng, ball=(x, y, r)), timestamp=4.0)
            assert seen.ball.found, (mode, x, y)
            # The fake reports an 8 px box around the white centroid, about 3 to 4 frame px per
            # model px, and the black patches pull the centroid a little.
            assert abs(seen.ball.x - x) <= 6 and abs(seen.ball.y - y) <= 6
            assert seen.ball.timestamp == 4.0 and seen.ball.quality == pytest.approx(0.9)
            assert (seen.width, seen.height) == (syn.WIDTH, syn.HEIGHT)
    finally:
        v.close()


def test_no_ball_means_missing(rng):
    v = vision()
    try:
        seen = v.observe(syn.scene_image(rng))
        assert not seen.ball.found and not seen.goal.found
    finally:
        v.close()


def test_low_confidence_boxes_are_ignored(rng):
    v = vision(min_confidence=0.95)
    try:
        assert not v.observe(syn.scene_image(rng, ball=(160, 180, 20))).ball.found
    finally:
        v.close()


def test_only_the_configured_labels_count(rng):
    # The fake always labels the ball "soccerball" (the guide's name); a model trained on the
    # August dataset says "soccer_ball" instead, which is why both are in the config.
    v = vision(ball_labels=("soccer_ball",))
    try:
        assert not v.observe(syn.scene_image(rng, ball=(160, 180, 20))).ball.found
    finally:
        v.close()


def cones(*boxes):
    """The fake's --boxes option for FOMO-sized goal boxes, each (x, y, confidence) in model pixels."""
    return ("--boxes", json.dumps([["goal", x, y, value] for x, y, value in boxes]))


# Squash stretches the fake's 96 by 96 model picture to 320 by 240: 10/3 frame pixels per model
# pixel across, 2.5 down. Every box is 8 by 8 model pixels, so its center is 4 past its corner.
SX, SY = 320 / 96, 240 / 96


def test_two_cones_give_the_gap_between_them(rng):
    v = vision(*cones((20, 40, 0.8), (60, 44, 0.7)))
    try:
        goal = v.observe(syn.scene_image(rng), timestamp=5.0).goal
        assert goal.found and goal.timestamp == 5.0
        assert goal.x == pytest.approx((24 + 64) / 2 * SX)  # halfway between the two centers
        assert goal.y == pytest.approx((44 + 48) / 2 * SY)
        assert goal.width == pytest.approx((68 - 20) * SX)  # left edge of one to right edge of the other
        assert goal.height == pytest.approx(8 * SY)
        assert goal.quality == pytest.approx(0.7)  # only as sure as the weaker cone
        assert goal.candidates == 2
    finally:
        v.close()


def test_one_cone_is_no_goal(rng):
    # No gap to aim at, so the controller treats the goal as not seen (rules 13 and 14).
    v = vision(*cones((20, 40, 0.8)))
    try:
        goal = v.observe(syn.scene_image(rng)).goal
        assert not goal.found and goal.candidates == 1
    finally:
        v.close()


def test_three_cones_use_the_two_most_confident(rng):
    v = vision(*cones((40, 40, 0.9), (4, 40, 0.6), (80, 40, 0.8)))
    try:
        goal = v.observe(syn.scene_image(rng)).goal
        assert goal.found and goal.x == pytest.approx((44 + 84) / 2 * SX)  # the 0.6 cone is left out
        assert goal.quality == pytest.approx(0.8)
    finally:
        v.close()


def test_a_cone_below_min_confidence_does_not_count(rng):
    v = vision(*cones((20, 40, 0.8), (60, 40, 0.3)))  # min_confidence is 0.45
    try:
        assert not v.observe(syn.scene_image(rng)).goal.found
    finally:
        v.close()


def test_the_ball_keeps_its_single_most_confident_box(rng):
    # A weaker second ball box and two cones change nothing about the ball.
    v = vision("--boxes", json.dumps([["soccerball", 10, 70, 0.6], ["goal", 20, 40, 0.8], ["goal", 60, 40, 0.7]]))
    try:
        seen = v.observe(syn.scene_image(rng, ball=(200, 180, 20)))
        assert seen.ball.found and seen.ball.quality == pytest.approx(0.9)  # the fake's own ball box
        assert abs(seen.ball.x - 200) <= 6 and abs(seen.ball.y - 180) <= 6
        assert seen.goal.found
    finally:
        v.close()


def test_a_crashed_model_raises_then_restarts(rng):
    v = vision("--die-after", "2")
    try:
        image = syn.scene_image(rng, ball=(160, 180, 20))
        assert v.observe(image).ball.found
        assert v.observe(image).ball.found
        with pytest.raises((ConnectionError, OSError, RuntimeError)):
            v.observe(image)
        assert v.observe(image).ball.found  # a fresh process answers again
    finally:
        v.close()


def test_close_stops_the_process_and_cleans_up():
    runner = EimRunner("unused.eim", command=fake_command())
    runner.start()
    process, tempdir = runner.process, runner._tempdir
    runner.stop()
    assert process.poll() is not None
    assert not os.path.exists(tempdir)


def stand_in_model(path):
    """A .eim stand-in that starts the fake model, saved without its run permission, the way
    make flash's unzip leaves a real one."""
    path.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{FAKE}" "$@"\n')
    path.chmod(0o644)
    return path


def test_missing_model_is_explained(tmp_path):
    with pytest.raises(FileNotFoundError, match="docs/EDGE_IMPULSE.md"):
        ModelVision(ModelConfig(path=str(tmp_path / "missing.eim")))


def test_model_without_its_run_permission_still_starts(tmp_path):
    model = stand_in_model(tmp_path / "model.eim")
    v = ModelVision(ModelConfig(path=str(model)))
    try:
        assert v.info["model_parameters"]["labels"] == ["goal", "soccerball"]
    finally:
        v.close()
    assert os.access(model, os.X_OK)  # restored on the file, so the next start needs nothing


def test_model_that_cannot_be_changed_runs_from_a_copy(tmp_path, monkeypatch):
    model = stand_in_model(tmp_path / "model.eim")
    real_chmod = os.chmod

    def read_only_app_folder(path, mode, *args, **kwargs):
        if os.fspath(path) == str(model):
            raise PermissionError("read-only file system")
        return real_chmod(path, mode, *args, **kwargs)

    monkeypatch.setattr(model_runner.os, "chmod", read_only_app_folder)
    v = ModelVision(ModelConfig(path=str(model)))
    try:
        assert v.runner.command[0] != str(model)  # it started the runnable copy
        assert v.info["model_parameters"]["labels"] == ["goal", "soccerball"]
    finally:
        v.close()
    assert not os.access(model, os.X_OK)


def test_model_that_is_not_a_program_fails_loudly(tmp_path):
    model = tmp_path / "model.eim"
    model.write_bytes(b"not a program")
    model.chmod(0o644)
    with pytest.raises(OSError):
        ModelVision(ModelConfig(path=str(model)))


def test_pixels_are_packed_like_the_sdk():
    image = np.array([[[0, 0, 255], [0, 255, 0]], [[255, 0, 0], [10, 20, 30]]], dtype=np.uint8)  # BGR
    features, mapper = prepare(image, 2, 2, 3, "squash")
    assert features == [0xFF0000, 0x00FF00, 0x0000FF, (30 << 16) | (20 << 8) | 10]
    assert mapper(1.0, 1.0) == (1.0, 1.0)
    gray, _ = prepare(image, 2, 2, 1, "squash")
    assert all(f == (f & 0xFF) * 0x010101 for f in gray)


def test_config_resolves_the_model_path(config, tmp_path):
    cfg = ModelConfig.from_dict(config["model"], base_dir=tmp_path)
    assert cfg.path == str(tmp_path / "models" / "robocar.eim")
    assert cfg.ball_labels == ("soccerball", "soccer_ball")
    with pytest.raises(ValueError, match="unknown"):
        ModelConfig.from_dict({"modelpath": "x.eim"})
    with pytest.raises(ValueError, match="min_confidence"):
        ModelConfig.from_dict({"min_confidence": 2})
