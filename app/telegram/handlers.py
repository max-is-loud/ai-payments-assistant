"""python-telegram-bot handlers. Thin: read the update, call sync glue in a thread, reply.

Every handler starts with the same check: the update came from a private
chat. Identity is the Telegram user, but replies go to the chat, and in a
group that chat has other members who would see the invoice list and the
payment buttons. Outside a private chat nothing is resolved, called, or
executed; the reply is one fixed sentence.
"""

import asyncio

from telegram import InlineKeyboardMarkup, Update
from telegram.constants import ChatType
from telegram.ext import ContextTypes

from app.agent.confirm import UnknownAction
from app.telegram import turns
from app.telegram.formatting import outgoing_message
from app.telegram.render import NOT_CONNECTED_TEXT, Reply, reply_for

WELCOME = ("Hi, I'm Ledger. I can tell you what you owe and take payment for your invoices. "
           "To connect your account, open the link the business sent you.")
HELP = (
    "Ask me things like \"what do I owe?\" or \"show my invoices\". /logout disconnects this chat."
)
NOT_PRIVATE_TEXT = (
    "I only work in a private chat. Please message me directly to see or pay your invoices."
)


def _deps(context: ContextTypes.DEFAULT_TYPE) -> turns.BotDeps:
    """Dependencies stored on the application at startup."""
    return context.application.bot_data["deps"]


def _is_private(update: Update) -> bool:
    """Whether the update came from a one-to-one chat with the bot."""
    return update.effective_chat is not None and update.effective_chat.type == ChatType.PRIVATE


async def _send(update: Update, reply: Reply) -> None:
    """Send a Reply to the effective chat, through the HTML formatting boundary."""
    markup = InlineKeyboardMarkup(reply.buttons) if reply.buttons else None
    assert update.effective_chat is not None
    await update.effective_chat.send_message(**outgoing_message(reply.text), reply_markup=markup)


async def _refuse_unless_private(update: Update) -> bool:
    """Reply with the fixed sentence and return True when the chat is not private."""
    if _is_private(update):
        return False
    await _send(update, Reply(NOT_PRIVATE_TEXT))
    return True


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/start [token]`: bind when a token is present, otherwise explain."""
    if await _refuse_unless_private(update):
        return
    assert update.effective_user is not None
    if not context.args:
        await _send(update, Reply(WELCOME))
        return
    name = await asyncio.to_thread(
        turns.bind_token, _deps(context), update.effective_user.id, context.args[0]
    )
    if name is None:
        await _send(update, Reply("That link isn't valid. Ask the business for a new one."))
    else:
        connected = f"Connected to {name}. Ask me what you owe, or /logout to disconnect."
        await _send(update, Reply(connected))


async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/logout`: revoke this chat's binding."""
    if await _refuse_unless_private(update):
        return
    assert update.effective_user is not None
    revoked = await asyncio.to_thread(turns.revoke, _deps(context), update.effective_user.id)
    await _send(update, Reply("Disconnected." if revoked else "This chat wasn't connected."))


async def help_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/help`."""
    if await _refuse_unless_private(update):
        return
    await _send(update, Reply(HELP))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Free text → agent turn, if bound."""
    if await _refuse_unless_private(update):
        return
    assert update.effective_user is not None
    assert update.message is not None and update.message.text
    deps = _deps(context)
    binding = await asyncio.to_thread(turns.resolve_customer, deps, update.effective_user.id)
    if binding is None:
        await _send(update, Reply(NOT_CONNECTED_TEXT))
        return
    events = await asyncio.to_thread(turns.customer_turn, deps, binding, update.message.text)
    await _send(update, reply_for(events))


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline buttons: pay:<invoice>, confirm:<action>, cancel:<action>.

    A callback can only arrive on a message the bot sent, and the bot never
    sends into a group; the check still runs, because a forwarded message or
    a future handler must not be the thing that decides.
    """
    query = update.callback_query
    assert query is not None and query.data
    if not _is_private(update):
        await query.answer(NOT_PRIVATE_TEXT, show_alert=True)
        return
    assert update.effective_user is not None
    await query.answer()
    deps = _deps(context)
    kind, _, ref = query.data.partition(":")
    # Every button, Cancel included, acts as the bound customer: the action
    # id in the callback names a row, and the binding says whose it may be.
    binding = await asyncio.to_thread(turns.resolve_customer, deps, update.effective_user.id)
    if binding is None:
        await _send(update, Reply(NOT_CONNECTED_TEXT))
        return
    if kind == "cancel":
        if await asyncio.to_thread(turns.cancel_action, deps, binding, ref):
            await query.edit_message_text("Cancelled.")
        else:
            await _send(update, Reply(str(UnknownAction())))
    elif kind == "pay":
        events = await asyncio.to_thread(turns.propose_payment, deps, binding, ref)
        await _send(update, reply_for(events))
    elif kind == "confirm":
        await query.edit_message_reply_markup(None)
        await _send(update, await asyncio.to_thread(turns.confirm_action, deps, binding, ref))
