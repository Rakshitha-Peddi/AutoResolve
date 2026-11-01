# AutoResolve 2.0

**AI-powered Python bug repair with Docker validation, GitHub pull requests, and human approval.**

AutoResolve is a **human-in-the-loop software maintenance system** that accepts bug reports from a web dashboard or Google Sheets, inspects a GitHub-hosted Python repository, proposes a focused AI-generated source-code fix and regression test, runs validation in an isolated Docker worker, and optionally publishes the result as a GitHub pull request (PR). **Only an explicit developer approval can trigger a merge.**

> **Project status:** Active academic major project / working prototype. The end-to-end workflow has been exercised on a disposable GitHub repository. AI services, repository permissions, Docker execution, and GitHub mergeability can still cause individual attempts to fail. Partial validation does **not** mean the entire repository passes.

## What AutoResolve does

- **Bug intake:** Manual reports through the FastAPI-powered dashboard, or polling of Google Sheets rows explicitly marked `Pending`.
- **Persistent tracking:** SQLite / SQLAlchemy stores bugs, repair attempts, changed files, validation output, feedback, and event history.
- **Repository analysis:** Retrieves relevant Python files, analyzes reported behavior, and plans a minimal repair.
- **AI provider choice:** Remote Gemini, Groq, or OpenRouter with configurable routing, fallback, timeouts, cooldowns, and persistent daily request budgets; optional local Ollama mode.
- **Patch and regression generation:** Produces a source patch and a pytest regression test; assigns each generated regression file a unique UUID-based filename to avoid cross-branch filename collisions.
- **Pre-fix/post-fix checks:** Confirms that the generated regression detects the bug before applying the patch and passes after applying it.
- **Docker isolation:** Runs tests in a restricted worker; performs a baseline comparison and reports the complete repository test result separately from the focused regression result.
- **GitHub collaboration:** When enabled, pushes a dedicated repair branch and creates a PR with the validation findings. The dashboard supports developer feedback and explicit approval.
- **Sheet writeback:** Preserves `Pending` during processing/review; writes `Failed` on a terminal failure and `Fixed` only after AutoResolve records a successful merge.

## End-to-end workflow

```text
Web dashboard / Google Sheets (Pending row)
                  |
                  v
         FastAPI + SQLite
                  |
                  v
         Workflow orchestrator
                  |
                  v
      Clone target GitHub repository
                  |
                  +--> Baseline Docker pytest run
                  |
                  v
     File retrieval + AI analysis / plan
                  |
                  v
       Source patch + regression test
                  |
                  +--> Validate paths and patch safety
                  +--> Regression FAILS before the fix
                  +--> Apply patch to isolated clone
                  +--> Regression PASSES after the fix
                  +--> Full Docker pytest run
                  +--> Compare failures with baseline
                  |
                  v
          Validation decision
                  |
           +------+-------------------+
           |                          |
      Full suite passes        Partial validation only*
           |                          |
           +------------+-------------+
                        |
              (Publishing enabled)
                        v
               GitHub branch + PR
                        |
                 Developer review
                  /           \
          Request changes   Approve & merge
                                   |
                         Successful GitHub merge
                                   |
                         Google Sheets -> Fixed

* Partially validated: focused regression passes, but known
  pre-existing repository failures remain. The PR explicitly
  discloses that full-suite validation is incomplete.
```

### Validation outcomes

| Outcome | Meaning | Result |
| --- | --- | --- |
| **Fully validated** | Generated regression failed before the fix, passed after the fix, and the full repository test suite passed. | Eligible for PR review when publishing is enabled. |
| **Partially validated** | Focused regression passed, but the full suite remains blocked by observed pre-existing failures and baseline comparison meets the project's partial-review checks. | Can be offered for **human review**, with a prominent warning. Full-suite success is **not** claimed. |
| **Failed** | Patch or regression failed, validation could not establish an acceptable result, or an execution/provider error occurred. | No successful validated repair is claimed. |

**Important:** Pytest collection may stop early, hiding additional failures. A comparison showing no newly reported failure identifiers is not proof that there are no regressions. Developers must inspect partially validated PRs carefully.

## Technology stack

| Layer | Technologies |
| --- | --- |
| Backend and API | Python, FastAPI, Uvicorn |
| Frontend | HTML, CSS, JavaScript |
| Persistence | SQLite, SQLAlchemy |
| AI repair | Gemini, Groq, OpenRouter; optional Ollama |
| Testing and analysis | pytest, Ruff, Git diffs |
| Isolation | Docker |
| GitHub integration | Git, PyGithub / GitHub API |
| Bug intake | Google Sheets API (optional), dashboard form |
| Configuration | `.env`, python-dotenv |

## Prerequisites

