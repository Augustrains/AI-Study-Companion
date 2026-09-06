"""Keep test scratch files inside the workspace on locked-down Windows hosts."""
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[1] / ".pytest_tmp"
ROOT.mkdir(parents=True, exist_ok=True)
tempfile.tempdir = str(ROOT)
