# API reference

Base path `/api`. Interactive docs at `/docs`. Bug ids look like `BUG-12`; the bare number `12` also works in URLs.
Timestamps are UTC ISO-8601 (`2026-10-01T05:52:25Z`). Errors are `{"detail": "..."}`.

| Method and path | Purpose | Success | Errors |
|---|---|---|---|
| `GET /api/health` | Liveness check | 200 | |
| `GET /api/metrics` | Dashboard numbers | 200 | |
| `GET /api/bugs?status=` | Bug queue, most recently updated first. `status` is optional. | 200 | 422 bad status |
| `POST /api/bugs` | Report a bug and start the AI run | 201 + bug detail | 422 |
| `GET /api/bugs/{id}` | Full detail for the review panel | 200 | 404 |
| `POST /api/bugs/{id}/approve` | Merge the fix, notify the tester | 200 + bug detail | 404, 409 not awaiting review, 502 merge failed |
| `POST /api/bugs/{id}/feedback` | Request changes; AI retries in the background | 200 + bug detail | 404, 409, 422 blank |
| `POST /api/sheets/sync` | Pull new Google Sheet rows now | 200 `{created, count}` | 400 intake off, 502 sheet unreadable |

## Request bodies

`POST /api/bugs`: `{"title", "description", "repo", "reporter"}` (`reporter` optional; `repository` is accepted in place of `repo`).

`POST /api/bugs/{id}/feedback`: `{"feedback": "text"}`.

## Statuses

`fixing` (AI working), `awaiting_review` (fix ready), `merged`, `failed` (limit reached or AI error).

## Bug summary (queue rows)

`id, title, repo, reporter, status, iteration, max_iterations, created_at, updated_at`

## Bug detail (adds)

| Field | Meaning |
|---|---|
| `description`, `source` | Report text; `api` or `sheet` |
| `root_cause` | Latest attempt's root cause |
| `changed_files` | Latest attempt: `[{"path", "diff"}]` (unified diffs) |
| `test_results` | Latest attempt: `{"passed", "total", "failed", "tests": [{"name", "passed"}]}` |
| `branch` | Branch or PR the merge will use |
| `attempts` | Every attempt, oldest first: `iteration, at, summary, root_cause, plan, changed_files, test_results, branch, outcome` (`pending`, `changes_requested`, `approved`) |
| `history` | Timeline: `[{"at", "event", "iteration", "message"}]`. Events: `reported, fix_proposed, changes_requested, merged, tester_notified, merge_failed, notify_failed, failed` |
| `feedback` | Developer change requests: `[{"iteration", "text", "at"}]` |
| `resolved_at` | Set when merged |

## Metrics

`total, fixing, awaiting_review, merged, failed, approvals, change_requests` (counts) and
`resolution_rate, first_attempt_rate, approval_rate` (fractions 0 to 1), `avg_iterations`.
