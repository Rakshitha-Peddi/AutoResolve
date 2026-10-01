from backend.database.session import SessionLocal, Base, engine
from backend.models.bug import Bug
from backend.models.schemas import BugCreate
from backend.orchestrator.workflow import Workflow

Base.metadata.create_all(bind=engine)
db=SessionLocal()
w=Workflow(db)

bug=w.create_bug(BugCreate(title='Null pointer in user lookup', description='User lookup fails when the user record is None. The application crashes instead of handling the missing user gracefully.', repository='demo_repo', reporter='tester'))
print(f'Created BUG-{bug.id}')
w.run_iteration(bug)
print('Iteration 1:', bug.status)
if bug.status == 'AWAITING_REVIEW':
    w.request_feedback(bug, 'Add an explicit regression test for the None user case and do not change the public API.', 'developer')
    print('After feedback:', bug.status)
if bug.status == 'AWAITING_REVIEW':
    pr=w.approve(bug)
    print('Merged:', pr)
print('Final:', bug.status)
