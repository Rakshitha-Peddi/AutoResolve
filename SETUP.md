
# AutoResolve 2.0 — Setup Guide (Linux Mint)

## 1. Prepare the environment

Open a terminal inside the AutoResolve project.

Check Python and Git:

```bash
python3 --version
git --version
```

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python3 -m pip install -r requirements.txt
```

## 2. Configure the application

Copy the example environment file:

```bash
cp .env.example .env
```

Open `.env` and select either demo mode or real mode.

Never share or commit `.env`.

## 3. Start in safe demo mode

Set:

```dotenv
AUTORESOLVE_REAL_ENGINE=false
AUTORESOLVE_ENABLE_PUBLISH=false
AUTORESOLVE_ENABLE_MERGE=false
GOOGLE_SHEET_ID=
GOOGLE_SHEET_URL=
```

Check:

```bash
python3 check_setup.py
```

Start:

```bash
python3 -m uvicorn backend.main:app \
  --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000

Submit a bug through the dashboard.

The demo engine creates simulated repair proposals. It does
not call Gemini, Groq, Docker or GitHub to perform a real fix.

## 4. Prepare Docker for real repairs

Confirm Docker is running:

```bash
docker info
```

Build the worker image:

```bash
docker build \
  -f docker/worker.Dockerfile \
  -t autoresolve-test-worker:python312 .
```

For Snap Docker on Linux Mint, use an accessible
workspace inside the project:

```bash
mkdir -p .autoresolve-test-workspaces
chmod 700 .autoresolve-test-workspaces
```

Set `AUTORESOLVE_WORKSPACE_DIR` to its absolute path in `.env`.

## 5. Configure Gemini/Groq

For remote AI, set:

```dotenv
AUTORESOLVE_AI_BACKEND=remote
AI_ENABLED_PROVIDERS=gemini,groq
AI_PRIMARY_PROVIDER=gemini
AI_FALLBACK_ENABLED=false

GEMINI_API_KEY=
GEMINI_MODEL=

GROQ_API_KEY=
GROQ_MODEL=
```

Fill in your own credentials and model identifiers.

To use only Gemini, set `AI_ENABLED_PROVIDERS=gemini`.
To use only Groq, set `AI_ENABLED_PROVIDERS=groq`
and `AI_PRIMARY_PROVIDER=groq`.

## 6. Configure a disposable GitHub repository

Create a separate practice repository on GitHub.

Use a small Python example such as:

```python
def get_user_name(user):
    return user["name"]
```

Expected requirements:

- `get_user_name(None)` returns `"Guest"`.
- Valid usernames are preserved.

Create a fine-grained GitHub token restricted to that
practice repository.

For validation-only operation, begin with read-only repository
contents permission.

Set the token privately in `.env`.

Keep these flags disabled:

```dotenv
AUTORESOLVE_ENABLE_PUBLISH=false
AUTORESOLVE_ENABLE_MERGE=false
```

## 7. Enable the real engine

Set:

```dotenv
AUTORESOLVE_REAL_ENGINE=true
AUTORESOLVE_AI_BACKEND=remote
```

Run:

```bash
python3 check_setup.py
```

All checks should pass.

Then start Uvicorn and submit the practice bug using the
practice repository's `owner/repo` identifier.

RealFixEngine clones the repository into an isolated workspace,
generates a patch and regression test, and runs Docker validation.

The AI may produce an incorrect patch. Rejection by validation
is expected and must not be bypassed.

## 8. Developer review

For successful fixes, the dashboard displays an awaiting-review
proposal.

Review the changed files and test results.

Request Changes allows another attempt when iterations remain.

When publishing is disabled, do not expect a GitHub pull request
or remote branch to appear.

## 9. Optional GitHub publishing

Publishing and merging are separate operations.

Only consider enabling publishing after validating the complete
workflow on a disposable repository.

Publishing requires appropriate repository write and pull
request permissions.

Keep merging disabled until explicitly testing the approval
workflow with a repository you control.

Never enable publishing or merging on an important repository
for an initial demonstration.

## 10. Run automated tests

```bash
python3 -m pytest -q
python3 -m ruff check .
```

## 11. Troubleshooting

| Issue | What to check |
|---|---|
| StubEngine starts unexpectedly | `AUTORESOLVE_REAL_ENGINE` |
| Gemini configuration failure | API key, enabled providers and model |
| Groq configuration failure | API key, enabled providers and model |
| Docker startup failure | Daemon, worker image, workspace access |
| GitHub clone failure | Token permission and repository name |
| Regression test fails before fix | Expected for a correctly reproduced bug |
| Tests fail after fix | AI-generated patch did not satisfy requirements |
| No pull request appears | Publishing may be intentionally disabled |
| Rate limit failure | Provider quota and daily usage limits |

## 12. Final safety reminder

Use an isolated test repository.
Keep `.env` private.
Do not disable regression checks.
Do not enable publishing or merging without explicit authorization.
