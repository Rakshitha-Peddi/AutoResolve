"""Safely demonstrate AutoResolve's bug workflow using StubEngine."""

from backend.database.session import Base, SessionLocal, engine
from backend.models.schemas import BugCreate
from backend.orchestrator.engine import StubEngine, set_engine
from backend.orchestrator.workflow import (
    approve,
    create_bug,
    get_bug,
    request_changes,
    run_iteration,
)


def main() -> None:
    # Guarantee that this demo uses placeholder fixes, not a real AI engine.
    set_engine(StubEngine())

    # Ensure the database tables exist.
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # 1. Create a demo bug.
        bug = create_bug(
            db,
            BugCreate(
                title="Null pointer in user lookup",
                description=(
                    "User lookup fails when the user record is None. "
                    "The application crashes instead of handling the "
                    "missing user gracefully."
                ),
                repo="demo_repo",
                reporter="tester",
            ),
            source="demo",
        )

        bug_id = bug.id
        print(f"Created {bug.public_id}: {bug.title}")

        # 2. Run the first placeholder repair attempt.
        bug = run_iteration(bug_id)
        bug = get_bug(db, bug_id)
        print(f"After iteration 1: {bug.status}")

        # 3. Demonstrate feedback and a second attempt.
        if bug.status == "awaiting_review":
            request_changes(
                db,
                bug,
                "Add an explicit regression test for the None user case "
                "and do not change the public API.",
            )
            print("Developer feedback recorded.")

            bug = run_iteration(bug_id)
            bug = get_bug(db, bug_id)
            print(f"After feedback iteration: {bug.status}")

        # 4. Demonstrate approval only when a candidate is ready.
        if bug.status == "awaiting_review":
            bug = approve(db, bug)
            print("Approval result: merged")

        print(f"Final status for {bug.public_id}: {bug.status}")
        print("Demo completed using StubEngine; no real repository merge occurred.")

    finally:
        db.close()


if __name__ == "__main__":
    main()