#!/usr/bin/env bash
# Run on the Mac: copy the project to the Jetson and (re)install the service.
#   ./deploy/push.sh            # default: Tailscale address
#   JETSON=rr@192.168.12.131 ./deploy/push.sh
set -euo pipefail
cd "$(dirname "$0")/.."
JETSON="${JETSON:-rr@100.82.223.73}"
rsync -az --delete \
  --exclude .venv --exclude .git --exclude VR/ --exclude '__pycache__' --exclude '*.mp3' \
  ./ "$JETSON:~/Dex_Guide/"
ssh -t "$JETSON" '~/Dex_Guide/deploy/install.sh'
