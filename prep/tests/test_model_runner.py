import os
import sys
from pathlib import Path

import numpy as np
import pytest

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


def test_missing_or_non_executable_model_is_explained(tmp_path):
    with pytest.raises(FileNotFoundError, match="docs/EDGE_IMPULSE.md"):
        ModelVision(ModelConfig(path=str(tmp_path / "missing.eim")))
    model = tmp_path / "model.eim"
    model.write_bytes(b"not a program")
    model.chmod(0o644)
    with pytest.raises(PermissionError, match="chmod"):
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
