import os
from urllib.parse import urlparse

from github import Github
from github.GithubException import GithubException


class GitHubClient:
    """Read-only GitHub client for AutoResolve."""

    def __init__(self, token: str | None = None):
        self.token = token or os.getenv("GITHUB_TOKEN")

        if not self.token:
            raise ValueError("GITHUB_TOKEN is not configured.")

        self.client = Github(self.token)

    @staticmethod
    def parse_repo_url(repo_url: str) -> str:
        parsed = urlparse(repo_url)

        if parsed.hostname not in {"github.com", "www.github.com"}:
            raise ValueError("Only GitHub repository URLs are supported.")

        parts = [part for part in parsed.path.split("/") if part]

        if len(parts) < 2:
            raise ValueError("Invalid GitHub repository URL.")

        owner = parts[0]
        repo = parts[1]

        if repo.endswith(".git"):
            repo = repo[:-4]

        return f"{owner}/{repo}"

    def get_repository(self, repo_url: str):
        repo_name = self.parse_repo_url(repo_url)

        try:
            return self.client.get_repo(repo_name)
        except GithubException as exc:
            raise RuntimeError(
                f"Unable to access GitHub repository '{repo_name}': "
                f"{exc.data.get('message', str(exc))}"
            ) from exc

    def get_repository_info(self, repo_url: str) -> dict:
        repo = self.get_repository(repo_url)

        return {
            "full_name": repo.full_name,
            "name": repo.name,
            "owner": repo.owner.login,
            "default_branch": repo.default_branch,
            "private": repo.private,
            "url": repo.html_url,
        }

    def get_file(self, repo_url: str, path: str) -> str:
        repo = self.get_repository(repo_url)

        try:
            file = repo.get_contents(
                path,
                ref=repo.default_branch,
            )

            if isinstance(file, list):
                raise ValueError(f"'{path}' is a directory, not a file.")

            return file.decoded_content.decode("utf-8")

        except GithubException as exc:
            raise RuntimeError(
                f"Unable to read '{path}': "
                f"{exc.data.get('message', str(exc))}"
            ) from exc
