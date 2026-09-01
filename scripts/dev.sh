#!/usr/bin/env bash
#
# Run the API, the Telegram bot, and the web dev server together.
# One Ctrl-C stops all three. The bot process exits fast with a clear message if
# TELEGRAM_BOT_TOKEN is unset; API and web keep running.
set -euo pipefail
cd "$(dirname "$0")/.."

trap 'kill 0' EXIT INT TERM

uv run uvicorn app.main:app --port 8000 --reload &
uv run python -m app.telegram.bot &
( cd web && npm run dev ) &
wait
