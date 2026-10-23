import socket
import time

import cv2
import numpy as np
import pytest

from stream import (
    CaptureStream,
    FolderStream,
    FrameRecorder,
    MjpegParser,
    MjpegStream,
    StreamConfig,
    open_stream,
    parse_boundary,
)
from tools import make_synthetic_video as syn
from tools.fake_camera import BOUNDARY, PART_BOUNDARY, FakeCamera


def numbered_jpegs(n):
    """Small JPEGs whose gray level encodes their index, so a test can tell which one arrived."""
    out = []
    for i in range(n):
        img = np.full((24, 32, 3), 3 + 9 * i, dtype=np.uint8)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        assert ok
        out.append(buf.tobytes())
    return out


def frame_number(frame):
    return int(round((float(frame.image.mean()) - 3) / 9))


def body(jpegs, with_length=True):
    out = b""
    for j in jpegs:
        if with_length:
            header = f"Content-Type: image/jpeg\r\nContent-Length: {len(j)}\r\n\r\n"
        else:
            header = "Content-Type: image/jpeg\r\n\r\n"
        out += PART_BOUNDARY + header.encode() + j
    return out


def cfg(**overrides):
    values = dict(
        connect_timeout_s=1.0,
        read_timeout_s=0.5,
        stale_after_ms=200,
        max_identical_frames=3,
        reconnect_delay_s=0.1,
        skip_after_connect=0,
    )
    values.update(overrides)
    return StreamConfig(**values)


def wait_until(predicate, timeout_s=3.0, step_s=0.01):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(step_s)
    return False


# The parser, on the firmware's framing


def test_parser_reads_the_firmware_framing():
    jpegs = numbered_jpegs(3)
    parser = MjpegParser(BOUNDARY.encode())
    assert parser.feed(body(jpegs)) == jpegs


def test_parser_handles_any_split(rng):
    jpegs = numbered_jpegs(5)
    data = body(jpegs)
    for _ in range(20):
        parser = MjpegParser(BOUNDARY.encode())
        out, i = [], 0
        while i < len(data):
            step = int(rng.integers(1, 200))
            out += parser.feed(data[i : i + step])
            i += step
        assert out == jpegs


def test_parser_one_byte_at_a_time():
    jpegs = numbered_jpegs(2)
    parser = MjpegParser(BOUNDARY.encode())
    out = []
    for i in range(len(body(jpegs))):
        out += parser.feed(body(jpegs)[i : i + 1])
    assert out == jpegs


def test_parser_without_content_length_cuts_at_the_next_boundary():
    jpegs = numbered_jpegs(3)
    parser = MjpegParser(BOUNDARY.encode())
    first = parser.feed(body(jpegs, with_length=False))
    assert first == jpegs[:2]  # the last part ends only when the next boundary arrives
    assert parser.feed(PART_BOUNDARY) == jpegs[2:]


def test_parser_skips_garbage_and_drops_broken_jpegs():
    good = numbered_jpegs(2)
    broken = good[0][:-2]  # no end-of-image marker
    parser = MjpegParser(BOUNDARY.encode())
    out = parser.feed(b"HTTP noise before the first part" + body([good[0], broken, good[1]]))
    assert out == good
    assert parser.dropped == 1


def test_parser_without_a_boundary_scans_for_jpeg_markers():
    jpegs = numbered_jpegs(3)
    parser = MjpegParser(None)
    assert parser.feed(body(jpegs)) == jpegs


@pytest.mark.parametrize(
    "header, expected",
    [
        (f"multipart/x-mixed-replace;boundary={BOUNDARY}", BOUNDARY.encode()),
        ('multipart/x-mixed-replace; boundary="frame"', b"frame"),
        ("multipart/x-mixed-replace; boundary=--frame", b"frame"),
        ("image/jpeg", None),
    ],
)
def test_boundary_from_content_type(header, expected):
    assert parse_boundary(header) == expected


# The reader, live against the fake camera


def test_reads_frames_from_the_fake_camera():
    with FakeCamera(numbered_jpegs(10), fps=30) as camera:
        with MjpegStream(camera.url, cfg()) as reader:
            frame = reader.wait_for_frame(min_seq=5, timeout_s=3.0)
            assert frame is not None and frame.image.shape == (24, 32, 3)
            assert reader.status().ok


def test_first_frames_after_connect_are_skipped():
    with FakeCamera(numbered_jpegs(6), fps=30, stall_after=3) as camera:
        with MjpegStream(camera.url, cfg(skip_after_connect=2, stale_after_ms=5000)) as reader:
            frame = reader.wait_for_frame(timeout_s=3.0)
            assert frame is not None
            assert wait_until(lambda: camera.connections == 1)
            time.sleep(0.2)
            assert reader.latest_seq() == 1
            assert frame_number(reader.latest()) == 2


def test_newest_frame_wins_when_the_consumer_is_slow():
    with FakeCamera(numbered_jpegs(20), fps=60) as camera:
        with MjpegStream(camera.url, cfg()) as reader:
            assert reader.wait_for_frame(timeout_s=3.0) is not None
            time.sleep(0.4)
            newest = reader.latest()
            assert newest.seq >= 12  # about 24 frames arrived; only the newest is kept
            later = reader.wait_for_frame(newer_than=newest.arrival, timeout_s=1.0)
            assert later is not None and later.seq > newest.seq


