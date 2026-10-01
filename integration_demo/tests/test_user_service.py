import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.user_service import get_user_name


def test_get_user_name():
    assert get_user_name({"name": "Albert"}) == "Albert"
