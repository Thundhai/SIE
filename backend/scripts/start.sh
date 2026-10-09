#!/usr/bin/env bash
# Production-safe startup wrapper for the Render SIE backend service.
#
# Replaces the previous inline Start Command (`alembic upgrade head &&
# python scripts/bootstrap_dev_identity.py && python scripts/
# bootstrap_dev_demo_data.py && uvicorn ...`), which unconditionally ran
# both dev-only bootstrap scripts regardless of DEV_MODE. Those scripts
# correctly fail closed (sys.exit(1)) when DEV_MODE is not "true" (see
# their own docstrings) -- so a deployment with DEV_MODE=false could
# never actually start: the `&&` chain aborted before uvicorn ever ran.
#
# This script preserves that fail-closed behavior inside the scripts
# themselves untouched -- it simply stops invoking them at all unless
# DEV_MODE (and, for demo data, SIE_DEV_DEMO_DATA) is actually "true",
# which is the same condition the scripts already enforce internally.
#
# `set -euo pipefail` ensures a genuine failure anywhere in this script
# (a real migration error, a real bootstrap crash while DEV_MODE=true)
# still aborts startup with a non-zero exit -- nothing here is silenced
# with `|| true` or similar.
set -euo pipefail

alembic upgrade head

if [ "${DEV_MODE:-}" = "true" ]; then
  python scripts/bootstrap_dev_identity.py

  if [ "${SIE_DEV_DEMO_DATA:-}" = "true" ]; then
    python scripts/bootstrap_dev_demo_data.py
  fi
fi

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
