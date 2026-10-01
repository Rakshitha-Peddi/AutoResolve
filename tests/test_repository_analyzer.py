from unittest.mock import Mock

from backend.orchestrator.repository_analyzer import RepositoryAnalyzer


REPO_URL = "https://github.com/Albert-2106/Major-project/tree/main"


def create_fake_repo():
    repo = Mock()
    repo.full_name = "Albert-2106/Major-project"
    repo.default_branch = "main"

    readme = Mock()
    readme.type = "file"
    readme.path = "README.md"

    main_file = Mock()
    main_file.type = "file"
    main_file.path = "backend/main.py"

    backend_dir = Mock()
    backend_dir.type = "dir"
    backend_dir.path = "backend"

    root_contents = [readme, backend_dir]
    backend_contents = [main_file]

    def get_contents(path, ref=None):
        if path == "":
            return root_contents

        if path == "backend":
            return backend_contents

        return []

    repo.get_contents.side_effect = get_contents

    return repo


def test_repository_analyzer_lists_files():
    fake_repo = create_fake_repo()

    github_client = Mock()
    github_client.get_repository.return_value = fake_repo

    analyzer = RepositoryAnalyzer(github_client)

    files = analyzer.list_files(REPO_URL)

    assert "README.md" in files
    assert "backend/main.py" in files


def test_repository_analyzer_returns_file_tree():
    fake_repo = create_fake_repo()

    github_client = Mock()
    github_client.get_repository.return_value = fake_repo

    analyzer = RepositoryAnalyzer(github_client)

    tree = analyzer.get_file_tree(REPO_URL)

    assert tree["repository"] == "Albert-2106/Major-project"
    assert tree["default_branch"] == "main"
    assert tree["file_count"] == 2
    assert "README.md" in tree["files"]