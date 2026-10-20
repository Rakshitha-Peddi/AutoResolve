import pytest
from unittest.mock import Mock, patch

from backend.orchestrator.github_client import GitHubClient


REPO_URL = "https://github.com/Albert-2106/Major-project/tree/main"


def test_github_repository_access():
    fake_repo = Mock()
    fake_repo.full_name = "Albert-2106/Major-project"
    fake_repo.name = "Major-project"
    fake_repo.owner.login = "Albert-2106"
    fake_repo.default_branch = "main"
    fake_repo.private = False
    fake_repo.html_url = REPO_URL

    with patch(
        "backend.orchestrator.github_client.Github"
    ) as mock_github:
        mock_github.return_value.get_repo.return_value = fake_repo

        client = GitHubClient(token="test-token")

        info = client.get_repository_info(REPO_URL)

    assert info["full_name"] == "Albert-2106/Major-project"
    assert info["default_branch"] == "main"
    assert info["owner"] == "Albert-2106"


def test_verify_pull_request_head_accepts_matching_sha():
    fake_pull = Mock()
    fake_pull.state = "open"
    fake_pull.head.sha = "a" * 40
    fake_pull.html_url = "https://github.com/example/repo/pull/7"

    fake_repo = Mock()
    fake_repo.get_pull.return_value = fake_pull

    with patch(
        "backend.orchestrator.github_client.Github"
    ) as mock_github:
        mock_github.return_value.get_repo.return_value = fake_repo
        client = GitHubClient(token="test-token")

        result = client.verify_pull_request_head(
            "https://github.com/example/repo",
            7,
            "a" * 40,
        )

    assert result["verified"] is True
    assert result["head_sha"] == "a" * 40
    assert result["pull_number"] == 7


def test_verify_pull_request_head_rejects_mismatched_sha():
    fake_pull = Mock()
    fake_pull.state = "open"
    fake_pull.head.sha = "b" * 40

    fake_repo = Mock()
    fake_repo.get_pull.return_value = fake_pull

    with patch(
        "backend.orchestrator.github_client.Github"
    ) as mock_github:
        mock_github.return_value.get_repo.return_value = fake_repo
        client = GitHubClient(token="test-token")


        with pytest.raises(RuntimeError, match="SHA mismatch"):
            client.verify_pull_request_head(
                "https://github.com/example/repo",
                7,
                "c" * 40,
            )
def test_verify_pull_request_head_rejects_closed_pull_request():
    fake_pull = Mock()
    fake_pull.state = "closed"

    fake_repo = Mock()
    fake_repo.get_pull.return_value = fake_pull

    with patch(
        "backend.orchestrator.github_client.Github"
    ) as mock_github:
        mock_github.return_value.get_repo.return_value = fake_repo
        client = GitHubClient(token="test-token")


        with pytest.raises(RuntimeError, match="not open"):
            client.verify_pull_request_head(
                "https://github.com/example/repo",
                7,
                "a" * 40,
            )

def test_verify_pull_request_head_rejects_invalid_sha():
    with patch(
        "backend.orchestrator.github_client.Github"
    ) as mock_github:
        client = GitHubClient(token="test-token")

        with pytest.raises(ValueError, match="Expected candidate SHA"):
            client.verify_pull_request_head(
                "https://github.com/example/repo",
                7,
                "not-a-valid-sha",
            )

        mock_github.return_value.get_repo.assert_not_called()
