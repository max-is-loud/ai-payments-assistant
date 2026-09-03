"""ORM tables. Timestamps are naive UTC (see `app.db.clock`)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.clock import utcnow


class Base(DeclarativeBase):
    """Declarative base for every table."""


class Conversation(Base):
    """One chat thread. Ids are minted by the client (web) or derived from the Telegram id."""

    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    channel: Mapped[str] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Message(Base):
    """A user or assistant turn."""

    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class PendingAction(Base):
    """A proposed mutation awaiting approval. Approval executes exactly these parameters.

    `status` is one of pending, executing, executed, failed, cancelled, or
    needs_review (an execution interrupted too long ago to finish safely).
    `idempotency_key` is minted when the row is claimed and is the key Stripe
    sees for this execution, however many times it is attempted; `claimed_at`
    bounds how long that key can be trusted.
    """

    __tablename__ = "pending_actions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(String(64), index=True)
    channel: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(64))
    action: Mapped[str] = mapped_column(String(64))
    parameters_json: Mapped[str] = mapped_column(Text)
    summary: Mapped[str] = mapped_column(Text)
    prompt: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    idempotency_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class TelegramBinding(Base):
    """telegram_id → stripe customer. The Telegram id comes from the update payload, never text."""

    __tablename__ = "telegram_bindings"
    telegram_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    stripe_customer_id: Mapped[str] = mapped_column(String(64), index=True)
    customer_name: Mapped[str] = mapped_column(String(128))
    bound_at: Mapped[datetime] = mapped_column(DateTime)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ConsumedBindToken(Base):
    """A binding token that has been used, so it can never bind again.

    Only a hash of the token is kept. The primary key is the arbiter between
    two accounts presenting the same token at once: exactly one insert lands.
    """

    __tablename__ = "consumed_bind_tokens"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer)
    consumed_at: Mapped[datetime] = mapped_column(DateTime)


class Escalation(Base):
    """A customer request the bot handed to the owner."""

    __tablename__ = "escalations"
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    telegram_id: Mapped[int] = mapped_column(Integer)
    stripe_customer_id: Mapped[str] = mapped_column(String(64))
    customer_name: Mapped[str] = mapped_column(String(128))
    invoice_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class AuditEntry(Base):
    """Every executed action, with the prompt that produced it."""

    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    channel: Mapped[str] = mapped_column(String(16))
    actor: Mapped[str] = mapped_column(String(64))
    prompt: Mapped[str] = mapped_column(Text)
    action: Mapped[str] = mapped_column(String(64))
    parameters_json: Mapped[str] = mapped_column(Text)
    result_json: Mapped[str] = mapped_column(Text)
    mutation: Mapped[bool] = mapped_column(Boolean, default=False)
