"""Time the reads the owner web app makes on load, against a running API.

Run with the API up: `make timing` (`uv run python -m scripts.time_reads`). Each read is timed
alone, then the three no-LLM poll reads are fired together the way the page
fires them, so the wall time the owner actually waits is measured, not just
the sum of parts. The token comes from the same `.env` the API reads.
"""

import sys
import threading
import time
import urllib.error
import urllib.request

from app.settings import load_settings

BASE = "http://127.0.0.1:8000"
SEQUENTIAL = [
    "/api/conversations/timing",
    "/api/escalations",
    "/api/summary/today?narrate=false",
    "/api/summary/series",
    "/api/summary/today",
]
POLL = ["/api/summary/today?narrate=false", "/api/summary/series", "/api/escalations"]


def timed(path: str, token: str) -> float:
    """Seconds one GET takes to return its full body."""
    request = urllib.request.Request(BASE + path, headers={"Authorization": f"Bearer {token}"})
    started = time.perf_counter()
    with urllib.request.urlopen(request) as response:
        response.read()
    return time.perf_counter() - started


def main() -> None:
    """Print one line per read, then the parallel poll's wall time."""
    token = load_settings().owner_api_token
    try:
        for path in SEQUENTIAL:
            print(f"{path:38s} {timed(path, token):6.2f}s")
    except urllib.error.URLError as exc:
        sys.exit(f"Could not reach {BASE}: {exc.reason}. Is `make dev` running?")
    each: dict[str, float] = {}
    threads = [
        threading.Thread(target=lambda p=path: each.__setitem__(p, timed(p, token)))
        for path in POLL
    ]
    started = time.perf_counter()
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    wall = time.perf_counter() - started
    parts = ", ".join(f"{seconds:.2f}" for seconds in each.values())
    print(f"{'poll reads fired together (wall)':38s} {wall:6.2f}s  (each: {parts})")


if __name__ == "__main__":
    main()
