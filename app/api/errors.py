"""One error envelope for every failure: {error: {code, message, hint}}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent.confirm import ConfirmationError
from app.llm.base import LLMError
from app.services.escalations import EscalationNotFound
from app.stripe_.gateway import NotFound, StripeGatewayError


class ApiError(Exception):
    """A deliberate HTTP failure with a stable code and a hint."""

    def __init__(self, status: int, code: str, message: str, hint: str = "") -> None:
        """Store status, code, message, hint."""
        super().__init__(message)
        self.status, self.code, self.hint = status, code, hint


def envelope(code: str, message: str, hint: str = "") -> dict[str, dict[str, str]]:
    """The wire shape."""
    return {"error": {"code": code, "message": message, "hint": hint}}


def install_error_handlers(app: FastAPI) -> None:
    """Map every known exception family onto the envelope."""

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
    async def _stripe(_r: Request, exc: StripeGatewayError) -> JSONResponse:
        """Stripe failures carry the gateway's hint; missing objects are 404."""
        status = 404 if isinstance(exc, NotFound) else 502
        content = envelope("stripe_error", str(exc), exc.hint)
        return JSONResponse(status_code=status, content=content)

    @app.exception_handler(LLMError)
    async def _llm(_r: Request, exc: LLMError) -> JSONResponse:
        """Model failures."""
        return JSONResponse(status_code=502, content=envelope("llm_error", str(exc), exc.hint))

    @app.exception_handler(RequestValidationError)
    async def _validation(_r: Request, exc: RequestValidationError) -> JSONResponse:
        """Body/query validation in the same envelope."""
        message = str(exc.errors()[0]["msg"])
        content = envelope("invalid_request", message, "Check the request body.")
        return JSONResponse(status_code=422, content=content)
