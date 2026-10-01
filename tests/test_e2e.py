from pathlib import Path
from fastapi.testclient import TestClient
import os, tempfile, shutil
os.environ['DATABASE_URL'] = 'sqlite:///./test_autoresolve.db'
from backend.main import app

client = TestClient(app)

def test_end_to_end_demo():
    # API smoke test; full local workflow is covered by demo script.
    r = client.post('/api/bugs', json={"title":"Null pointer in user lookup","description":"User lookup fails when the user record is None. The application crashes instead of handling the missing user gracefully.","repository":"demo_repo","reporter":"tester"})
    assert r.status_code == 200
    bug_id = r.json()['id']
    r = client.post(f'/api/bugs/{bug_id}/analyze')
    assert r.status_code == 200
    detail = client.get(f'/api/bugs/{bug_id}').json()
    assert detail['status'] == 'AWAITING_REVIEW'
    assert detail['iterations'][0]['validation']['passed'] is True
