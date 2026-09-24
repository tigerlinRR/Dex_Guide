#!/usr/bin/env bash
# Run ON the Jetson, from the project dir: sets up the venv and the boot service.
#   ./deploy/install.sh
set -euo pipefail
cd "$(dirname "$0")/.."
DIR="$(pwd)"; USER_NAME="$(id -un)"; USER_ID="$(id -u)"

# The Jetson lacks python3.12-venv (no ensurepip), so build the venv without pip and
# install into it with the system pip (--python) instead of apt-installing anything.
mkdir -p logs
[ -x .venv/bin/python ] || python3 -m venv --without-pip .venv
python3 -m pip --python .venv/bin/python install -q -r requirements.txt

sed -e "s#@USER@#$USER_NAME#g" -e "s#@UID@#$USER_ID#g" -e "s#@DIR@#$DIR#g" \
  deploy/dex-guide.service | sudo tee /etc/systemd/system/dex-guide.service >/dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now dex-guide
sudo systemctl restart dex-guide
sleep 2
systemctl --no-pager --lines=5 status dex-guide || true
curl -fsS http://127.0.0.1:8600/api/state >/dev/null && echo "OK: console up on :8600"
