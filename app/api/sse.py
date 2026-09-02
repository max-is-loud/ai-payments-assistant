"""Server-Sent Events over a sync iterator of agent events.

This is the boundary between a turn and the browser, so it also owns two
things the routes cannot: applying the error envelope's `detail` policy to
error frames, and closing a stream whose turn crashed after the headers went
out, where no HTTP exception handler can run any more.
"""

import json
import logging
from collections.abc import Iterator
from typing import Any

from sse_starlette.sse import EventSourceResponse

from app.agent.events import AgentEvent
from app.api.errors import INTERNAL_HINT, INTERNAL_MESSAGE, describe_exception, error_fields

log = logging.getLogger(__name__)


def for_wire(event: AgentEvent, *, debug: bool) -> dict[str, Any]:
    """The frame payload; error events go through the same field policy as HTTP errors."""
    if event.type != "error":
        return event.data
    data = event.data
    return error_fields(
        data["code"], data["message"], data.get("hint", ""), data.get("detail", ""), debug=debug
    )


def sse_response(events: Iterator[AgentEvent], *, debug: bool) -> EventSourceResponse:
    """Stream events as `event: <type>` / `data: <json>` frames.

    Sync iterators run in a threadpool. A crash inside the turn becomes one
    final `error` frame, so the web app ends the turn with a sentence instead
    of an empty bubble.
    """
    def frames() -> Iterator[dict[str, str]]:
        """Convert each event into an SSE frame."""
        try:
            for event in events:
                yield {"event": event.type, "data": json.dumps(for_wire(event, debug=debug))}
        except Exception as exc:
            log.exception("Turn failed after the stream opened")
            payload = error_fields(
                "internal_error", INTERNAL_MESSAGE, INTERNAL_HINT, describe_exception(exc),
                debug=debug,
            )
            yield {"event": "error", "data": json.dumps(payload)}
    # Browser client frames on \n\n; sse-starlette defaults to \r\n separators.
    return EventSourceResponse(frames(), sep="\n")
