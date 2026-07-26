#!/usr/bin/env bash
# Container entrypoint: wait for Postgres, migrate, seed, then serve.
set -euo pipefail

echo "Waiting for the database…"
python - <<'PY'
import sys, time
import sqlalchemy
from app.core.config import settings

deadline = time.time() + 60
while True:
    try:
        sqlalchemy.create_engine(settings.DATABASE_URL).connect().close()
        break
    except Exception as exc:
        if time.time() > deadline:
            print(f"Database unreachable: {exc}", file=sys.stderr)
            raise SystemExit(1)
        time.sleep(1)
PY

echo "Running migrations…"
alembic upgrade head

echo "Seeding reference data…"
python -m app.db.init_db

echo "Starting API…"
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'
