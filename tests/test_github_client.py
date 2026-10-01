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