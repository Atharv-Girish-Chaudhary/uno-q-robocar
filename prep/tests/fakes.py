"""Stand-ins for the clock, the camera and the robot, so the run loop can be tested on a laptop."""

from typing import Any, List, Optional, Sequence, Tuple

from controller import DIRECTIONS
from detector import Detection, Sighting
from stream import StreamStatus


class FakeClock:
    def __init__(self, t: float = 1000.0) -> None:
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeFrame:
    def __init__(self, seq: int, arrival: float, image: Any) -> None:
        self.seq, self.arrival, self.image, self.jpeg = seq, arrival, image, None


class ScriptedCamera:
    """Frames that 'arrive' at fixed times on a FakeClock; waiting moves the clock forward."""

    def __init__(self, clock: FakeClock, frames: Sequence[Tuple[float, Any]], stale_after_ms: float = 400) -> None:
        self.clock = clock
        self.frames = [FakeFrame(i + 1, t, image) for i, (t, image) in enumerate(frames)]
        self.stale_s = stale_after_ms / 1000.0

    def _newest_at(self, t: float) -> Optional[FakeFrame]:
        newest = None
        for frame in self.frames:
            if frame.arrival <= t:
                newest = frame
            else:
                break
        return newest

    def wait_for_frame(self, newer_than: float = float("-inf"), min_seq: int = 0, timeout_s: float = 1.0):
        now = self.clock()
        deadline = now + timeout_s
        times = [now] + [f.arrival for f in self.frames if now < f.arrival <= deadline]
        for t in times:
            frame = self._newest_at(t)
            if frame is not None and frame.arrival > newer_than and frame.seq >= min_seq:
                self.clock.t = max(self.clock.t, t)
                return frame
        self.clock.t = deadline
        return None

    def latest(self) -> Optional[FakeFrame]:
        return self._newest_at(self.clock())

    def latest_seq(self) -> int:
        frame = self.latest()
        return frame.seq if frame else 0

    @property
    def ended(self) -> bool:
        return not self.frames or self.clock() > self.frames[-1].arrival + self.stale_s

    def status(self, now: Optional[float] = None) -> StreamStatus:
        now = self.clock() if now is None else now
        frame = self._newest_at(now)
        seq = frame.seq if frame else 0
        if frame is None:
            return StreamStatus(False, "no frame yet", None, 0, 0, 0)
        age_ms = (now - frame.arrival) * 1000.0
        if age_ms > self.stale_s * 1000.0:
            return StreamStatus(False, f"no new frame for {age_ms:.0f} ms", age_ms, seq, 0, 0, finished=self.ended)
        return StreamStatus(True, "ok", age_ms, seq, 0, 0)

    def close(self) -> None:
        pass


class PassThroughVision:
    """For frames whose 'image' is already a Sighting."""

    def __init__(self, fail_at_call: Optional[int] = None) -> None:
        self.calls = 0
        self.fail_at_call = fail_at_call

    def observe(self, image: Any, timestamp: Optional[float] = None) -> Sighting:
        self.calls += 1
        if self.fail_at_call is not None and self.calls >= self.fail_at_call:
            raise RuntimeError("detector blew up")
        return image

    def close(self) -> None:
        pass


def sight(ball: Optional[Tuple[float, float, float]] = None, goal_x: Optional[float] = 160.0) -> Sighting:
    if ball is None:
        b = Detection.missing(None)
    else:
        x, y, r = ball
        b = Detection(found=True, x=x, y=y, radius=r, width=2 * r, height=2 * r, quality=0.9)
    g = Detection.missing(None) if goal_x is None else Detection(found=True, x=goal_x, y=110.0, width=70, height=36, quality=0.9)
    return Sighting(ball=b, goal=g, width=320, height=240)


class FakeProgramStopped(Exception):
    pass


class FakeRobot:
    """Records every call. drive() checks the pulse and moves the fake clock like the real wait."""

    def __init__(
        self,
        clock: Optional[FakeClock] = None,
        disable_after_drives: Optional[int] = None,
        raise_after_drives: Optional[int] = None,
        stop_fails: bool = False,
        max_ms: int = 1000,
    ) -> None:
        self.clock = clock
        self.camera: Any = None  # set it to also record the newest frame number at each pulse end
        self.enabled = True
        self.drives: List[Tuple[str, int, int]] = []
        self.drive_ends: List[float] = []
        self.drive_end_seqs: List[int] = []
        self.stops = 0
        self.is_running_calls = 0
        self.disable_after_drives = disable_after_drives
        self.raise_after_drives = raise_after_drives
        self.stop_fails = stop_fails
        self.max_ms = max_ms

    def press_boot(self) -> None:
        self.enabled = True

    def is_running(self) -> bool:
        self.is_running_calls += 1
        return self.enabled

    def drive(self, direction: str, speed: int = 150, ms: int = 500) -> None:
        assert self.enabled, "drive() while the program is disabled"
        assert direction in DIRECTIONS and direction != "stop", direction
        assert 1 <= ms <= self.max_ms, f"unbounded or zero pulse: {ms} ms"
        assert 1 <= speed <= 255, speed
        self.drives.append((direction, speed, ms))
        if self.clock is not None:
            self.clock.advance(ms / 1000.0 + 0.1)  # robot_client.drive waits ms + 100 ms
            self.drive_ends.append(self.clock())
            if self.camera is not None:
                self.drive_end_seqs.append(self.camera.latest_seq())
        if self.disable_after_drives is not None and len(self.drives) >= self.disable_after_drives:
            self.enabled = False
        if self.raise_after_drives is not None and len(self.drives) >= self.raise_after_drives:
            self.enabled = False
            raise FakeProgramStopped()

    def stop(self) -> bool:
        self.stops += 1
        self.enabled = False
        if self.stop_fails:
            raise RuntimeError("Bridge timed out")
        return True
