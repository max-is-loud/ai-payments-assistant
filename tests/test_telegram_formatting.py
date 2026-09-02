"""The Telegram formatting boundary: text becomes HTML Telegram will never reject."""

from telegram.constants import ParseMode

from app.telegram.formatting import outgoing_message, to_telegram_html


def test_allowed_tags_pass_through() -> None:
    """Balanced <b>, <i>, and <code> are the whole dialect the customer prompt may use."""
    text = "Invoice <b>F-0001</b> is <i>due Friday</i>; reference <code>in_1</code>."
    assert to_telegram_html(text) == text


def test_reserved_characters_are_escaped() -> None:
    """A bare `<`, `>`, or `&` in prose would make Telegram reject the whole message."""
    assert to_telegram_html("Davis & Sons owe < $100 > $50") == (
        "Davis &amp; Sons owe &lt; $100 &gt; $50"
    )


def test_unknown_tags_are_stripped_not_shown() -> None:
    """A tag outside the dialect disappears; its text stays. The customer never sees markup."""
    assert to_telegram_html('<u>Paid</u> — see <a href="https://x.test">receipt</a>') == (
        "Paid — see receipt"
    )


def test_unbalanced_tags_fall_back_to_plain_text() -> None:
    """Telegram rejects an unclosed entity, so the safe output is the text with no tags."""
    assert to_telegram_html("<b>Due Friday <i>tomorrow</b>") == "Due Friday tomorrow"
    assert to_telegram_html("closed</b> before opened") == "closed before opened"


def test_code_cannot_nest_with_other_entities() -> None:
    """Telegram forbids code inside or around bold/italic; either way, send it plain."""
    assert to_telegram_html("<b>ref <code>in_1</code></b>") == "ref in_1"
    assert to_telegram_html("<code>see <b>this</b></code>") == "see this"


def test_outgoing_message_carries_html_parse_mode_and_sanitized_text() -> None:
    """Every send goes through one helper, so parse mode and sanitizing cannot drift apart."""
    kwargs = outgoing_message("Connected to <b>Acme & Co</b>.")
    assert kwargs == {"text": "Connected to <b>Acme &amp; Co</b>.", "parse_mode": ParseMode.HTML}
