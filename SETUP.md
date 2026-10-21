# AutoResolve — setup task list 

Do the steps in order. Each step says how you know it worked.
Commands go in a **terminal** opened inside the project folder
(Windows: open the folder, type `cmd` in the address bar, Enter.
Mac: right-click the folder → "New Terminal at Folder").

---
## PART A — Install the tools (one time)

- [ ] **A1. Python 3.12** from python.org. Check: `python --version` (Mac/Linux: `python3 --version`).
- [ ] **A2. Git** from git-scm.com. Check: `git --version`.
- [ ] **A3. Docker Desktop** from docker.com. Install, **open it, leave it running** (whale icon).
      Check: `docker info` prints a lot of text, no error.
- [ ] **A4. Accounts:** a GitHub account and an OpenAI account **with billing enabled**
      (the API needs credit; ChatGPT subscriptions do not cover it).

## PART B — Prepare the project

- [ ] **B1. Install the Python packages**
      ```
      python -m venv .venv
      .venv\Scripts\activate          (Windows)   |   source .venv/bin/activate   (Mac/Linux)
      pip install -r requirements.txt
      ```
      Works if the last line says "Successfully installed …".
- [ ] **B2. Build the safe test sandbox** (AutoResolve runs untrusted code ONLY inside this):
      ```
      docker build -f docker/worker.Dockerfile -t autoresolve-test-worker:python312 .
      ```
- [ ] **B3. Delete the old test database** for a clean start: delete the file `autoresolve.db`.
- [ ] **B4. Create your settings file**
      ```
      cp .env.example .env            (Windows: copy .env.example .env)
      ```
      Open `.env` in Notepad. You'll fill it in below.

## PART C — Get your two keys

- [ ] **C1. OpenAI key:** platform.openai.com → API keys → Create. Paste after `OPENAI_API_KEY=`.
      Set `OPENAI_MODEL=` to a model your account can use (the checker in D1 tells you if it's wrong).
- [ ] **C2. A practice repo on GitHub** (do NOT start on your real project):
      1. GitHub → New repository → name `autoresolve-practice` → Create.
      2. Upload the 4 files from the `practice_repo/` folder here, **keeping the folders**
         (`src/__init__.py`, `src/user_service.py`, `tests/test_user_service.py`, `README.md`).
- [ ] **C3. GitHub token (read-only first):** GitHub → Settings → Developer settings →
      Personal access tokens → **Fine-grained tokens** → Generate.
      - Repository access: **Only select repositories** → `autoresolve-practice`
      - Permissions → Repository → **Contents: Read-only**
      Paste after `GITHUB_TOKEN=` in `.env`.
      Never share this token or the `.env` file with anyone (including in chat).

## PART D — Check it, then run it

- [ ] **D1. Run the checker:**
      ```
      python check_setup.py YOUR_GITHUB_USERNAME/autoresolve-practice
      ```
      Fix every `[FAIL]` line (it tells you how), re-run until it says **All good**.
- [ ] **D2. Start AutoResolve**
      ```
      uvicorn backend.main:app --reload
      ```
      The terminal must say `AutoResolve using RealFixEngine`. If it says `StubEngine`,
      `AUTORESOLVE_REAL_ENGINE=true` is missing in `.env`.
- [ ] **D3. Open** http://127.0.0.1:8000 in your browser.
- [ ] **D4. Report the practice bug** in the form:
      - Title: `get_user_name crashes on None`
      - Description: `get_user_name in src/user_service.py raises TypeError when user is None. It should return None.`
      - Repo: `YOUR_GITHUB_USERNAME/autoresolve-practice`
      Click **Create Bug**. Wait 1–3 minutes; the page updates by itself.
- [ ] **D5. Review the result.** Status `awaiting review` = the AI wrote a fix, a test that fails
      before the fix, and the full suite passes after it. Read the diff.
      - **Request Changes** → type instructions → AI tries again (max 3 attempts).
      - If it says `failed`: look at the terminal window running uvicorn — the real error is printed there.

## PART E — Turn on real merging (only after D works)

- [ ] **E1.** Make a new token (or edit C3) with **Contents: Read and write** and
      **Pull requests: Read and write**, still only for the practice repo. Put it in `.env`.
- [ ] **E2.** In `.env` set `AUTORESOLVE_ENABLE_MERGE=true`. Restart (Ctrl+C, run D2 again).
- [ ] **E3.** Run `python check_setup.py YOUR_USERNAME/autoresolve-practice` again.
- [ ] **E4.** Report the bug again. Now a branch and a **Pull Request** appear on GitHub
      when tests pass. Clicking **Approve & Merge** in AutoResolve merges that PR.
      Nothing is ever merged without your click.
- [ ] **E5.** Only now point it at a real repo (new token limited to that repo).

## PART F — Optional: Google Sheets intake
Share a sheet (columns `Title | Description | Repo | Reporter`) with a Google service account,
save its key as `credentials/credentials.json`, set `GOOGLE_SHEET_URL=` in `.env`, restart.
Every row needs a real **Repo** value (`owner/repo`), otherwise the fix cannot start.

---
## Limits to know about
- The target repo's tests must run with plain `pytest` and **only the packages in this project's
  requirements.txt** (the sandbox has no internet). If the repo needs other libraries, add them to
  `requirements.txt` and rebuild (B2).
- Python repos only. Test files are put under `tests/`.
- A fix that doesn't pass validation is marked `failed` (you can still read why in the detail panel).

## Troubleshooting
| You see | Cause → fix |
|---|---|
| Terminal says `StubEngine` | `AUTORESOLVE_REAL_ENGINE=true` missing in `.env` |
| App won't start: "setup is incomplete" | a key is empty in `.env` → run `python check_setup.py` |
| `Docker could not start the test worker` | Docker Desktop not running, or B2 not done |
| Bug → `failed` immediately | read the uvicorn terminal; usually bad repo name, token without access to that repo, or wrong `OPENAI_MODEL` |
| "regression test did not reproduce the bug" | the AI's test passed on unfixed code; click Request Changes asking for a test that calls the exact function from the bug report |
| Approve says "Merge failed" | `AUTORESOLVE_ENABLE_MERGE` still false, or token lacks write access (E1–E2) |
