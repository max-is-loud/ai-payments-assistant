"""Send a message to a customer from outside the bot process (the API's approve path)."""

import asyncio
import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from app.actions.context import Notifier, no_notifier
from app.telegram.formatting import outgoing_message

log = logging.getLogger(__name__)


def make_notifier(token: str) -> Notifier:
    """A sync notifier over the Bot API, or a no-op when no token is configured."""
    if not token:
        return no_notifier

    def send(telegram_id: int, text: str, url: str | None) -> bool:
        """Deliver one message with an optional link button; False on any Telegram error."""
        async def _go() -> None:
            """Open a short-lived Bot session and send."""
            markup = None
            if url:
                row = [InlineKeyboardButton("Pay on Stripe", url=url)]
                markup = InlineKeyboardMarkup([row])
            async with Bot(token) as bot:
                await bot.send_message(
                    chat_id=telegram_id, **outgoing_message(text), reply_markup=markup
                )
        try:
            asyncio.run(_go())
            return True
        except TelegramError as exc:
            log.warning("Telegram notification to %s failed: %s", telegram_id, exc)
            return False

    return send
