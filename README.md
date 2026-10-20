# AutoResolve — End-to-End MVP

AutoResolve is a human-in-the-loop system for automated software bug resolution. A tester reports a defect, the system retrieves relevant repository context, proposes a repair, validates it in an isolated workspace, presents evidence to a developer, accepts feedback, and only merges after approval.

## Architecture

```text
Tester -> FastAPI/SQLite -> Code Fix Agent -> Isolated Execution -> Developer Review
                                      ^                  |                 |
                                      |                  +---- PASS -------+
                                      |                                     |
                                      +---- developer feedback <------------+
                                                                    |
                                                               Git branch/merge
                                                                    |
                                                               Tester notification
```

## Current implementation

Without configuration the app runs a deterministic demo engine (no keys needed). With `AUTORESOLVE_REAL_ENGINE=true` it uses OpenAI to analyse and fix bugs in a GitHub repo, validates in a Docker sandbox, opens a Pull Request, and merges it only after human approval (`AUTORESOLVE_ENABLE_MERGE=true`).

## Real setup

See **SETUP.md** for the full step-by-step task list, `.env.example` for settings and
`python check_setup.py` to verify your setup.

## Run (demo mode)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

Open http://127.0.0.1:8000

## Automated demo

```bash
python run_demo.py
```

The demo creates an intentional None-handling bug, generates a real unified diff, applies it in a temporary copied workspace, runs pytest, supports developer feedback, then applies the approved patch to the demo repository and creates a local Git branch/merge.

## Tests

```bash
pytest -q
```

## Next adapters

- Real Anthropic/OpenAI LLM client
- Docker execution sandbox
- GitHub PR API
- Google Sheets polling
- Email notifications
- AST/embedding retrieval

Human approval remains mandatory before merge.
