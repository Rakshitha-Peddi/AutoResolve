
"""Tests for sensitive Python source detection."""

from ai_agent.retriever import RepositoryRetriever
from ai_agent.source_safety import contains_sensitive_source


def test_rejects_hardcoded_api_key():
    source = 'API_KEY = "example-secret-value"\n'

    assert contains_sensitive_source(source) is True


def test_rejects_hardcoded_password_dictionary():
    source = 'config = {"password": "example-value"}\n'

    assert contains_sensitive_source(source) is True


def test_allows_environment_variable_reference():
    source = (
        "import os\n"
        'API_KEY = os.getenv("API_KEY")\n'
    )

    assert contains_sensitive_source(source) is False


def test_rejects_private_key_marker():
    source = (
        'data = """-----BEGIN PRIVATE KEY-----\n'
        'example\n'
        '-----END PRIVATE KEY-----"""\n'
    )

    assert contains_sensitive_source(source) is True


def test_sensitive_file_never_enters_retrieved_context(tmp_path):
    (tmp_path / "unsafe.py").write_text(
        'API_KEY = "example-secret-value"\n'
        "def find_user():\n"
        "    return 1\n"
    )

    (tmp_path / "safe.py").write_text(
        "def find_user():\n"
        "    return 2\n"
    )

    results = RepositoryRetriever().retrieve(
        str(tmp_path),
        "find_user",
    )

    paths = [path for _, path, _ in results]

    assert "safe.py" in paths
    assert "unsafe.py" not in paths
    assert all(
        "example-secret-value" not in content
        for _, _, content in results
    )
