import json

import pytest

import demo
import tune
from detector import DetectorConfig
from tools import make_synthetic_video as syn


@pytest.mark.parametrize("name", ["white_ball", "red_ball", "white_goal", "red_tape", "blue_tape"])
def test_sliders_round_trip_every_preset(presets, name):
    cfg = DetectorConfig.from_dict(presets[name])
    assert tune.from_sliders(tune.to_sliders(cfg), cfg) == cfg


def test_sliders_fix_even_kernels_and_crossed_ends(presets):
    cfg = DetectorConfig.from_dict(presets["white_ball"])
    values = tune.to_sliders(cfg)
    values.update({"close": 6, "blur": 4, "H1 low": 120, "H1 high": 20, "band top %": 80, "band bottom %": 40})
    fixed = tune.from_sliders(values, cfg)
    assert (fixed.close_ksize, fixed.blur_ksize) == (7, 5)
    assert fixed.hsv_ranges[0].lower[0] == 20 and fixed.hsv_ranges[0].upper[0] == 120
    assert (fixed.roi_top_frac, fixed.roi_bottom_frac) == (0.4, 0.8)


def test_saving_one_section_keeps_the_rest(tmp_path, config, presets):
    path = tmp_path / "robocar_config.json"
    path.write_text(json.dumps(config, indent=2))
    new_ball = DetectorConfig.from_dict(presets["red_ball"])
    tune.save_section(path, "ball", new_ball)
    saved = json.loads(path.read_text())
    assert DetectorConfig.from_dict(saved["ball"]) == new_ball
    for section in ("run", "goal", "model", "stream", "controller"):
        assert saved[section] == config[section]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["robocar_config.json"]  # no temp file left
    assert '"lower": [0, 120, 70]' in path.read_text()  # ranges stay readable on one line


def test_demo_dry_runs_the_synthetic_video(tmp_path, capsys, config, presets):
    frames, _ = syn.render()
    video = tmp_path / "clip.avi"
    syn.write_video(video, frames[:45])  # left_far, then the ball starts moving: 3 seconds
    # The video shows August's field, so the demo runs August's presets, not the live config's.
    august = tmp_path / "robocar_config.json"
    august.write_text(json.dumps(dict(config, ball=presets["white_ball"], goal=presets["white_goal"])))
    args = ["--source", str(video), "--config", str(august), "--save-dir", str(tmp_path / "frames"), "--restart-s", "0"]
    assert demo.main(args) == 0
    out = capsys.readouterr().out
    assert "--- run 1: BOOT pressed" in out
    assert "STEER   left" in out and "dry run: drive left" in out
    assert "end of video" in out
    assert any((tmp_path / "frames").glob("*.jpg"))


def test_dry_robot_sends_nothing_and_waits_like_the_real_one():
    waits = []
    robot = demo.DryRobot(log=lambda line: None, sleep=waits.append)
    robot.press_boot()
    robot.drive("forward", speed=100, ms=200)
    assert waits == [pytest.approx(0.3)]
    robot.stop()
    with pytest.raises(RuntimeError):
        robot.drive("forward", speed=100, ms=200)
