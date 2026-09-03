"""Channel prompts: each platform gets its richest format, and neither gets the other's."""

from datetime import date

from app.actions.customer import build_customer_registry
from app.actions.owner_registry import build_owner_registry
from app.agent.prompts import (
    TELEGRAM_FORMATTING,
    WEB_FORMATTING,
    result_system,
    summary_system,
    telegram_planner_system,
    web_planner_system,
)
from app.domain.currency import USD, resolve

TODAY = date(2026, 9, 1)


def test_web_planner_speaks_markdown_only() -> None:
    """The owner's web app renders GFM; the Telegram HTML rules must never reach it."""
    system = web_planner_system(registry=build_owner_registry(), today=TODAY, currency=USD)
    assert WEB_FORMATTING in system
    assert TELEGRAM_FORMATTING not in system
    assert "Markdown" in WEB_FORMATTING and "<b>" not in WEB_FORMATTING


def test_telegram_planner_speaks_telegram_html_only() -> None:
    """The bot sends Telegram HTML; the Markdown rules must never reach it."""
    system = telegram_planner_system(registry=build_customer_registry(), today=TODAY, currency=USD)
    assert TELEGRAM_FORMATTING in system
    assert WEB_FORMATTING not in system
    assert "<b>" in TELEGRAM_FORMATTING and "bulleted" not in TELEGRAM_FORMATTING


def test_narrators_write_for_the_web() -> None:
    """The daily summary and the post-confirmation receipt only ever appear in the web app."""
    assert WEB_FORMATTING in summary_system()
    assert WEB_FORMATTING in result_system()
    assert TELEGRAM_FORMATTING not in summary_system() + result_system()


def test_the_planner_is_told_the_account_currency() -> None:
    """The planner renders cents itself, so it must be told which symbol the account uses."""
    cad = web_planner_system(registry=build_owner_registry(), today=TODAY, currency=resolve("cad"))
    assert "cents of CAD" in cad and "CA$1,200.00" in cad
    usd = web_planner_system(registry=build_owner_registry(), today=TODAY, currency=USD)
    assert "cents of USD" in usd and "$1,200.00" in usd and "CA$" not in usd
