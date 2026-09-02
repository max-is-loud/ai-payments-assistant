"""The Telegram formatting boundary: text becomes HTML Telegram will never reject.

Telegram renders a small HTML dialect under `parse_mode="HTML"` and rejects
the *whole message* on any parse error — an unbalanced tag, a tag it does not
know, a bare `<`. A customer would then receive nothing. So no text reaches
`send_message` except through `outgoing_message`, which keeps only the tags
the customer prompt is allowed to use, escapes everything else, and falls
back to tag-free text when the tags do not balance. The prompt asks for good
formatting; this module guarantees a deliverable message.

Text that is composed in Python (receipts, "Connected to …") goes through the
same boundary, so a customer name containing `&` is escaped rather than
rejected. A name that itself contains a literal `<b>` would be read as a tag;
that is accepted as a non-problem for a demo whose names come from the seed.
"""

import html
import re
from typing import Any

from telegram.constants import ParseMode

ALLOWED_TAGS = ("b", "i", "code")

_ALLOWED = re.compile(r"(</?(?:b|i|code)>)")
_ANY_TAG = re.compile(r"</?[A-Za-z][^<>]*>")


def _plain(text: str) -> str:
    """Every tag removed, reserved characters escaped: readable and always deliverable."""
    return html.escape(_ANY_TAG.sub("", text), quote=False)


def to_telegram_html(text: str) -> str:
    """Make `text` safe for Telegram's HTML parse mode, keeping balanced allowed tags.

    Tags outside `ALLOWED_TAGS` are removed with their text kept. Telegram
    forbids `code` from containing or being contained by any other entity,
    so such nesting — like any unbalanced tag — downgrades the whole message
    to plain text rather than risk a rejected send.
    """
    stripped = _ANY_TAG.sub(lambda m: m.group(0) if _ALLOWED.fullmatch(m.group(0)) else "", text)
    pieces = _ALLOWED.split(stripped)
    out: list[str] = []
    open_tags: list[str] = []
    for index, piece in enumerate(pieces):
        if index % 2 == 0:
            out.append(html.escape(piece, quote=False))
            continue
        name = piece.strip("</>")
        if piece.startswith("</"):
            if not open_tags or open_tags[-1] != name:
                return _plain(text)
            open_tags.pop()
        else:
            if open_tags and (name == "code" or open_tags[-1] == "code"):
                return _plain(text)
            open_tags.append(name)
        out.append(piece)
    if open_tags:
        return _plain(text)
    return "".join(out)


def outgoing_message(text: str) -> dict[str, Any]:
    """`send_message` keyword arguments for `text`: sanitized HTML plus its parse mode.

    The single place parse mode is set, so a send cannot be HTML-mode with
    unsanitized text or sanitized text with no parse mode.
    """
    return {"text": to_telegram_html(text), "parse_mode": ParseMode.HTML}