def test_a_stalled_camera_is_reported_quickly():
    with FakeCamera(numbered_jpegs(10), fps=30, stall_after=5) as camera:
        with MjpegStream(camera.url, cfg(stale_after_ms=200, read_timeout_s=5.0)) as reader:
            assert reader.wait_for_frame(min_seq=5, timeout_s=3.0) is not None
            last = reader.latest().arrival
            assert wait_until(lambda: not reader.status().ok, timeout_s=2.0)
            detected = time.monotonic() - last
            assert 0.15 <= detected <= 0.5
            assert "no new frame" in reader.status().reason


def test_a_frozen_picture_is_reported():
    with FakeCamera(numbered_jpegs(10), fps=60, repeat_after=3) as camera:
        with MjpegStream(camera.url, cfg(max_identical_frames=3, stale_after_ms=5000)) as reader:
            assert wait_until(lambda: "identical" in reader.status().reason, timeout_s=3.0)
            assert reader.latest_seq() == 3  # repeats are not new frames


def test_a_dropped_connection_reconnects():
    with FakeCamera(numbered_jpegs(10), fps=60, drop_after=3) as camera:
        with MjpegStream(camera.url, cfg()) as reader:
            assert wait_until(lambda: reader.latest_seq() >= 7, timeout_s=5.0)
            assert camera.connections >= 2
            assert reader.status().reconnects >= 1


def test_a_silent_camera_times_out_and_reconnects():
    with FakeCamera(numbered_jpegs(3), fps=30, stall_after=0) as camera:
        with MjpegStream(camera.url, cfg(read_timeout_s=0.3)) as reader:
            assert wait_until(lambda: reader.status().reconnects >= 1, timeout_s=3.0)
            status = reader.status()
            assert not status.ok and "timed out" in status.reason
            assert "only stream" in status.reason


def test_close_returns_quickly_even_mid_read():
    with FakeCamera(numbered_jpegs(5), fps=30, stall_after=2) as camera:
        reader = MjpegStream(camera.url, cfg(read_timeout_s=10.0)).start()
        assert reader.wait_for_frame(min_seq=2, timeout_s=3.0) is not None
        started = time.monotonic()
        reader.close()
        assert time.monotonic() - started < 1.0
        assert reader.status().reason == "stream closed"


def test_a_refused_connection_is_reported():
    probe = socket.socket()
    probe.bind(("127.0.0.1", 0))
    port = probe.getsockname()[1]
    probe.close()  # nothing listens on this port now
    with MjpegStream(f"http://127.0.0.1:{port}/stream", cfg()) as reader:
        assert wait_until(lambda: "refused" in reader.status().reason, timeout_s=3.0)
        assert not reader.status().ok


def test_second_viewer_waits_until_the_first_leaves():
    with FakeCamera(numbered_jpegs(10), fps=30) as camera:
        first = MjpegStream(camera.url, cfg()).start()
        assert first.wait_for_frame(timeout_s=3.0) is not None
        second = MjpegStream(camera.url, cfg(read_timeout_s=0.3, reconnect_delay_s=0.05)).start()
        try:
            time.sleep(0.6)
            assert second.latest_seq() == 0  # the camera serves one stream at a time
            first.close()
            assert second.wait_for_frame(timeout_s=3.0) is not None
        finally:
            first.close()
            second.close()


# Laptop sources


def synthetic_video(tmp_path, count=12):
    frames, _ = syn.render()
    path = tmp_path / "clip.avi"
    syn.write_video(path, frames[:count], fps=30)
    return path


def test_video_file_plays_to_its_end(tmp_path):
    path = synthetic_video(tmp_path)
    with CaptureStream(str(path), cfg(max_identical_frames=0, stale_after_ms=5000)) as reader:
        assert wait_until(lambda: reader.status().finished, timeout_s=5.0)
        assert reader.latest_seq() == 12
        assert reader.status().reason == "end of video"
        assert reader.latest().image.shape == (syn.HEIGHT, syn.WIDTH, 3)


def test_recording_replays_in_order(tmp_path):
    path = synthetic_video(tmp_path, count=8)
    recorder = FrameRecorder(tmp_path / "rec")
    with CaptureStream(str(path), cfg(stale_after_ms=5000)) as reader:
        seen = 0
        while seen < 8:
            frame = reader.wait_for_frame(min_seq=seen + 1, timeout_s=3.0)
            assert frame is not None
            recorder.add(frame)
            seen = frame.seq
    recorder.close()
    assert recorder.count >= 6  # a slow consumer may skip a frame, the newest wins
    with FolderStream(tmp_path / "rec", cfg(stale_after_ms=5000)) as replay:
        assert wait_until(lambda: replay.status().finished, timeout_s=5.0)
        assert replay.latest_seq() == recorder.count


def test_open_stream_picks_the_reader(tmp_path):
    path = synthetic_video(tmp_path, count=3)
    with open_stream(str(path), cfg()) as reader:
        assert isinstance(reader, CaptureStream)
    with open_stream("http://127.0.0.1:9/stream", cfg()) as reader:
        assert isinstance(reader, MjpegStream)
    with pytest.raises(ValueError, match="no camera URL"):
        open_stream(str(tmp_path / "missing.avi"), cfg())


def test_stream_settings_validate(config):
    assert StreamConfig.from_dict(config["stream"]).url.startswith("http://192.168.5.1")
    with pytest.raises(ValueError, match="unknown"):
        StreamConfig.from_dict({"stale_ms": 100})
    with pytest.raises(ValueError, match="positive"):
        StreamConfig.from_dict({"stale_after_ms": 0})