- Python **3.12 recommended** (the included worker image uses Python 3.12).
- Git and an accessible Docker daemon for real repairs.
- An AI backend: configured remote provider credentials **or** local Ollama.
- A GitHub token with access to the target repository for `RealFixEngine`; **repository Contents write** and appropriate PR permissions are needed to publish branches/PRs.
- A **disposable repository you own or are authorized to modify** for initial live testing.

## Quick start — Linux Mint / Linux

```bash
git clone https://github.com/Rakshitha-Peddi/AutoResolve.git
cd AutoResolve

python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and select one of the modes below. Do **not** commit the `.env` file, credentials, private datasets, or API keys.

### A. Safe demonstration mode (no real AI or GitHub changes)

```dotenv
AUTORESOLVE_REAL_ENGINE=false
AUTORESOLVE_ENABLE_PUBLISH=false
AUTORESOLVE_ENABLE_MERGE=false
GOOGLE_SHEET_ID=
GOOGLE_SHEET_URL=
```

```bash
python3 check_setup.py
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

- Dashboard: <http://127.0.0.1:8000>
- Interactive API docs: <http://127.0.0.1:8000/docs>

**StubEngine is a simulation:** it does not perform a real AI repository repair, create a real PR, or merge code on GitHub.

### B. Real AI repair mode

Build the Docker worker from the project root:

```bash
docker info
docker build -f docker/worker.Dockerfile \
  -t autoresolve-test-worker:python312 .
```

Set the following in `.env`, alongside the API keys and model identifiers for the providers you actually enable:

```dotenv
AUTORESOLVE_REAL_ENGINE=true
AUTORESOLVE_AI_BACKEND=remote

AI_ENABLED_PROVIDERS=gemini,groq,openrouter
AI_PRIMARY_PROVIDER=gemini
AI_FALLBACK_ENABLED=true
AI_REQUEST_TIMEOUT=120
AI_MAX_RETRIES=0
ALLOW_PAID_PROVIDERS=false

# Add your real values privately:
GEMINI_API_KEY=
GEMINI_MODEL=
GROQ_API_KEY=
GROQ_MODEL=
OPENROUTER_API_KEY=
OPENROUTER_MODEL=
GITHUB_TOKEN=

# Start with both GitHub write operations disabled.
AUTORESOLVE_ENABLE_PUBLISH=false
AUTORESOLVE_ENABLE_MERGE=false
```

Enable **only providers whose credentials and model names you have configured**. For example, set `AI_ENABLED_PROVIDERS=gemini,groq` if OpenRouter is not configured. The `AI_PRIMARY_PROVIDER` must appear in the enabled list. The manager uses provider fallback when enabled; external provider availability is not guaranteed. **Current caveat:** the OpenRouter adapter also configures its own 60-second HTTP client timeout, so raising `AI_REQUEST_TIMEOUT` alone does not necessarily extend OpenRouter network waits.

Request budgets are recorded in `.autoresolve_data/ai_usage.sqlite3` by default. They are **local safety limits**, not proof of available provider credits:

```dotenv
AI_GEMINI_DAILY_LIMIT=20
AI_GROQ_DAILY_LIMIT=30
AI_OPENROUTER_DAILY_LIMIT=30
AI_USAGE_DB_PATH=.autoresolve_data/ai_usage.sqlite3
```

The default values above may be overridden to match your own usage policy. Reservations are counted before a request is sent, including requests that subsequently time out; do not reset counters to bypass provider limits.

For optional local inference, set `AUTORESOLVE_AI_BACKEND=ollama` and configure `OLLAMA_HOST` / `OLLAMA_MODEL` instead of using remote provider routing.

Check the environment and start:

