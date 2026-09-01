#!/usr/bin/env bash
#
# Run the same two checks CI runs against the documentation/ vault.
#
# This script deliberately lives OUTSIDE documentation/ because it contains the
# literal wikilink pattern, which the guard below would otherwise flag in its
# own source.
#
# Usage: ./scripts/check-docs.sh
set -uo pipefail

cd "$(dirname "$0")/.."

status=0

echo "==> 1/2  no wikilinks in documentation/"
if grep -rn --include='*.md' -e '\[\[' documentation/; then
  echo "FAIL: wikilinks found. Use relative markdown links with the .md" >&2
  echo "      extension instead: [Text](../path/to/note.md)" >&2
  status=1
else
  echo "ok"
fi

echo "==> 2/2  every relative doc link resolves"
if ! command -v lychee >/dev/null 2>&1; then
  echo "SKIP: lychee not installed (brew install lychee)" >&2
else
  if lychee --offline --no-progress --include-fragments 'documentation/**/*.md'; then
    echo "ok"
  else
    echo "FAIL: broken links in documentation/" >&2
    status=1
  fi
fi

exit "$status"
