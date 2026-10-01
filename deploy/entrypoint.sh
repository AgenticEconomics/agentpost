#!/bin/bash
set -e

# ── Configuration ────────────────────────────────────────────────────────────
AGENTPOST_ROOT="${AGENTPOST_ROOT:-/var/lib/agentpost}"
API_HOST="${AGENTPOST_API_HOST:-0.0.0.0}"
API_PORT="${AGENTPOST_API_PORT:-8765}"

# ── Ensure data directory is writable ────────────────────────────────────────
# When a Docker volume is first mounted it may be owned by root.
# Fix ownership so the non-root user (uid 1000) can write to it.
if [ -d "$AGENTPOST_ROOT" ]; then
    # Only chown if we are running as root (e.g., via docker exec or override)
    if [ "$(id -u)" = "0" ]; then
        chown -R 1000:1000 "$AGENTPOST_ROOT"
    fi
fi

# ── Start uvicorn ────────────────────────────────────────────────────────────
exec uvicorn app.main:app \
    --host "$API_HOST" \
    --port "$API_PORT" \
    --log-level info \
    --access-log
