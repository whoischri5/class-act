"""Point every test at a throwaway database + folders, so tests never touch your real data."""
import os
import sys
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="ucl-tests-"))
# Set TEST_DATABASE_URL to run the tests against Postgres instead of SQLite.
os.environ["DATABASE_URL"] = os.environ.get("TEST_DATABASE_URL") or f"sqlite:///{_tmp / 'test.db'}"
os.environ["SAMPLE_DATA_DIR"] = str(_tmp / "sample")
os.environ["RAW_DATA_DIR"] = str(_tmp / "raw")
os.environ["MODELS_DIR"] = str(_tmp / "models")
os.environ["FOOTBALL_DATA_API_KEY"] = ""  # never call the real API from tests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
