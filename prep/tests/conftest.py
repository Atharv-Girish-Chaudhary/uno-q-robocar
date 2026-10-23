import json
from pathlib import Path

import numpy as np
import pytest

PREP = Path(__file__).resolve().parents[1]


@pytest.fixture
def rng():
    return np.random.default_rng(1234)


@pytest.fixture
def presets():
    return json.loads((PREP / "detector_presets.json").read_text())


@pytest.fixture
def config():
    return json.loads((PREP / "robocar_config.json").read_text())
