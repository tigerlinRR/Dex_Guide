#!/usr/bin/env bash
# Start the guide console (sim backend by default; runs on a dev machine).
# Real robot: GUIDE_BACKEND=real ./run.sh   (run on/near the robot, real.py must be wired)
set -e
cd "$(dirname "$0")"
source .venv/bin/activate 2>/dev/null || { echo "Create the venv first: see README.md"; exit 1; }
export GUIDE_BACKEND="${GUIDE_BACKEND:-sim}"
HOST="${HOST:-0.0.0.0}"; PORT="${PORT:-8600}"
echo "backend=$GUIDE_BACKEND  ->  http://localhost:$PORT  (reachable from a phone on the same LAN via this host's IP)"
exec uvicorn guide.server:app --host "$HOST" --port "$PORT"
