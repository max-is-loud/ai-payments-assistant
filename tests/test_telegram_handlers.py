"""The bot answers in private chats only.

Identity is the Telegram user, but a reply goes to the chat the update came
from. In a group that chat has other members, so an invoice list or a payment
link would be shown to everyone present. Every handler therefore checks the
chat type before it resolves a binding, calls the model, or touches Stripe,
and outside a private chat says only that the customer should message the bot
directly.
"""

import asyncio
import json
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import Engine

from app.db import pending_actions
from app.db.engine import session_scope
from app.settings import Settings
from app.telegram import handlers
from app.telegram.render import NOT_CONNECTED_TEXT
from app.telegram.turns import BotDeps
from tests.fakes.llm_fake import ScriptedLLM
from tests.fakes.stripe_fake import FakeStripeGateway

NON_PRIVATE = ["group", "supergroup", "channel"]


def _update(chat_type: str, *, text: str | None = None, callback: str | None = None) -> Any:
    """A minimal update: the chat, the user (channels have none), a message or a callback."""
    chat = SimpleNamespace(type=chat_type, id=-100, send_message=AsyncMock())
    user = None if chat_type == "channel" else SimpleNamespace(id=7)
    query = None
    if callback is not None:
        query = SimpleNamespace(
            data=callback, answer=AsyncMock(), edit_message_text=AsyncMock(),
            edit_message_reply_markup=AsyncMock(),
        )
    return SimpleNamespace(
        effective_chat=chat, effective_user=user,
        message=SimpleNamespace(text=text) if text is not None else None,
        callback_query=query,
    )


def _context(deps: Any, args: list[str] | None = None) -> Any:
    """What python-telegram-bot hands a handler: the application's bot_data and command args."""
    return SimpleNamespace(application=SimpleNamespace(bot_data={"deps": deps}), args=args or [])


class _Untouchable:
    """Stands in for the bot's dependencies where none may be used."""

    def __getattr__(self, name: str) -> Any:
        """Any attribute read means a handler reached for a dependency it must not."""
        raise AssertionError(f"deps.{name} was touched outside a private chat")


def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
    """Stands in for a `turns` function that must not be called outside a private chat."""
    raise AssertionError("a turn function ran outside a private chat")


def _sent_texts(update: Any) -> list[str]:
    """Every text the handler sent into the chat."""
    return [call.kwargs["text"] for call in update.effective_chat.send_message.await_args_list]


@pytest.fixture
def deps(engine: Engine) -> tuple[BotDeps, FakeStripeGateway, ScriptedLLM]:
    """Acme, bindable with `tok-acme`, owing one $1,200 invoice."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_acme", "Acme Corp", bind_token="tok-acme")
    fake.add_invoice("in_1", "cus_acme", 120000)
    llm = ScriptedLLM([])
    bot_deps = BotDeps(settings=Settings(_env_file=None), gateway=fake, llm=llm, engine=engine)
    return bot_deps, fake, llm


def test_private_chat_flow_is_unchanged(
    deps: tuple[BotDeps, FakeStripeGateway, ScriptedLLM],
) -> None:
    """/start <token>, a question, Pay, Confirm, and Cancel all work in a private chat."""
    bot_deps, fake, llm = deps
    context = _context(bot_deps, ["tok-acme"])

    start = _update("private")
    asyncio.run(handlers.start(start, context))
    assert _sent_texts(start) == [
        "Connected to Acme Corp. Ask me what you owe, or /logout to disconnect."
    ]

    llm._responses.extend([
        json.dumps({"reasoning": "", "action": "my_balance", "parameters": {}}),
        json.dumps({
            "reasoning": "", "action": "answer", "parameters": {"text": "1 unpaid invoice."},
        }),
    ])
    asked = _update("private", text="what do I owe?")
    asyncio.run(handlers.on_text(asked, context))
    # The model's sentence, then the server's own figure; the buttons carry the amount.
    assert _sent_texts(asked) == [
        "1 unpaid invoice.\n\nYou owe <b>$1,200.00</b> across 1 invoice."
    ]
    markup = asked.effective_chat.send_message.await_args.kwargs["reply_markup"]
    assert [b.text for b in markup.inline_keyboard[0]] == ["View IN_1", "Pay IN_1 · $1,200.00"]

    pay = _update("private", callback="pay:in_1")
    asyncio.run(handlers.on_callback(pay, context))
    proposal = pay.effective_chat.send_message.await_args.kwargs
    assert proposal["text"].startswith("Pay invoice IN_1 for $1,200.00")
    confirm_data = proposal["reply_markup"].inline_keyboard[0][0].callback_data
    action_id = confirm_data.removeprefix("confirm:")

    cancel = _update("private", callback=f"cancel:{action_id}")
    asyncio.run(handlers.on_callback(cancel, context))
    cancel.callback_query.edit_message_text.assert_awaited_once_with("Cancelled.")

    asyncio.run(handlers.on_callback(pay, context))
    second = pay.effective_chat.send_message.await_args.kwargs["reply_markup"]
    confirm = _update("private", callback=second.inline_keyboard[0][0].callback_data)
    asyncio.run(handlers.on_callback(confirm, context))
    assert "settled" in _sent_texts(confirm)[0]
    assert len([c for c in fake.calls if c[0] == "pay_invoice"]) == 1


@pytest.mark.parametrize("chat_type", NON_PRIVATE)
def test_commands_and_text_outside_a_private_chat_get_only_the_generic_instruction(
    chat_type: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/start <token>, /logout, /help, and free text: one fixed sentence, no dependency touched."""
    for name in ("bind_token", "revoke", "resolve_customer", "customer_turn"):
        monkeypatch.setattr(handlers.turns, name, _forbidden)
    context = _context(_Untouchable(), ["tok-acme"])
    for handler, update in (
        (handlers.start, _update(chat_type)),
        (handlers.logout, _update(chat_type)),
        (handlers.help_command, _update(chat_type)),
        (handlers.on_text, _update(chat_type, text="what do I owe?")),
    ):
        asyncio.run(handler(update, context))
        assert _sent_texts(update) == [handlers.NOT_PRIVATE_TEXT]
        assert update.effective_chat.send_message.await_args.kwargs["reply_markup"] is None


