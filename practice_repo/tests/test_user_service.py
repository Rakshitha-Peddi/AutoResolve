from src.user_service import get_user_name


def test_get_user_name():
    assert get_user_name({"name": "Albert"}) == "Albert"
