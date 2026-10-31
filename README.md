
# AutoResolve 2.0

AI-Powered Automated Bug Detection, Repair and Validation System

AutoResolve is a human-in-the-loop software maintenance platform that receives bug reports, analyzes Python repositories, generates AI-assisted fixes and regression tests, validates changes inside Docker, and presents verified proposals for developer review.

## Key Features

- Bug reporting through FastAPI and a web dashboard
- SQLite-based bug records, attempts and history
- Optional Google Sheets bug intake
- Source-code retrieval and AI-based bug analysis
- Gemini and Groq integration with provider routing
- Optional local Ollama backend
- Automated Python patch generation
- Regression test generation
- Pre-fix failure verification
- Post-fix Docker test execution
- Validation-based retry with feedback
- Developer approval and change requests
- Optional GitHub branch and pull request publishing
- Separately controlled GitHub merging
- Security checks for source paths, patches and generated tests

## Architecture

```text
Bug Report / Google Sheets
           |
           v
     FastAPI Backend
           |
           v
      SQLite Database
           |
           v
   Workflow Orchestrator
           |
           v
     Code Fix Engine
           |
           +--> Repository Retriever
           +--> AI Analyzer
           +--> Repair Planner
           +--> AI Fixer
           +--> Regression Test Generator
           |
           v
    Security Validation
           |
           v
    Docker Test Worker
           |
           +--> Regression must fail before fix
           +--> Tests must pass after fix
           |
           v
     Developer Review
           |
           +--> Approve
           +--> Request Changes / Retry
           |
           v
    Optional GitHub Actions
```

## Technology Stack

| Layer | Technologies |
|---|---|
| Backend | Python, FastAPI |
| Frontend | HTML, CSS, JavaScript |
| Database | SQLite, SQLAlchemy |
| AI | Gemini, Groq, optional Ollama |
| Testing | pytest, Ruff |
| Isolation | Docker |
| Version Control | Git, GitHub API |
| Configuration | python-dotenv |
| Optional Integration | Google Sheets API |

## Requirements

- Python 3.12 recommended
- Git
- Docker daemon and the project worker image
- Gemini/Groq API credentials for remote AI mode
- GitHub token for RealFixEngine
- A disposable GitHub repository for real-engine testing

## Quick Start — Linux Mint

Clone the repository:

```bash
git clone https://github.com/Rakshitha-Peddi/AutoResolve.git
cd AutoResolve
```

Create the virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

Create the configuration:

```bash
cp .env.example .env
```

For the safe demo mode, set:

```dotenv
AUTORESOLVE_REAL_ENGINE=false
AUTORESOLVE_ENABLE_PUBLISH=false
AUTORESOLVE_ENABLE_MERGE=false
```

Check the installation:

```bash
python3 check_setup.py
```

Start the application:

```bash
python3 -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Dashboard: http://127.0.0.1:8000

API documentation: http://127.0.0.1:8000/docs

## Real AI Mode

Configure `.env` with the desired backend and provider credentials.

Example:

```dotenv
AUTORESOLVE_REAL_ENGINE=true
AUTORESOLVE_AI_BACKEND=remote

AI_ENABLED_PROVIDERS=gemini,groq
AI_PRIMARY_PROVIDER=gemini
AI_FALLBACK_ENABLED=false

GEMINI_API_KEY=
GEMINI_MODEL=

GROQ_API_KEY=
GROQ_MODEL=

GITHUB_TOKEN=

AUTORESOLVE_ENABLE_PUBLISH=false
AUTORESOLVE_ENABLE_MERGE=false
```

Fill in the required values privately. Never commit actual credentials.

Build the test worker:

```bash
docker build -f docker/worker.Dockerfile \
  -t autoresolve-test-worker:python312 .
```

On Linux Mint systems using Snap Docker, configure
`AUTORESOLVE_WORKSPACE_DIR` to a directory inside the project
that Docker can access.

Verify:

```bash
AUTORESOLVE_REAL_ENGINE=true python3 check_setup.py
```

Start the server using the normal Uvicorn command.

Only test against repositories you control.

## Safety Controls

By default:

- Real AI execution is disabled.
- GitHub publishing is disabled.
- GitHub merging is disabled.
- Docker test execution is isolated from the network.
- AI-generated patches and test paths are validated.
- A regression test must fail before the fix.
- The test suite must pass after the fix.
- Real publishing and merging require explicit configuration.

Approvals in StubEngine mode are simulated. They do not merge
GitHub pull requests.

## Testing

```bash
python3 -m pytest -q
python3 -m ruff check .
```

## Project Demonstration

1. Start AutoResolve in StubEngine mode.
2. Submit a sample bug.
3. Inspect the generated proposal.
4. Request changes to demonstrate a retry.
5. Approve a proposal.
6. Switch to a properly configured isolated real-engine test.
7. Verify AI patch generation and Docker validation.
8. Review the resulting patch without enabling GitHub publishing.

## Current Limitations

- The repair pipeline primarily targets Python source files.
- A generated patch may be rejected if the model produces incorrect behavior.
- Target repository dependencies must be available inside the worker image.
- RealFixEngine currently requires GitHub repository access.
- API provider configuration does not guarantee available quota.
- Docker validation is necessary but does not guarantee a completely bug-free repair.

## Documentation

See `SETUP.md` for installation and demonstration instructions.

## Academic Project

AutoResolve 2.0 — Major Project

B.Tech Computer Science and Engineering