@pytest.mark.parametrize("chat_type", NON_PRIVATE)
@pytest.mark.parametrize("callback", ["pay:in_1", "confirm:act_1", "cancel:act_1"])
def test_callbacks_outside_a_private_chat_are_refused_before_anything_runs(
    chat_type: str, callback: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Pay, Confirm, and Cancel: answered with the instruction, nothing sent, nothing executed."""
    for name in ("resolve_customer", "propose_payment", "confirm_action", "cancel_action"):
        monkeypatch.setattr(handlers.turns, name, _forbidden)
    update = _update(chat_type, callback=callback)
    asyncio.run(handlers.on_callback(update, _context(_Untouchable())))
    update.callback_query.answer.assert_awaited_once_with(
        handlers.NOT_PRIVATE_TEXT, show_alert=True
    )
    update.effective_chat.send_message.assert_not_awaited()
    update.callback_query.edit_message_text.assert_not_awaited()
    update.callback_query.edit_message_reply_markup.assert_not_awaited()


def test_the_generic_instruction_names_no_customer_and_no_link() -> None:
    """The one sentence a group ever sees carries nothing worth seeing."""
    text = handlers.NOT_PRIVATE_TEXT.lower()
    assert "private" in text or "directly" in text
    assert "http" not in text and "invoice" not in text.replace("invoices", "")


def test_cancel_is_scoped_to_the_customer_who_proposed_the_action(
    deps: tuple[BotDeps, FakeStripeGateway, ScriptedLLM],
) -> None:
    """An action id is not authority: only the bound customer it belongs to can cancel it.

    An unbound user gets the not-connected reply; another customer's Cancel
    is refused with the same wording as an unknown id; the action stays
    pending for its owner in both cases.
    """
    bot_deps, fake, _llm = deps
    fake.add_customer("cus_maya", "Maya Chen", bind_token="tok-maya")
    acme = _context(bot_deps, ["tok-acme"])
    asyncio.run(handlers.start(_update("private"), acme))
    pay = _update("private", callback="pay:in_1")
    asyncio.run(handlers.on_callback(pay, acme))
    markup = pay.effective_chat.send_message.await_args.kwargs["reply_markup"]
    cancel_data = markup.inline_keyboard[0][1].callback_data
    action_id = cancel_data.removeprefix("cancel:")

    def status() -> str:
        """The stored action's status right now."""
        with session_scope(bot_deps.engine) as session:
            return pending_actions.get(session, action_id).status  # type: ignore[union-attr]

    stranger = _update("private", callback=cancel_data)
    stranger.effective_user.id = 8
    asyncio.run(handlers.on_callback(stranger, _context(bot_deps)))
    assert _sent_texts(stranger) == [NOT_CONNECTED_TEXT]
    stranger.callback_query.edit_message_text.assert_not_awaited()
    assert status() == "pending"

    maya_context = _context(bot_deps, ["tok-maya"])
    maya_start = _update("private")
    maya_start.effective_user.id = 9
    asyncio.run(handlers.start(maya_start, maya_context))
    maya = _update("private", callback=cancel_data)
    maya.effective_user.id = 9
    asyncio.run(handlers.on_callback(maya, maya_context))
    maya.callback_query.edit_message_text.assert_not_awaited()
    assert "expired or does not exist" in _sent_texts(maya)[0]
    assert status() == "pending"

    own = _update("private", callback=cancel_data)
    asyncio.run(handlers.on_callback(own, acme))
    own.callback_query.edit_message_text.assert_awaited_once_with("Cancelled.")
    assert status() == "cancelled"
