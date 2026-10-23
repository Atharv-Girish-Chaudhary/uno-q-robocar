from importlib import metadata


def installed(name):
    try:
        metadata.version(name)
        return True
    except metadata.PackageNotFoundError:
        return False


def test_exactly_one_opencv_build_is_installed():
    # Both builds provide the same cv2 module; with both installed, whichever was installed
    # last silently wins. The dev venv has the GUI build, the board has the headless one.
    builds = [n for n in ("opencv-python", "opencv-python-headless") if installed(n)]
    assert len(builds) == 1, f"found {builds}; keep exactly one OpenCV build per environment"
