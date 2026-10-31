
"""Security regression tests for repository retrieval."""

from ai_agent.retriever import RepositoryRetriever


def test_retriever_excludes_environment_files(tmp_path):
    (tmp_path / ".env").write_text("TOKEN=private_marker")
    (tmp_path / "app.py").write_text(
        "def private_marker():\n    return 1\n"
    )

    results = RepositoryRetriever().retrieve(
        str(tmp_path),
        "private_marker",
    )

    assert [item[1] for item in results] == ["app.py"]
    assert all("TOKEN=" not in item[2] for item in results)


def test_retriever_excludes_secret_python_files(tmp_path):
    (tmp_path / "secrets.py").write_text(
        "private_marker = 'secret'\n"
    )
    (tmp_path / "app.py").write_text(
        "private_marker = 'safe example'\n"
    )

    results = RepositoryRetriever().retrieve(
        str(tmp_path),
        "private_marker",
    )

    assert [item[1] for item in results] == ["app.py"]


def test_retriever_skips_virtual_environments(tmp_path):
    venv = tmp_path / ".venv"
    venv.mkdir()
    (venv / "hidden.py").write_text("private_marker")

    (tmp_path / "app.py").write_text("private_marker")

    results = RepositoryRetriever().retrieve(
        str(tmp_path),
        "private_marker",
    )

    assert [item[1] for item in results] == ["app.py"]


def test_retriever_does_not_follow_file_symlinks(tmp_path):
    external = tmp_path.parent / "external_secret.py"
    external.write_text("private_marker = 'secret'")

    (tmp_path / "linked.py").symlink_to(external)
    (tmp_path / "app.py").write_text("private_marker")

    results = RepositoryRetriever().retrieve(
        str(tmp_path),
        "private_marker",
    )

    assert [item[1] for item in results] == ["app.py"]


def test_retriever_rejects_oversized_files(tmp_path):
    (tmp_path / "large.py").write_text(
        "private_marker\n" + "x" * 150000
    )
    (tmp_path / "app.py").write_text("private_marker")

    results = RepositoryRetriever().retrieve(
        str(tmp_path),
        "private_marker",
    )

    assert [item[1] for item in results] == ["app.py"]


def test_retriever_skips_binary_files(tmp_path):
    (tmp_path / "binary.py").write_bytes(
        b"private_marker\x00binary"
    )
    (tmp_path / "app.py").write_text("private_marker")

    results = RepositoryRetriever().retrieve(
        str(tmp_path),
        "private_marker",
    )

    assert [item[1] for item in results] == ["app.py"]
