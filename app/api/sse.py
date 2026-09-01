"""Serialise agent events as Server-Sent Events."""

import json
from collections.abc import Iterator

from sse_starlette.sse import EventSourceResponse

from app.agent.events import AgentEvent


def sse_response(events: Iterator[AgentEvent]) -> EventSourceResponse:
    """Stream events as `event: <type>` / `data: <json>` frames.

    Sync iterators run in a threadpool.
    """
    def frames() -> Iterator[dict[str, str]]:
        """Convert each event into an SSE frame."""
        for event in events:
            yield {"event": event.type, "data": json.dumps(event.data)}
    # Browser client frames on \n\n; sse-starlette defaults to \r\n separators.
    return EventSourceResponse(frames(), sep="\n")
