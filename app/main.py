"""uvicorn entrypoint: `uvicorn app.main:app`."""

from app.api.app import Services, create_app
from app.db.engine import make_engine
from app.llm.factory import build_backend
from app.settings import load_settings
from app.stripe_.cached_gateway import CachedGateway, warm_in_background
from app.stripe_.owner_client import StripeOwnerGateway
from app.telegram.notify import make_notifier


def build_services() -> Services:
    """Validate configuration and construct real dependencies.

    Raises:
        ConfigError: A missing or invalid setting; the message says which.
    """
    settings = load_settings()
    settings.require_stripe()
    settings.require_llm()
    settings.require_owner_token()
    return Services(
        settings=settings,
        gateway=CachedGateway(StripeOwnerGateway(settings.stripe_secret_key)),
        llm=build_backend(settings),
        engine=make_engine(settings.database_url),
        notify=make_notifier(settings.telegram_bot_token),
    )


services = build_services()
# The first page after `make dev` should not pay for the cold listing itself.
warm_in_background(services.gateway)
app = create_app(services)
