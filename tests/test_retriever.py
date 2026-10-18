
from pathlib import Path

from ai_agent.retriever import RepositoryRetriever


def test_retriever_finds_relevant_source_file(tmp_path: Path):
    # Create a tiny fake repository; no GitHub or AI access is needed.
    (tmp_path / "user_service.py").write_text(
        "def find_user(user_id):\n"
        "    user = database_lookup(user_id)\n"
        "    if user is None:\n"
        "        return None\n"
        "    return user\n"
    )

    (tmp_path / "unrelated.py").write_text(
        "def calculate_tax(amount):\n"
        "    return amount * 0.1\n"
    )

    (tmp_path / "README.md").write_text(
        "This project manages user records.\n"
    )

    retriever = RepositoryRetriever()
    results = retriever.retrieve(
        str(tmp_path),
        "find_user database_lookup user None",
    )

    assert results, "Retriever should find relevant source files"

    paths = [path for _, path, _ in results]
    assert "user_service.py" in paths
    assert "unrelated.py" not in paths

    # Check that the result contains useful source-code evidence.
    user_result = next(
        result for result in results
        if result[1] == "user_service.py"
    )
    _, _, source = user_result

    assert "database_lookup" in source
    assert "if user is None" in source

