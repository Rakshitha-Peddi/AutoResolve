"""Collision prevention for independent AutoResolve repair workspaces."""
import re
from unittest.mock import Mock, patch

import pytest

from backend.orchestrator.real_engine import RealFixEngine


def test_independent_clones_never_reuse_generated_regression_path(tmp_path):
    engine = object.__new__(RealFixEngine)
    names = set()
    for n in range(30):
        repo = tmp_path / f"repo_{n}"
        repo.mkdir()
        result = engine._write_generated_test(
            repo,
            {"path": "tests/test_regression_bugfix3.py",
             "code": "def test_example():\n    assert True\n"},
            unique_name=True,
        )
        path = result["path"]
        assert re.fullmatch(r"tests/test_autoresolve_[a-f0-9]{32}\.py", path)
        assert path not in names
        names.add(path)
        assert (repo / path).is_file()


def test_live_generated_test_preserves_existing_name(tmp_path):
    repo = tmp_path / "repo"
    tests = repo / "tests"
    tests.mkdir(parents=True)
    original = tests / "test_regression_bugfix3.py"
    original.write_text('def test_old():\n    assert True\n')
    engine = object.__new__(RealFixEngine)
    result = engine._write_generated_test(
        repo,
        {"path": "tests/test_regression_bugfix3.py",
         "code": "def test_new():\n    assert True\n"},
        unique_name=True,
    )
    assert original.read_text() == 'def test_old():\n    assert True\n'
    assert result['path'] != 'tests/test_regression_bugfix3.py'


def test_merge_conflict_is_detected_without_attempting_merge(monkeypatch):
    monkeypatch.setenv('AUTORESOLVE_ENABLE_MERGE', 'true')
    engine = object.__new__(RealFixEngine)
    engine.github_token = 'dummy'
    pull = Mock()
    pull.mergeable = False
    pull.html_url = 'https://github.com/example/repo/pull/7'
    repo = Mock()
    repo.owner.login = 'example'
    repo.get_pulls.return_value = [pull]
    with patch('backend.orchestrator.real_engine.Github') as github:
        github.return_value.get_repo.return_value = repo
        with pytest.raises(RuntimeError, match='merge conflicts'):
            engine.merge('example/repo', 'autoresolve/bug-7')
    pull.merge.assert_not_called()
