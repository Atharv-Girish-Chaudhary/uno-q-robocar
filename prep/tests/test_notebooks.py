"""Run each notebook top to bottom, the way VS Code would.

The notebooks check themselves against detector.py and controller.decide, so a change that makes
an explanation drift from the code fails here. Each notebook runs in memory, from notebooks/ like
in VS Code, and the saved file with its pictures is never rewritten.
"""

from pathlib import Path

import nbformat
import pytest
from nbclient import NotebookClient

NOTEBOOKS = Path(__file__).resolve().parents[1] / "notebooks"


@pytest.mark.parametrize("name", ["01_how_the_detector_sees.ipynb"])
def test_notebook_runs_top_to_bottom(name):
    nb = nbformat.read(NOTEBOOKS / name, as_version=4)
    client = NotebookClient(nb, timeout=300, kernel_name="python3", resources={"metadata": {"path": str(NOTEBOOKS)}})
    client.execute()