```bash
python3 check_setup.py
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

> **Setup-check note:** The repository's current `check_setup.py` still validates only `gemini`/`groq` for remote mode. It may reject a valid OpenRouter configuration even though `ai_agent/ai/bootstrap.py` supports OpenRouter. This checker needs a separate update; do not disable tests or change AI settings solely to silence its outdated provider list.

### Enable PR publishing and human-approved merging

Once the controlled real-engine validation works, enable publishing:

```dotenv
AUTORESOLVE_ENABLE_PUBLISH=true
AUTORESOLVE_ENABLE_MERGE=false
```

With this configuration, AutoResolve may push branches and create PRs, **but it cannot merge them through its approval action**. Inspect the PR and test output first. To test the explicit **Approve & Merge** action, set `AUTORESOLVE_ENABLE_MERGE=true` and restart the server, then approve the reviewed PR in the dashboard. Do not enable merging on an important repository until the workflow has been verified.

GitHub may reject a push or merge despite valid credentials (for example due to server-side restrictions or conflicting changes). Unique regression filenames prevent the previously observed **test-file name collision**, but do **not** eliminate genuine conflicts between edits to the same source lines. A conflicted PR requires rebasing/regeneration and revalidation; it must not be silently force-merged.

### Docker workspaces

If Docker cannot access the temporary workspace (for example with certain Snap Docker configurations), create a directory accessible to the daemon and set its **absolute** path:

```bash
mkdir -p .autoresolve-test-workspaces
chmod 700 .autoresolve-test-workspaces
realpath .autoresolve-test-workspaces
```

```dotenv
# Replace with the absolute path printed by realpath:
AUTORESOLVE_WORKSPACE_DIR=/absolute/path/to/AutoResolve/.autoresolve-test-workspaces
```

## Google Sheets integration

Google Sheets intake is optional. Configure `GOOGLE_SHEET_ID` or `GOOGLE_SHEET_URL` and `GOOGLE_CREDENTIALS_FILE` in `.env`, then grant the configured Google service account access to the spreadsheet.

Use the existing columns:

| Title | Description | Repo | Reporter | Status | Error |
| --- | --- | --- | --- | --- | --- |
| Handle missing user | Function crashes when user is None | `owner/repo` | Tester | `Pending` | |

- Only rows explicitly marked **`Pending`** are imported for new processing.
- `Status` remains `Pending` while a repair is running or awaiting review.
- Terminal repair failures set **`Failed`** and populate **`Error`**.
- **`Fixed` is recorded only after successful GitHub merge** through the workflow.
- Existing `Failed` / `Fixed` rows must not be reset merely to trigger another run. Do not delete the project database as a way to retry old rows.

## API and dashboard

The frontend communicates with these backend routes:

| Method | Route | Purpose |
| --- | --- | --- |
| `GET` | `/api/bugs` | List reported bugs |
| `GET` | `/api/bugs/{id}` | Read a bug, attempts, history, diffs, and test results |
| `GET` | `/api/metrics` | Workflow statistics |
| `POST` | `/api/bugs` | Submit a bug manually |
| `POST` | `/api/bugs/{id}/feedback` | Request changes to a repair proposal |
| `POST` | `/api/bugs/{id}/approve` | Request GitHub merge of a reviewable PR |

The dashboard distinguishes **full test success**, **partial validation**, and **failed validation** instead of labeling every full-suite failure as a failed targeted repair.

## Testing

From the project root with `.venv` active:

```bash
python3 -m pytest -q
python3 -m ruff check .
git diff --check
```

The project has achieved **277 passing pytest tests** in the development environment after the validation and test-filename-collision changes. This is a recorded development result, **not** a guarantee that every target repository will pass validation.

## Security and operational boundaries

- Use repositories you own or have explicit authorization to test and modify.
- AI-generated patches, source paths, and regression-test locations are checked, but security checks are not a substitute for code review.
- The Docker test worker uses restricted execution settings, including disabled container networking; container isolation is a risk reduction measure, **not an absolute sandbox guarantee**.
- The focused regression must expose a real pre-fix failure before a repair is accepted.
- A full-suite failure is never represented as full success. Partial validation is disclosed in the PR and must receive careful developer review.
- Generated regression tests receive unique filenames across independently prepared fixes; overlapping **source edits** can still cause genuine merge conflicts.
- Published code is not automatically merged by AI. Approval and a successful GitHub merge are distinct steps.
- Keep `.env`, tokens, service-account credentials, and databases private. Provider prompts may send eligible repository source to external AI services; use trusted, non-sensitive test repositories.

## Known limitations

1. Automated repairs currently focus on **Python** source files and pytest-based regression tests.
2. The Docker worker needs the relevant target-repository dependencies to be installed or otherwise available.
3. AI providers may time out, rate-limit requests, or exhaust internal/external budgets even when fallback is enabled.
4. Baseline comparisons are diagnostic; interrupted pytest collection may hide failures. A partially validated PR is **not** equivalent to a passing full suite.
5. Independent modifications to the same source lines may still conflict at merge time. AutoResolve detects conflicts rather than guaranteeing autonomous conflict resolution.
6. `check_setup.py`, `.env.example`, and `SETUP.md` have older provider documentation/checks and should be aligned with the implemented OpenRouter support.

## Documentation

- [`SETUP.md`](SETUP.md) — installation and demonstration guidance (note the provider-list caveat above).
- [`.env.example`](.env.example) — configuration starter; add OpenRouter settings if using that provider.
- [GitHub repository](https://github.com/Rakshitha-Peddi/AutoResolve)

## Academic project

**AutoResolve 2.0 — Major Project**  
B.Tech, Computer Science and Engineering

This is an academic software-engineering prototype intended to demonstrate AI-assisted repair **with validation, traceability, and human oversight**.
