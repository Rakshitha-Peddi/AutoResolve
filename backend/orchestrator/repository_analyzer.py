from .github_client import GitHubClient


class RepositoryAnalyzer:
    """Analyze the structure of a GitHub repository."""

    def __init__(self, github_client: GitHubClient):
        self.github_client = github_client

    def list_files(self, repo_url: str, path: str = "") -> list[str]:
        """Return all files in the repository recursively."""
        repo = self.github_client.get_repository(repo_url)

        files = []

        def walk(current_path: str):
            contents = repo.get_contents(
                current_path,
                ref=repo.default_branch,
            )

            for item in contents:
                if item.type == "file":
                    files.append(item.path)

                elif item.type == "dir":
                    walk(item.path)

        walk(path)

        return files

    def get_file_tree(self, repo_url: str) -> dict:
        """Return basic repository structure information."""
        repo = self.github_client.get_repository(repo_url)

        files = self.list_files(repo_url)

        return {
            "repository": repo.full_name,
            "default_branch": repo.default_branch,
            "file_count": len(files),
            "files": files,
        }