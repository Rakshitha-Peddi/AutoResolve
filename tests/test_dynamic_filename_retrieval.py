from types import SimpleNamespace

from ai_agent.engine import CodeFixEngine


def test_retrieval_uses_title_and_description(tmp_path):
    source = tmp_path / "test_3.py"
    source.write_text(
        "value = 3\nprint(value)\n",
        encoding="utf-8",
    )

    engine = CodeFixEngine()

    bug = SimpleNamespace(
        title="Syntax and Name error in test_3.py",
        description=(
            "test_3.py has wrong use of datatype, "
            "expected output: str"
        ),
    )

    query = f"{getattr(bug, 'title', '')}\n{bug.description}"

    results = engine.retriever.retrieve(tmp_path, query)

    paths = [path for _, path, _ in results]

    assert "test_3.py" in paths