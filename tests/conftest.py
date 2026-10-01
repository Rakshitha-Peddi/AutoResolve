import os
import sys
import tempfile
from pathlib import Path

# Must be set before anything from `backend` is imported.
os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["MAX_ITERATIONS"] = "3"
os.environ["GOOGLE_SHEET_ID"] = ""
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend.database.session import Base, engine  # noqa: E402
from backend.main import app  # noqa: E402
from backend.orchestrator.engine import StubEngine, set_engine  # noqa: E402


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    set_engine(StubEngine())
    with TestClient(app) as c:
        yield c
