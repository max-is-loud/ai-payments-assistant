"""Conversation threads and their messages."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.clock import utcnow
from app.db.models import Conversation, Message


def ensure(session: Session, conversation_id: str, channel: str) -> Conversation:
    """Return the thread, creating it on first contact."""
    thread = session.get(Conversation, conversation_id)
    if thread is None:
        thread = Conversation(id=conversation_id, channel=channel, created_at=utcnow())
        session.add(thread)
        session.flush()
    return thread


def append(session: Session, conversation_id: str, role: str, content: str) -> Message:
    """Record one turn."""
    message = Message(
        conversation_id=conversation_id, role=role, content=content, created_at=utcnow()
    )
    session.add(message)
    session.flush()
    return message


def history(session: Session, conversation_id: str, limit: int = 20) -> list[Message]:
    """The most recent `limit` messages, oldest first, as the planner expects them."""
    rows = session.scalars(
        select(Message)
        .where(Message.conversation_id == conversation_id)
        .order_by(Message.id.desc())
        .limit(limit)
    ).all()
    return list(reversed(rows))
