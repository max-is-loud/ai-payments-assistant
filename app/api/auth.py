"""Single-owner bearer auth on every /api route."""

import secrets

from fastapi import Request

from app.api.errors import ApiError


def require_owner(request: Request) -> None:
    """Compare the bearer token to OWNER_API_TOKEN in constant time.

    Raises:
        ApiError: 401 with the header format and the variable name.
    """
    expected = request.app.state.services.settings.owner_api_token
    header = request.headers.get("Authorization", "")
    supplied = header.removeprefix("Bearer ").strip()
    if not header.startswith("Bearer ") or not secrets.compare_digest(supplied, expected):
        raise ApiError(
            401, "unauthorized", "Missing or invalid owner token.",
            hint="Send 'Authorization: Bearer <OWNER_API_TOKEN>' using the value in .env.",
        )
