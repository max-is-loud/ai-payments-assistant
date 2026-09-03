"""Application factory. Dependencies are injected so tests run over fakes."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy import Engine
from starlette.concurrency import run_in_threadpool

from app.actions.context import Notifier
from app.api import audit, conversations, customers, escalations, summary
from app.api.errors import install_error_handlers
from app.llm.base import LLMBackend
from app.settings import Settings
from app.stripe_.gateway import StripeGateway


@dataclass
class Services:
    """Everything the routes need, built once per process."""

    settings: Settings
    gateway: StripeGateway
    llm: LLMBackend
    engine: Engine
    notify: Notifier


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Finish what a previous process left half-executed before serving the first request."""
    await run_in_threadpool(conversations.recover_interrupted, app.state.services)
    yield


def create_app(services: Services) -> FastAPI:
    """Assemble routers and error handlers around the given services."""
    app = FastAPI(
        title="AI payments assistant", docs_url="/api/docs", openapi_url="/api/openapi.json",
        lifespan=_lifespan,
    )
    app.state.services = services
    install_error_handlers(app)
    routers = (
        conversations.router, summary.router, escalations.router, customers.router, audit.router,
    )
    for router in routers:
        app.include_router(router)
    return app
