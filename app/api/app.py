"""Application factory. Dependencies are injected so tests run over fakes."""

from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy import Engine

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


def create_app(services: Services) -> FastAPI:
    """Assemble routers and error handlers around the given services."""
    app = FastAPI(
        title="AI payments assistant", docs_url="/api/docs", openapi_url="/api/openapi.json"
    )
    app.state.services = services
    install_error_handlers(app)
    routers = (
        conversations.router, summary.router, escalations.router, customers.router, audit.router,
    )
    for router in routers:
        app.include_router(router)
    return app
