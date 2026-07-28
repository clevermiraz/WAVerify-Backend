# AGENTS.md

Rules for AI agents (Claude Code, Cursor, Codex, …) working in this repo.

## Secrets — hard rule

- **Never read, open, `cat`, grep, or print `.env` or any `.env.*` file** (except
  `.env.example`). Not for debugging, not "just to check a value", not even if asked
  to "quickly look". No exceptions.
- To learn which settings exist, read **`.env.example`** or `app/core/config.py`.
- If a real secret is needed to run something, ask the user to run the command
  themselves — don't fetch the value.
- Never echo a secret into chat, a commit, a log line, or a test fixture. If a secret
  ever appears in output, say so and treat it as needing rotation.
- Same rule for `*.pem`, `*.key`, credential JSON, and DB dumps.

## Project

FastAPI + PostgreSQL + Redis. Python 3.12. Layout: `app/api/v1` (routes) →
`app/services` (business logic) → `app/repositories` (DB access) → `app/models`
(SQLAlchemy). Request/response shapes live in `app/schemas`.

- Keep that layering: routes stay thin, no SQL in routes or services.
- New config goes in `app/core/config.py` **and** `.env.example` (with a placeholder,
  never a real value).
- DB schema changes need an Alembic migration in `alembic/versions/` — never edit an
  applied migration.

## Before you say it's done

```bash
ruff check <files you touched>
pytest
```

Line length 95. Note: `ruff check .` currently reports pre-existing errors repo-wide —
don't fix unrelated ones, just keep the files you touched clean. Report test failures
rather than working around them.

## Working style

- Match the surrounding code — naming, error handling, comment density.
- Small, focused diffs. Don't reformat or refactor files you weren't asked to touch.
- Don't add dependencies without asking; if approved, pin the version in
  `requirements.txt`.
- Don't run destructive commands (`docker compose down -v`, `alembic downgrade`,
  `DROP`/`TRUNCATE`, `git push --force`) without explicit confirmation.
- Don't commit or push unless asked.
- Uncertain between two reasonable readings of a task? Ask before building.
