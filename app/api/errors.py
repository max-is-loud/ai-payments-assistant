"""One error envelope for every failure: {error: {code, message, hint}}.

A fourth field, `detail`, carries developer text: a provider's raw response
body, or the name of an exception nothing anticipated. It goes on the wire
only when the API runs with DEBUG=1, and it is always written to the log, so
turning debug off hides nothing from whoever runs the API. It only keeps that
text off the owner's screen, where it reads as a stack dump.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent.confirm import ConfirmationError
from app.llm.base import LLMError
from app.services.escalations import EscalationNotFound
from app.stripe_.gateway import NotFound, StripeGatewayError

log = logging.getLogger(__name__)

INTERNAL_MESSAGE = "Something went wrong on our side."
INTERNAL_HINT = "Try again. If it keeps happening, the API log has the traceback."


class ApiError(Exception):
    """A deliberate HTTP failure with a stable code and a hint."""

    def __init__(self, status: int, code: str, message: str, hint: str = "") -> None:
        """Store status, code, message, hint."""
        super().__init__(message)
        self.status, self.code, self.hint = status, code, hint


def error_fields(
    code: str, message: str, hint: str = "", detail: str = "", *, debug: bool
) -> dict[str, str]:
    """The fields sent for one failure, on HTTP and SSE alike.

    The first three are written for the owner and always sent. `detail` is
    logged whenever present and sent only in debug mode.
    """
    if detail:
        log.warning("%s: %s (%s)", code, message, detail)
    fields = {"code": code, "message": message, "hint": hint}
    if debug and detail:
        fields["detail"] = detail
    return fields


def envelope(
    code: str, message: str, hint: str = "", detail: str = "", *, debug: bool = False
) -> dict[str, dict[str, str]]:
    """The wire shape."""
    return {"error": error_fields(code, message, hint, detail, debug=debug)}


def describe_exception(exc: BaseException) -> str:
    """One line naming an unexpected exception, for `detail`."""
    return f"{type(exc).__name__}: {exc}"


def install_error_handlers(app: FastAPI) -> None:
    """Map every known exception family onto the envelope, and the rest onto a 500."""

    def _debug(request: Request) -> bool:
        """Whether this process was launched with DEBUG=1."""
        return bool(request.app.state.services.settings.debug)

    @app.exception_handler(ApiError)
    async def _api(_r: Request, exc: ApiError) -> JSONResponse:
        """Deliberate errors."""
        return JSONResponse(status_code=exc.status, content=envelope(exc.code, str(exc), exc.hint))

    @app.exception_handler(ConfirmationError)
    async def _confirm(_r: Request, exc: ConfirmationError) -> JSONResponse:
        """Expired/foreign ids are 404; decided ones are 409."""
        status = 404 if exc.code == "unknown_action" else 409
        return JSONResponse(status_code=status, content=envelope(exc.code, str(exc)))

    @app.exception_handler(EscalationNotFound)
    async def _esc(_r: Request, exc: EscalationNotFound) -> JSONResponse:
        """Unknown escalation."""
        content = envelope("not_found", f"No escalation {exc}.")
        return JSONResponse(status_code=404, content=content)

    @app.exception_handler(StripeGatewayError)
    async def _stripe(request: Request, exc: StripeGatewayError) -> JSONResponse:
        """Stripe failures carry the gateway's hint; missing objects are 404."""
        status = 404 if isinstance(exc, NotFound) else 502
        content = envelope("stripe_error", str(exc), exc.hint, exc.detail, debug=_debug(request))
        return JSONResponse(status_code=status, content=content)

    @app.exception_handler(LLMError)
    async def _llm(request: Request, exc: LLMError) -> JSONResponse:
        """Model failures."""
        content = envelope("llm_error", str(exc), exc.hint, exc.detail, debug=_debug(request))
        return JSONResponse(status_code=502, content=content)

    @app.exception_handler(RequestValidationError)
    async def _validation(_r: Request, exc: RequestValidationError) -> JSONResponse:
        """Body/query validation in the same envelope."""
        message = str(exc.errors()[0]["msg"])
        content = envelope("invalid_request", message, "Check the request body.")
        return JSONResponse(status_code=422, content=content)

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception) -> JSONResponse:
        """Anything no handler above anticipated: a generic message, the cause only in debug."""
        log.exception("Unhandled exception on %s %s", request.method, request.url.path)
        content = envelope(
            "internal_error", INTERNAL_MESSAGE, INTERNAL_HINT, describe_exception(exc),
            debug=_debug(request),
        )
        return JSONResponse(status_code=500, content=content)
