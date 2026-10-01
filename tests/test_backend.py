import pytest

from backend.database.session import SessionLocal
from backend.orchestrator import sheets, workflow
from backend.orchestrator.engine import FixEngine, StubEngine, set_engine

BUG = {"title": "Login fails on empty password", "description": "Crashes with a 500.",
       "repo": "acme/web", "reporter": "tina"}


def report(client, **over):
    r = client.post("/api/bugs", json={**BUG, **over})
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_report_runs_ai_and_waits_for_review(client):
    bug_id = report(client)
    assert bug_id.startswith("BUG-")
    bug = client.get(f"/api/bugs/{bug_id}").json()
    assert bug["status"] == "awaiting_review"
    assert bug["iteration"] == 1
    assert bug["root_cause"] and bug["changed_files"] and bug["test_results"]["passed"] is True
    assert [h["event"] for h in bug["history"]] == ["reported", "fix_proposed"]
    assert len(bug["attempts"]) == 1


def test_accepts_repository_alias_and_numeric_ids(client):
    r = client.post("/api/bugs", json={"title": "t", "description": "d", "repository": "x/y"})
    assert r.status_code == 201 and r.json()["repo"] == "x/y"
    n = r.json()["id"].split("-")[1]
    assert client.get(f"/api/bugs/{n}").status_code == 200
    assert client.get(f"/api/bugs/bug-{n}").status_code == 200


def test_validation_and_not_found(client):
    assert client.post("/api/bugs", json={"title": "  ", "description": "d", "repo": "r"}).status_code == 422
    assert client.post("/api/bugs", json={"title": "t"}).status_code == 422
    assert client.get("/api/bugs/BUG-9999").status_code == 404
    assert client.get("/api/bugs/nonsense").status_code == 404
    assert client.get("/api/bugs?status=bogus").status_code == 422


def test_approve_merges_and_notifies(client):
    bug_id = report(client)
    r = client.post(f"/api/bugs/{bug_id}/approve")
    assert r.status_code == 200
    bug = r.json()
    assert bug["status"] == "merged" and bug["resolved_at"]
    events = [h["event"] for h in bug["history"]]
    assert events[-2:] == ["merged", "tester_notified"]
    assert bug["attempts"][-1]["outcome"] == "approved"
    # can't approve twice
    assert client.post(f"/api/bugs/{bug_id}/approve").status_code == 409


def test_feedback_triggers_new_attempt_with_constraint(client):
    bug_id = report(client)
    r = client.post(f"/api/bugs/{bug_id}/feedback", json={"feedback": "Do not change the public API"})
    assert r.status_code == 200
    bug = client.get(f"/api/bugs/{bug_id}").json()
    assert bug["status"] == "awaiting_review" and bug["iteration"] == 2
    assert len(bug["attempts"]) == 2
    assert bug["attempts"][0]["outcome"] == "changes_requested"
    assert any("Do not change the public API" in step for step in bug["attempts"][1]["plan"])
    assert bug["feedback"][0]["text"] == "Do not change the public API"


def test_iteration_limit_marks_failed(client):
    bug_id = report(client)
    for _ in range(2):  # attempts 2 and 3
        client.post(f"/api/bugs/{bug_id}/feedback", json={"feedback": "try again"})
    assert client.get(f"/api/bugs/{bug_id}").json()["iteration"] == 3
    r = client.post(f"/api/bugs/{bug_id}/feedback", json={"feedback": "still wrong"})
    assert r.json()["status"] == "failed"
    bug = client.get(f"/api/bugs/{bug_id}").json()
    assert bug["status"] == "failed" and bug["iteration"] == 3
    assert bug["history"][-1]["event"] == "failed"
    assert client.post(f"/api/bugs/{bug_id}/feedback", json={"feedback": "x"}).status_code == 409


def test_feedback_must_not_be_blank(client):
    bug_id = report(client)
    assert client.post(f"/api/bugs/{bug_id}/feedback", json={"feedback": "   "}).status_code == 422


def test_engine_error_marks_failed(client):
    class Boom(StubEngine):
        def propose_fix(self, request):
            raise RuntimeError("model unavailable")
    set_engine(Boom())
    bug = client.get(f"/api/bugs/{report(client)}").json()
    assert bug["status"] == "failed"
    assert "model unavailable" in bug["history"][-1]["message"]


