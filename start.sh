#!/usr/bin/env bash
# Day 06. Break-Even Analysis Tool, local launcher (macOS / Linux).
#
# Day-N port convention: port = 1000 + N. Day 06 = 1006.
#
#   ./start.sh           # default port 1006
#   ./start.sh 1106      # custom port
#
set -euo pipefail

cd "$(dirname "$0")"

if [[ ! -x "../.venv/bin/python" ]]; then
  cat <<EOF
ERROR: virtual environment not found at ../.venv/

First-time setup (run from project root):
  python -m venv .venv
  ./.venv/bin/python -m pip install -r requirements.txt
  cp .env.example .env
  $EDITOR .env             # paste your DEEPSEEK_API_KEY
EOF
  exit 1
fi

if [[ ! -f "server.py" ]]; then
  echo "ERROR: server.py not found in this folder. Run from inside day-06-breakeven-tool/."
  exit 1
fi

if [[ ! -f "../.env" ]]; then
  echo "NOTICE: ../.env not found. AI scenarios will fail until you create it."
fi

PORT="${1:-1006}"
FALLBACKS=(1106 1206 1306)

port_in_use() {
  if command -v lsof >/dev/null 2>&1; then
    lsof -iTCP:"$1" -sTCP:LISTEN -t >/dev/null 2>&1
  else
    (echo > "/dev/tcp/127.0.0.1/$1") >/dev/null 2>&1
  fi
}

if port_in_use "$PORT"; then
  echo "NOTICE: port $PORT is in use. Trying ${FALLBACKS[*]}..."
  found=""
  for p in "${FALLBACKS[@]}"; do
    if ! port_in_use "$p"; then
      PORT="$p"
      found="1"
      break
    fi
  done
  if [[ -z "$found" ]]; then
    echo "ERROR: no fallback port free. Pass an explicit port: ./start.sh 1234"
    exit 1
  fi
fi

(
  sleep 2
  if command -v open >/dev/null 2>&1; then
    open "http://127.0.0.1:${PORT}/"
  elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "http://127.0.0.1:${PORT}/" >/dev/null 2>&1 || true
  fi
) &

echo
echo "Starting Day 06. Break-Even Analysis Tool on port ${PORT}..."
echo "Local URL: http://127.0.0.1:${PORT}/"
echo "Press Ctrl+C to stop."
echo

PYTHONIOENCODING=utf-8 ../.venv/bin/python server.py --port "$PORT"
