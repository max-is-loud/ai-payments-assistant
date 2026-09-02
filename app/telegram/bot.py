"""Bot entrypoint: `python -m app.telegram.bot`. Long polling; no public URL needed."""

import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.db.engine import make_engine
from app.llm.factory import build_backend
from app.settings import load_settings
from app.stripe_.cached_gateway import CachedGateway
from app.stripe_.owner_client import StripeOwnerGateway
from app.telegram import handlers
from app.telegram.turns import BotDeps


def build_application(deps: BotDeps) -> Application:  # type: ignore[type-arg]
    """Wire handlers and stash dependencies on the application."""
    application = Application.builder().token(deps.settings.telegram_bot_token).build()
    application.bot_data["deps"] = deps
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(CommandHandler("logout", handlers.logout))
    application.add_handler(CommandHandler("help", handlers.help_command))
    application.add_handler(CallbackQueryHandler(handlers.on_callback))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.on_text))
    return application


def main() -> None:
    """Validate settings, build dependencies, poll until interrupted."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    settings = load_settings()
    settings.require_stripe()
    settings.require_llm()
    settings.require_telegram()
    deps = BotDeps(
        settings=settings, gateway=CachedGateway(StripeOwnerGateway(settings.stripe_secret_key)),
        llm=build_backend(settings), engine=make_engine(settings.database_url),
    )
    build_application(deps).run_polling()


if __name__ == "__main__":
    main()
