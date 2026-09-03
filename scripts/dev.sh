#!/usr/bin/env bash
#
# Run the API, the Telegram bot, and the web dev server together.
# One Ctrl-C stops all three, and everything under them. The bot process exits
# fast with a clear message if TELEGRAM_BOT_TOKEN is unset; API and web keep
# running.
#
# Stopping is done by walking the process tree, not by process group. `uv run`
# and `npm run` each wrap the real process, and uvicorn's reloader wraps its
# worker, so the pid of a job is never the whole job. The tree is collected
# before the first signal — once a wrapper dies its children are re-parented
# and can no longer be found from it — then every process in it is asked to
# stop, given five seconds, and killed if still there. The bot's polling loop
# does not always come down on TERM alone.
#
# Two earlier versions of this script did not work. `kill 0` signals the
# script's own group, this script included; that re-enters the trap and on
# macOS's bash 3.2 crashes it ("Segmentation fault: 11") before the bot was
# told anything — one orphaned bot per Ctrl-C, all polling Telegram with the
# same token. And `set -m` with `kill -- -pgid` depends on job control, which
# bash only reliably provides with a controlling terminal.
set -euo pipefail
cd "$(dirname "$0")/.."

pids=()

descendants() {
  local child
  for child in $(pgrep -P "$1" 2>/dev/null); do
    echo "$child"
    descendants "$child"
  done
}

stop() {
  trap - EXIT INT TERM
  local tree=() pid
  for pid in "${pids[@]}"; do
    tree+=("$pid")
    for child in $(descendants "$pid"); do tree+=("$child"); done
  done
  kill -TERM "${tree[@]}" 2>/dev/null || true
  local _tick
  for _tick in 1 2 3 4 5 6 7 8 9 10; do
    kill -0 "${tree[@]}" 2>/dev/null || break
    sleep 0.5
  done
  kill -KILL "${tree[@]}" 2>/dev/null || true
  wait 2>/dev/null || true
  exit 0
}
trap stop EXIT INT TERM

uv run uvicorn app.main:app --port 8000 --reload & pids+=("$!")
uv run python -m app.telegram.bot & pids+=("$!")
( cd web && npm run dev ) & pids+=("$!")
wait