def test_merge_error_keeps_bug_awaiting_review(client):
    class BadMerge(StubEngine):
        def merge(self, repo, branch):
            raise RuntimeError("conflict")
    bug_id = report(client)
    set_engine(BadMerge())
    r = client.post(f"/api/bugs/{bug_id}/approve")
    assert r.status_code == 502 and "conflict" in r.json()["detail"]
    bug = client.get(f"/api/bugs/{bug_id}").json()
    assert bug["status"] == "awaiting_review"
    assert bug["history"][-1]["event"] == "merge_failed"
    set_engine(StubEngine())
    assert client.post(f"/api/bugs/{bug_id}/approve").json()["status"] == "merged"


def test_cannot_act_on_a_bug_that_is_not_awaiting_review(client):
    class Never(StubEngine):
        def propose_fix(self, request):
            raise RuntimeError("x")
    set_engine(Never())
    bug_id = report(client)  # -> failed
    assert client.post(f"/api/bugs/{bug_id}/approve").status_code == 409
    assert client.post(f"/api/bugs/{bug_id}/feedback", json={"feedback": "hi"}).status_code == 409


def test_run_iteration_is_idempotent(client):
    bug_id = int(report(client).split("-")[1])
    workflow.run_iteration(bug_id)  # status is awaiting_review, so this must do nothing
    assert len(client.get(f"/api/bugs/{bug_id}").json()["attempts"]) == 1


def test_list_filter_and_order(client):
    a, b = report(client, title="first"), report(client, title="second")
    client.post(f"/api/bugs/{a}/approve")
    all_ids = [x["id"] for x in client.get("/api/bugs").json()]
    assert all_ids == [a, b]  # most recently updated first
    assert [x["id"] for x in client.get("/api/bugs?status=awaiting_review").json()] == [b]


def test_metrics(client):
    empty = client.get("/api/metrics").json()
    assert empty["total"] == 0 and empty["resolution_rate"] == 0 and empty["avg_iterations"] == 0

    a = report(client)                                    # merged on attempt 1
    client.post(f"/api/bugs/{a}/approve")
    b = report(client)                                    # one change request, then merged
    client.post(f"/api/bugs/{b}/feedback", json={"feedback": "tweak"})
    client.post(f"/api/bugs/{b}/approve")
    report(client)                                        # still awaiting review

    m = client.get("/api/metrics").json()
    assert (m["total"], m["merged"], m["awaiting_review"]) == (3, 2, 1)
    assert m["resolution_rate"] == pytest.approx(2 / 3, abs=1e-3)
    assert m["first_attempt_rate"] == 0.5
    assert m["avg_iterations"] == pytest.approx(4 / 3, abs=1e-2)
    assert m["approval_rate"] == pytest.approx(2 / 3, abs=1e-3)  # 2 approvals, 1 change request


def test_sheets_sync_off_by_default(client):
    assert client.post("/api/sheets/sync").status_code == 400


def test_sheets_sync_imports_each_row_once(client, monkeypatch):
    rows = [["Title", "Description", "Repo", "Reporter"],
            ["Crash on save", "Stack trace attached", "acme/app", "sam"],
            ["", "no title, skipped", "acme/app", "sam"],
            ["Typo in footer", "", "", ""]]
    monkeypatch.setattr(sheets, "GOOGLE_SHEET_ID", "sheet123")
    monkeypatch.setattr(sheets, "_fetch_rows", lambda: rows)

    r = client.post("/api/sheets/sync")
    assert r.status_code == 200 and r.json()["count"] == 2
    bugs = {b["title"]: client.get(f"/api/bugs/{b['id']}").json() for b in client.get("/api/bugs").json()}
    assert bugs["Crash on save"]["reporter"] == "sam" and bugs["Crash on save"]["source"] == "sheet"
    assert bugs["Typo in footer"]["repo"] == "default"       # blank cells get defaults
    assert all(b["status"] == "awaiting_review" for b in bugs.values())

    assert client.post("/api/sheets/sync").json()["count"] == 0   # nothing new the second time
    rows.append(["New one", "d", "r", "t"])
    assert client.post("/api/sheets/sync").json()["count"] == 1


def test_sheets_error_is_a_502(client, monkeypatch):
    def broken():
        raise sheets.SheetsError("no access")
    monkeypatch.setattr(sheets, "GOOGLE_SHEET_ID", "sheet123")
    monkeypatch.setattr(sheets, "_fetch_rows", broken)
    r = client.post("/api/sheets/sync")
    assert r.status_code == 502 and "no access" in r.json()["detail"]


def test_serves_frontend_and_docs(client):
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/").status_code == 200  # the frontend folder
