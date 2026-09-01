---
title: AI payments assistant — implementation plan
status: active
updated: 2026-09-01
---

# AI Payments Assistant Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the three deliverables of the Replicant.ai take-home — an owner web app, a customer Telegram bot, and a seed script — over a fresh Stripe sandbox, with the agent's guardrails enforced in Python.

**Architecture:** A synchronous FastAPI backend owns a propose→execute→narrate agent loop: the LLM returns one validated JSON action per step, deterministic Python executes it, mutations pause for confirmation and execute the *stored* action on approval. Two action registries (owner, customer) share one executor; the customer registry has no action that accepts a `customer_id`. Stripe is the source of truth for money; SQLite holds conversations, pending confirmations, Telegram bindings, escalations, and the audit log. The Telegram bot is a second process importing the same package and sharing the SQLite file.

**Tech Stack:** Python 3.12 · uv · FastAPI 0.141 · sse-starlette 3.4 · SQLAlchemy 2.0 · pydantic-settings 2.15 · stripe 15.6 (API `2026-08-26.dahlia`) · anthropic 1.3 · openai 3.6 · python-telegram-bot 22.8 · Faker 40 · pytest 9 · ruff · Vite 8 + React 19 + TypeScript.

**Spec:** [AI payments assistant — design](../specs/2026-09-01-ai-payments-assistant-design.md). Requirements of record: [Assignment brief](../assignment-brief.md). Code rules: [Code conventions](../code-conventions.md).

## Global Constraints

Every task's requirements implicitly include this section.

- **Every Python function, class, and module carries a Google-style docstring** written for humans (tests included). `ruff` rule set `D` with `convention = "google"` enforces this; `make lint` must pass before every commit.
- **Full type annotations** on every parameter and return value.
- **No god files:** one reason to change per module; past 300 lines justify, past 400 split. Never `utils.py`, `helpers.py`, `common.py`, `misc.py`.
- **Single-source every business rule.** `TELEGRAM_PAYMENT_CEILING_CENTS = 200_000`, `BINDING_INACTIVITY = timedelta(days=14)`, `MAX_AGENT_ITERATIONS = 5` live only in `app/domain/policy.py`.
- **`metadata.demo_created_at` is read in exactly one function**, `app/domain/mapping.py:_occurred_at`. Nothing downstream reads that field.
- **The customer registry contains no action with a `customer_id` parameter.** A test asserts it mechanically.
- **Secrets only from the environment** via `pydantic-settings`. `.env` is gitignored; `.env.example` is committed with the working default `OWNER_API_TOKEN=dev-owner-token`. Only `sk_test_` Stripe keys are accepted.
- **Stripe API version pinned** to `2026-08-26.dahlia` in one constant, passed to `StripeClient(stripe_version=...)`.
- **Telegram uses long polling.** No webhooks, no tunnel.
- **All tests run without an LLM and without network.** The single live LLM smoke test sits behind the `live_llm` marker and is deselected by default.
- **Money is integer cents everywhere in Python**; formatting to dollars happens only in `app/domain/money.py:format_usd` and in the web app.
- **Commit after every task** with a conventional-commit message (`feat:`, `test:`, `chore:`, `docs:`). Never commit `.env`, `data/`, `web/node_modules`, or the Telegram token.
- Documentation edits under `documentation/` follow `.claude/rules/documentation.md`: relative `.md` links, no wikilinks, never rename or move a vault file, run `./scripts/check-docs.sh`.

## Decisions this plan makes that the spec leaves open

Recorded here so implementers do not re-derive them.

| Question | Decision | Why |
| --- | --- | --- |
| Sync or async backend | **Synchronous** everywhere except Telegram handlers, which call the agent via `asyncio.to_thread`. FastAPI runs `def` routes in its threadpool; `sse-starlette` accepts a plain `Iterator`. | stripe-python, SQLAlchemy, and the LLM SDKs are all sync; one execution model, no bridging code. |
| What "payments" are | **PaymentIntents**, listed with `expand=["data.latest_charge", "data.customer"]`. A PaymentIntent with no `latest_charge` was never attempted and maps to `None`. | Seed metadata is set on the PaymentIntent, so `demo_created_at` is read from the object we created rather than relying on charge propagation. Declines still appear (failed charge, `outcome.reason == "insufficient_funds"`). |
| Refund parameter | Owner action is **`refund_payment(payment_id)`** (a `pi_…` id), refunding via `refunds.create({"payment_intent": …})`. The spec's table says `refund_charge`; the rename keeps the parameter and the name honest. | The planner sees `payment_id` in `query_payments` results; no charge-id lookup step needed. |
| How the bot pays | Seed attaches `pm_card_visa` to every customer as the default payment method; `pay_invoice` calls `invoices.pay(invoice_id)` which charges the card on file. | A complete in-bot payment under $2,000, demonstrable without a browser. |
| Owner approval of an escalation | Marks it approved and sends the customer the invoice's `hosted_invoice_url` on Telegram. The bot never completes a ≥ $2,000 payment; the customer pays on Stripe's hosted page. | Matches the spec's loop diagram ("customer receives link") and the brief's hard rule. |
| Where binding tokens live | `metadata.telegram_bind_token` on the Stripe customer, minted by the seed script. The bot resolves `/start <token>` by listing customers and matching metadata. | Seed touches only Stripe; the SQLite file can be deleted freely. Customer search has indexing lag; a list-scan of ten customers does not. |
| The `confirm` terminator | Not an action the LLM chooses. When the planner selects an action whose spec is `mutation=True`, the loop resolves a human-readable summary, stores a `PendingAction`, emits a `confirmation` event, and stops. `answer` and `clarify` are the LLM-chosen terminators. | Prevents the model from deciding whether something needs approval. |
| The narrator | The final `answer` in the loop is written by the planner (it has seen the observations). A separate `narrate_*` call is used where no planner is in the loop: the daily summary endpoint and the post-confirmation result. | One extra LLM round-trip only where it is needed. |
| Telegram output | The bot's free-text replies come from the planner, which only ever sees **amount-free** observations (`my_invoices` returns numbers, statuses, due dates, and view URLs). Amounts appear exactly once: on the payment confirmation prompt. | Makes the spec's "1 unpaid invoice, tap to view" stance structural rather than prompted. |
| "Today" boundaries | The machine's local timezone, resolved in `app/domain/periods.py`. | The reviewer's day is the reviewer's day. |
| Next-day demos | `python -m seed --today-only` adds a fresh day of activity for existing seeded customers. | A reviewer who seeds one evening and demos the next morning still gets a real summary. |
| Extra endpoints beyond the spec | `POST /api/conversations/{id}/cancel` (dismiss a pending action) and `?narrate=false` on `GET /api/summary/today` (facts only, for the live rail). | Small, resource-shaped, documented in the README's API section. |
| Default LLM models | Anthropic `claude-opus-5` with `output_config={"effort": "low"}`; OpenAI `gpt-5.4-mini`. Overridable with `LLM_MODEL`. | Chat-shaped planner calls are latency-sensitive; low effort keeps the loop snappy. Server-side refusal fallbacks are deliberately not enabled — one fewer beta flag in a take-home. |

## File map

```
pyproject.toml  .python-version  Makefile  .env.example  scripts/dev.sh
app/
  settings.py                 Settings + ConfigError, per-entrypoint require_*()
  main.py                     `app = create_app()` for uvicorn
  domain/
    policy.py                 the three numbers a reviewer looks for
    money.py                  format_usd
    models.py                 Customer, Payment, Invoice, Refund (frozen dataclasses)
    mapping.py                Stripe objects → domain; the only reader of demo_created_at
    periods.py                Window, local day boundaries, date ranges
    summary.py                DailyFacts, build_daily_facts, period_totals
  stripe_/
    gateway.py                StripeGateway Protocol + StripeGatewayError family
    owner_client.py           StripeOwnerGateway over StripeClient (the only Stripe import)
    customer_client.py        CustomerScopedGateway — bound to one customer id
  db/
    engine.py                 make_engine, session_scope, WAL pragma
    clock.py                  utcnow (naive UTC for SQLite)
    models.py                 Conversation, Message, PendingAction, TelegramBinding, Escalation, AuditEntry
    conversations.py  pending_actions.py  bindings.py  escalations.py  audit.py
  llm/
    base.py                   ChatMessage, LLMBackend Protocol, LLMError, extract_json_object
    anthropic_backend.py  openai_backend.py  factory.py
  agent/
    schema.py                 ActionCall, ActionSpec, Proposal, Registry, terminal params
    events.py                 AgentEvent + to_jsonable
    executor.py               parse_call, resolve — the LLM boundary
    loop.py                   run_turn: the propose→execute loop
    confirm.py                execute_pending: runs the stored action, never a re-plan
    prompts.py                personality + system prompt builders
    narrator.py               narrate_summary, narrate_result
  actions/
    context.py                OwnerContext, CustomerContext
    owner_reads.py  owner_mutations.py  owner_registry.py
    customer.py               customer actions + build_customer_registry
  services/
    escalations.py            approve_and_notify (shared by chat action and REST route)
  api/
    app.py  auth.py  errors.py  sse.py
    conversations.py  summary.py  escalations.py  customers.py  audit.py
  telegram/
    bot.py  handlers.py  render.py  notify.py
seed/
  __main__.py  dataset.py  writer.py  inventory.py  report.py
tests/
  conftest.py  fakes/stripe_fake.py  fakes/llm_fake.py  test_*.py
web/                          Vite + React + TypeScript (scaffolded, then replaced)
README.md  write-up.md
```

---

### Task 1: Python scaffold, settings, and quality gates

**Files:**
- Create: `pyproject.toml`, `.python-version`, `Makefile`, `.env.example`, `app/__init__.py`, `app/settings.py`, `tests/__init__.py`, `tests/test_settings.py`
- Modify: `.gitignore` (append), `.serena/project.yml` (no change needed — languages already list python and typescript)

**Interfaces:**
- Produces: `Settings` (pydantic-settings), `ConfigError(RuntimeError)`, `Settings.require_stripe()`, `Settings.require_llm()`, `Settings.require_telegram()`, `Settings.require_owner_token()`, `load_settings() -> Settings`.

- [ ] **Step 1: Create `pyproject.toml`, `.python-version`, `.env.example`, `.gitignore` additions**

`pyproject.toml`:

```toml
[project]
name = "ai-payments-assistant"
version = "0.1.0"
description = "AI assistant over a Stripe account: owner web app, customer Telegram bot, seed script."
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.141,<1",
  "uvicorn[standard]>=0.52,<1",
  "sse-starlette>=3.4,<4",
  "pydantic>=2.13,<3",
  "pydantic-settings>=2.15,<3",
  "sqlalchemy>=2.0.52,<3",
  "stripe>=15.6,<16",
  "anthropic>=1.3,<2",
  "openai>=3.6,<4",
  "python-telegram-bot>=22.8,<23",
  "faker>=40,<41",
]

[dependency-groups]
dev = ["pytest>=9.1,<10", "httpx>=0.28,<1", "ruff>=0.12"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["app", "seed"]

[tool.pytest.ini_options]
testpaths = ["tests"]
markers = ["live_llm: calls a real LLM; deselected by default, needs a key"]
addopts = "-m 'not live_llm'"

[tool.ruff]
line-length = 100
target-version = "py312"
extend-exclude = ["web"]

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "D"]
ignore = ["D203", "D213"]

[tool.ruff.lint.pydocstyle]
convention = "google"
```

`.python-version`: `3.12`

`.env.example`:

```bash
# Stripe — test mode only. Dashboard → Developers → API keys.
STRIPE_SECRET_KEY=sk_test_replace_me

# LLM — set one provider and its key. https://console.anthropic.com / https://platform.openai.com
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
# Optional model override (defaults: claude-opus-5 / gpt-5.4-mini)
LLM_MODEL=

# Telegram — create a bot with @BotFather and paste the token.
TELEGRAM_BOT_TOKEN=

# Owner web app auth. The SPA reads this same variable through Vite.
OWNER_API_TOKEN=dev-owner-token

# SQLite file for conversations, confirmations, bindings, escalations, audit.
DATABASE_URL=sqlite:///./data/assistant.db
```

Append to `.gitignore`:

```gitignore

# Application
.venv/
__pycache__/
*.pyc
.pytest_cache/
.ruff_cache/
data/
web/node_modules/
web/dist/
```

- [ ] **Step 2: Write the failing settings tests**

`tests/__init__.py`: a one-line module docstring: `"""Test suite for the AI payments assistant."""`.

`tests/test_settings.py`:

```python
"""Settings must fail loudly, naming the missing variable and where to get it."""

import pytest

from app.settings import ConfigError, Settings


def _settings(**overrides: str) -> Settings:
    """Build Settings from explicit values, ignoring any .env on disk."""
    return Settings(_env_file=None, **overrides)


def test_missing_stripe_key_names_the_variable() -> None:
    """A blank Stripe key must produce an error that says which variable to set."""
    with pytest.raises(ConfigError) as excinfo:
        _settings(stripe_secret_key="").require_stripe()
    assert "STRIPE_SECRET_KEY" in str(excinfo.value)
    assert ".env" in str(excinfo.value)


def test_live_stripe_key_is_refused() -> None:
    """A live key must never be accepted: this project only runs against a sandbox."""
    with pytest.raises(ConfigError) as excinfo:
        _settings(stripe_secret_key="sk_live_abc").require_stripe()
    assert "test mode" in str(excinfo.value)


def test_llm_key_required_for_selected_provider_only() -> None:
    """Only the chosen provider's key is required, so a reviewer needs one key, not two."""
    _settings(llm_provider="openai", openai_api_key="sk-x").require_llm()
    with pytest.raises(ConfigError) as excinfo:
        _settings(llm_provider="anthropic", openai_api_key="sk-x").require_llm()
    assert "ANTHROPIC_API_KEY" in str(excinfo.value)


def test_default_model_follows_provider() -> None:
    """With no LLM_MODEL override, each provider gets its documented default."""
    assert _settings(llm_provider="anthropic").resolved_model == "claude-opus-5"
    assert _settings(llm_provider="openai").resolved_model == "gpt-5.4-mini"
    assert _settings(llm_model="custom").resolved_model == "custom"
```

- [ ] **Step 3: Run the tests to verify they fail**

Run: `uv sync && uv run pytest tests/test_settings.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app'` (or import error on `app.settings`).

- [ ] **Step 4: Implement `app/settings.py`**

`app/__init__.py`: `"""AI payments assistant: FastAPI backend, agent loop, Telegram bot."""`

```python
"""Process configuration loaded from the environment.

Every entrypoint (API, bot, seed) validates only the settings it needs, so a
reviewer running the seed script is never asked for a Telegram token. Errors
name the variable and where to obtain it.
"""

from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_MODELS: dict[str, str] = {"anthropic": "claude-opus-5", "openai": "gpt-5.4-mini"}


class ConfigError(RuntimeError):
    """A required setting is missing or invalid; the message says how to fix it."""


class Settings(BaseSettings):
    """All configuration, read from the environment and a repo-root .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    stripe_secret_key: str = ""
    llm_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    llm_model: str = ""
    telegram_bot_token: str = ""
    owner_api_token: str = ""
    database_url: str = "sqlite:///./data/assistant.db"

    @property
    def resolved_model(self) -> str:
        """The model to call: the override if set, else the provider's default."""
        return self.llm_model or DEFAULT_MODELS[self.llm_provider]

    def require_stripe(self) -> None:
        """Fail unless a Stripe *test* key is configured.

        Raises:
            ConfigError: Missing key, or a live key. A live key is refused
                outright because the seed script creates charges.
        """
        if not self.stripe_secret_key or self.stripe_secret_key == "sk_test_replace_me":
            raise ConfigError(
                "Set STRIPE_SECRET_KEY in .env — Stripe Dashboard → Developers → API keys "
                "(test mode)."
            )
        if not self.stripe_secret_key.startswith("sk_test_"):
            raise ConfigError(
                "STRIPE_SECRET_KEY must be a test mode key (sk_test_...). "
                "This project never runs against live data."
            )

    def require_llm(self) -> None:
        """Fail unless the selected provider has a key.

        Raises:
            ConfigError: Names the key for the configured LLM_PROVIDER only.
        """
        key = self.anthropic_api_key if self.llm_provider == "anthropic" else self.openai_api_key
        if not key:
            variable = "ANTHROPIC_API_KEY" if self.llm_provider == "anthropic" else "OPENAI_API_KEY"
            url = (
                "https://console.anthropic.com"
                if self.llm_provider == "anthropic"
                else "https://platform.openai.com"
            )
            raise ConfigError(f"Set {variable} in .env (LLM_PROVIDER={self.llm_provider}) — {url}")

    def require_telegram(self) -> None:
        """Fail unless a bot token is configured.

        Raises:
            ConfigError: With the BotFather pointer.
        """
        if not self.telegram_bot_token:
            raise ConfigError("Set TELEGRAM_BOT_TOKEN in .env — create a bot with @BotFather.")

    def require_owner_token(self) -> None:
        """Fail unless the owner API token is configured.

        Raises:
            ConfigError: The .env.example default is fine for local use.
        """
        if not self.owner_api_token:
            raise ConfigError("Set OWNER_API_TOKEN in .env (copy .env.example for a default).")


def load_settings() -> Settings:
    """Read settings from the environment and .env."""
    return Settings()
```

- [ ] **Step 5: Run tests and lint to verify they pass**

Run: `uv run pytest tests/test_settings.py -v && uv run ruff check .`
Expected: 4 passed; ruff reports no violations.

- [ ] **Step 6: Create the Makefile with the targets that work today**

```make
.PHONY: install test lint

install:
	uv sync
	cd web && npm install

test:
	uv run pytest

lint:
	uv run ruff check .
```

(`seed` and `dev` targets are added by the tasks that make them work; `cd web && npm install` becomes valid in Task 15 — leave it in now so the file is written once.)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock .python-version .env.example .gitignore Makefile app/__init__.py app/settings.py tests/__init__.py tests/test_settings.py
git commit -m "chore: scaffold Python project with validated settings and lint/test gates"
```

### Task 2: Domain — policy, money, models, Stripe→domain mapping, periods

**Files:**
- Create: `app/domain/__init__.py`, `app/domain/policy.py`, `app/domain/money.py`, `app/domain/models.py`, `app/domain/mapping.py`, `app/domain/periods.py`
- Test: `tests/test_money.py`, `tests/test_mapping.py`, `tests/test_periods.py`

**Interfaces:**
- Produces: `TELEGRAM_PAYMENT_CEILING_CENTS`, `BINDING_INACTIVITY`, `MAX_AGENT_ITERATIONS`; `format_usd(cents: int) -> str`; frozen dataclasses `Customer(id, name, email)`, `Payment(id, charge_id, customer_id, customer_name, amount_cents, amount_refunded_cents, status, failure_reason, description, occurred_at)`, `Invoice(id, number, customer_id, customer_name, total_cents, amount_remaining_cents, status, due_at, hosted_url, description, occurred_at)`, `Refund(id, payment_id, amount_cents, status)`; `to_payment(obj) -> Payment | None`, `to_invoice(obj) -> Invoice`, `to_customer(obj) -> Customer`, `to_refund(obj) -> Refund`; `Window(start, end, label).contains(moment)`, `local_timezone()`, `day_window(day, tz)`, `today_window(now)`, `yesterday_window(now)`, `date_range_window(start, end_inclusive, tz)`.
- Mapping functions accept any `Mapping[str, Any]` — Stripe SDK objects are `dict` subclasses, so production passes SDK objects and tests pass plain dicts.

- [ ] **Step 1: Write the failing tests**

`tests/test_money.py`:

```python
"""Dollar formatting is the only place cents become a string."""

from app.domain.money import format_usd


def test_format_usd_groups_thousands_and_keeps_cents() -> None:
    """Amounts read like an invoice: thousands separators, two decimals, sign first."""
    assert format_usd(120000) == "$1,200.00"
    assert format_usd(4500) == "$45.00"
    assert format_usd(-4500) == "-$45.00"
    assert format_usd(0) == "$0.00"
```

`tests/test_mapping.py`:

```python
"""The one concession to a fresh sandbox: occurred_at may come from seed metadata."""

from datetime import UTC, datetime

import pytest

from app.domain.mapping import to_invoice, to_payment

CREATED = 1756728000  # 2025-09-01T12:00:00Z


def _pi(**overrides: object) -> dict[str, object]:
    """A succeeded PaymentIntent as Stripe returns it with latest_charge and customer expanded."""
    base: dict[str, object] = {
        "id": "pi_1",
        "amount": 4500,
        "status": "succeeded",
        "created": CREATED,
        "description": "Consulting",
        "metadata": {},
        "customer": {"id": "cus_1", "name": "Maya Chen", "email": "maya@example.com"},
        "latest_charge": {"id": "ch_1", "refunded": False, "amount_refunded": 0, "outcome": None},
        "last_payment_error": None,
    }
    base.update(overrides)
    return base


def test_occurred_at_prefers_demo_created_at() -> None:
    """Seeded history carries its intended timestamp in metadata."""
    payment = to_payment(_pi(metadata={"demo_created_at": "2025-08-20T14:30:00+00:00"}))
    assert payment is not None
    assert payment.occurred_at == datetime(2025, 8, 20, 14, 30, tzinfo=UTC)


def test_occurred_at_falls_back_to_created() -> None:
    """Objects created live carry no metadata and use Stripe's own timestamp."""
    payment = to_payment(_pi())
    assert payment is not None
    assert payment.occurred_at == datetime.fromtimestamp(CREATED, tz=UTC)
    assert payment.customer_name == "Maya Chen"
    assert payment.charge_id == "ch_1"
    assert payment.status == "succeeded"


def test_declined_intent_maps_to_failed_with_reason() -> None:
    """A decline is a failed payment whose reason comes from the charge outcome."""
    declined = _pi(
        status="requires_payment_method",
        latest_charge={
            "id": "ch_2",
            "refunded": False,
            "amount_refunded": 0,
            "outcome": {"reason": "insufficient_funds"},
        },
    )
    payment = to_payment(declined)
    assert payment is not None
    assert payment.status == "failed"
    assert payment.failure_reason == "insufficient_funds"


def test_unattempted_intent_is_not_a_payment() -> None:
    """An open invoice's PaymentIntent has no charge yet and must not count as a decline."""
    assert to_payment(_pi(status="requires_payment_method", latest_charge=None)) is None


def test_unexpanded_charge_is_a_programming_error() -> None:
    """A string latest_charge means the caller forgot expand; fail fast rather than mis-map."""
    with pytest.raises(ValueError, match="expand"):
        to_payment(_pi(latest_charge="ch_1"))


def test_refund_states() -> None:
    """Partial and full refunds are distinct statuses so summaries can net them."""
    full = _pi(latest_charge={"id": "ch", "refunded": True, "amount_refunded": 4500, "outcome": None})
    part = _pi(latest_charge={"id": "ch", "refunded": False, "amount_refunded": 1000, "outcome": None})
    assert to_payment(full).status == "refunded"  # type: ignore[union-attr]
    assert to_payment(part).status == "partially_refunded"  # type: ignore[union-attr]
    assert to_payment(part).amount_refunded_cents == 1000  # type: ignore[union-attr]


def test_invoice_mapping() -> None:
    """Invoices expose what the bot and owner need: remaining balance, due date, hosted URL."""
    invoice = to_invoice(
        {
            "id": "in_1",
            "number": "F-0001",
            "customer": "cus_1",
            "total": 120000,
            "amount_remaining": 120000,
            "status": "open",
            "due_date": CREATED,
            "hosted_invoice_url": "https://invoice.stripe.com/i/x",
            "description": "Q3 retainer",
            "created": CREATED,
            "metadata": {},
        }
    )
    assert invoice.customer_id == "cus_1"
    assert invoice.customer_name is None
    assert invoice.amount_remaining_cents == 120000
    assert invoice.due_at == datetime.fromtimestamp(CREATED, tz=UTC)
```

`tests/test_periods.py`:

```python
"""Day boundaries are computed in one place and in the local timezone."""

from datetime import date, datetime, timedelta, timezone

from app.domain.periods import date_range_window, day_window, today_window, yesterday_window

TZ = timezone(timedelta(hours=-4))


def test_day_window_spans_local_midnight_to_midnight() -> None:
    """A day runs from local 00:00 inclusive to the next local 00:00 exclusive."""
    window = day_window(date(2026, 9, 1), TZ)
    assert window.start == datetime(2026, 9, 1, 0, 0, tzinfo=TZ)
    assert window.end == datetime(2026, 9, 2, 0, 0, tzinfo=TZ)
    assert window.contains(datetime(2026, 9, 1, 23, 59, tzinfo=TZ))
    assert not window.contains(datetime(2026, 9, 2, 0, 0, tzinfo=TZ))


def test_today_and_yesterday_follow_now() -> None:
    """Today and yesterday are derived from the supplied clock, not the wall clock."""
    now = datetime(2026, 9, 1, 10, 0, tzinfo=TZ)
    assert today_window(now).start.date() == date(2026, 9, 1)
    assert yesterday_window(now).start.date() == date(2026, 8, 31)
    assert yesterday_window(now).end == today_window(now).start


def test_date_range_is_end_inclusive() -> None:
    """Natural-language ranges ("Aug 24 to Aug 30") include the last day."""
    window = date_range_window(date(2026, 8, 24), date(2026, 8, 30), TZ)
    assert window.end == datetime(2026, 8, 31, 0, 0, tzinfo=TZ)
    assert window.label == "2026-08-24 to 2026-08-30"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_money.py tests/test_mapping.py tests/test_periods.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain'`.

- [ ] **Step 3: Implement the domain modules**

`app/domain/__init__.py`: `"""Domain models and the Stripe-to-domain boundary. Nothing here imports Stripe."""`

`app/domain/policy.py`:

```python
"""The business rules a reviewer will look for, each defined exactly once.

Nothing else in the codebase may restate these numbers; import them.
"""

from datetime import timedelta

TELEGRAM_PAYMENT_CEILING_CENTS = 200_000
"""Payments at or above this amount are never completed by the bot; they escalate."""

BINDING_INACTIVITY = timedelta(days=14)
"""A Telegram binding unused for this long is revoked on next contact."""

MAX_AGENT_ITERATIONS = 5
"""Planner steps per turn before the loop gives up, so a confused model cannot spin."""
```

`app/domain/money.py`:

```python
"""Cents-to-dollars formatting. The only place an amount becomes a string in Python."""


def format_usd(cents: int) -> str:
    """Render integer cents as a US dollar string with grouping.

    Negative amounts put the sign before the dollar sign so refunds read the
    way a bank statement prints them.
    """
    sign = "-" if cents < 0 else ""
    dollars, remainder = divmod(abs(cents), 100)
    return f"{sign}${dollars:,}.{remainder:02d}"
```

`app/domain/models.py`:

```python
"""Immutable domain records. Amounts are integer cents; times are tz-aware UTC."""

from dataclasses import dataclass
from datetime import datetime
from typing import Literal

PaymentStatus = Literal["succeeded", "failed", "refunded", "partially_refunded"]


@dataclass(frozen=True)
class Customer:
    """A Stripe customer as the assistant refers to it."""

    id: str
    name: str
    email: str | None


@dataclass(frozen=True)
class Payment:
    """One payment attempt, successful or declined.

    `occurred_at` is the business time of the payment. For seeded history it
    is the intended historical moment rather than Stripe's creation time; see
    `app.domain.mapping`.
    """

    id: str
    charge_id: str
    customer_id: str | None
    customer_name: str | None
    amount_cents: int
    amount_refunded_cents: int
    status: PaymentStatus
    failure_reason: str | None
    description: str | None
    occurred_at: datetime

    @property
    def refundable_cents(self) -> int:
        """How much can still be refunded on this payment."""
        return max(self.amount_cents - self.amount_refunded_cents, 0)


@dataclass(frozen=True)
class Invoice:
    """An invoice with the fields both the owner and the customer bot need."""

    id: str
    number: str | None
    customer_id: str
    customer_name: str | None
    total_cents: int
    amount_remaining_cents: int
    status: str
    due_at: datetime | None
    hosted_url: str | None
    description: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class Refund:
    """The receipt returned after a refund executes."""

    id: str
    payment_id: str
    amount_cents: int
    status: str
```

`app/domain/mapping.py`:

```python
"""Map Stripe API objects to domain records.

This module is the single place that knows Stripe's field names, and the
single reader of `metadata.demo_created_at`. Stripe SDK objects are dict
subclasses, so every function takes a Mapping and tests pass plain dicts.
"""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from app.domain.models import Customer, Invoice, Payment, PaymentStatus, Refund


def _occurred_at(obj: Mapping[str, Any]) -> datetime:
    """Business timestamp of an object.

    Seeded history cannot carry a past `created` (Stripe assigns it), so the
    seed script records the intended moment in metadata. Deleting the first
    branch makes this production behaviour; nothing else reads the field.
    """
    demo = (obj.get("metadata") or {}).get("demo_created_at")
    if demo:
        parsed = datetime.fromisoformat(demo)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.fromtimestamp(obj["created"], tz=UTC)


def _customer_ref(value: Any) -> tuple[str | None, str | None]:
    """Split a `customer` field into (id, name) whether or not it was expanded."""
    if value is None:
        return None, None
    if isinstance(value, str):
        return value, None
    if value.get("deleted"):
        return value.get("id"), None
    return value.get("id"), value.get("name")


def to_payment(obj: Mapping[str, Any]) -> Payment | None:
    """Map a PaymentIntent (with `latest_charge` and `customer` expanded).

    Returns None for an intent that was never attempted — an open invoice's
    intent, for instance — because it is neither a payment nor a decline.

    Raises:
        ValueError: `latest_charge` is an id string, meaning the caller forgot
            `expand=["data.latest_charge"]`; mapping blind would hide declines.
    """
    charge = obj.get("latest_charge")
    if charge is None:
        return None
    if isinstance(charge, str):
        raise ValueError("PaymentIntent.latest_charge must be expanded before mapping")
    customer_id, customer_name = _customer_ref(obj.get("customer"))
    status: PaymentStatus
    failure_reason: str | None = None
    if obj["status"] == "succeeded":
        if charge.get("refunded"):
            status = "refunded"
        elif charge.get("amount_refunded"):
            status = "partially_refunded"
        else:
            status = "succeeded"
    else:
        status = "failed"
        outcome = charge.get("outcome") or {}
        error = obj.get("last_payment_error") or {}
        failure_reason = outcome.get("reason") or error.get("decline_code") or charge.get("failure_code")
    return Payment(
        id=obj["id"],
        charge_id=charge["id"],
        customer_id=customer_id,
        customer_name=customer_name,
        amount_cents=obj["amount"],
        amount_refunded_cents=charge.get("amount_refunded") or 0,
        status=status,
        failure_reason=failure_reason,
        description=obj.get("description"),
        occurred_at=_occurred_at(obj),
    )


def to_invoice(obj: Mapping[str, Any]) -> Invoice:
    """Map an Invoice; `customer` may be an id or an expanded object."""
    customer_id, customer_name = _customer_ref(obj.get("customer"))
    due = obj.get("due_date")
    return Invoice(
        id=obj["id"],
        number=obj.get("number"),
        customer_id=customer_id or "",
        customer_name=customer_name,
        total_cents=obj.get("total") or 0,
        amount_remaining_cents=obj.get("amount_remaining") or 0,
        status=obj.get("status") or "draft",
        due_at=datetime.fromtimestamp(due, tz=UTC) if due else None,
        hosted_url=obj.get("hosted_invoice_url"),
        description=obj.get("description"),
        occurred_at=_occurred_at(obj),
    )


def to_customer(obj: Mapping[str, Any]) -> Customer:
    """Map a Customer. Deleted customers keep their id and lose their name."""
    return Customer(id=obj["id"], name=obj.get("name") or "(unnamed)", email=obj.get("email"))


def to_refund(obj: Mapping[str, Any]) -> Refund:
    """Map a Refund created against a PaymentIntent."""
    return Refund(
        id=obj["id"],
        payment_id=obj.get("payment_intent") or "",
        amount_cents=obj["amount"],
        status=obj.get("status") or "pending",
    )
```

`app/domain/periods.py`:

```python
"""Time windows for "today", "yesterday", and explicit date ranges.

All boundaries are local-midnight in the given timezone (default: the
machine's), so the reviewer's day is the reviewer's day.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo


@dataclass(frozen=True)
class Window:
    """A half-open interval [start, end) with a human label."""

    start: datetime
    end: datetime
    label: str

    def contains(self, moment: datetime) -> bool:
        """Whether a tz-aware moment falls inside the window."""
        return self.start <= moment < self.end


def local_timezone() -> tzinfo:
    """The process's local timezone, resolved once per call from the system clock."""
    tz = datetime.now().astimezone().tzinfo
    assert tz is not None  # astimezone() always attaches one
    return tz


def day_window(day: date, tz: tzinfo | None = None) -> Window:
    """The local calendar day containing `day`."""
    zone = tz or local_timezone()
    start = datetime(day.year, day.month, day.day, tzinfo=zone)
    return Window(start=start, end=start + timedelta(days=1), label=day.isoformat())


def today_window(now: datetime | None = None) -> Window:
    """Today according to `now` (tz-aware) or the local clock."""
    current = now or datetime.now(local_timezone())
    return day_window(current.date(), current.tzinfo)


def yesterday_window(now: datetime | None = None) -> Window:
    """The day before today, sharing today's timezone."""
    current = now or datetime.now(local_timezone())
    return day_window(current.date() - timedelta(days=1), current.tzinfo)


def date_range_window(start: date, end_inclusive: date, tz: tzinfo | None = None) -> Window:
    """A range of whole days, end inclusive, as people phrase ranges."""
    zone = tz or local_timezone()
    first = datetime(start.year, start.month, start.day, tzinfo=zone)
    last = datetime(end_inclusive.year, end_inclusive.month, end_inclusive.day, tzinfo=zone)
    return Window(
        start=first,
        end=last + timedelta(days=1),
        label=f"{start.isoformat()} to {end_inclusive.isoformat()}",
    )
```

- [ ] **Step 4: Run tests and lint**

Run: `uv run pytest tests/test_money.py tests/test_mapping.py tests/test_periods.py -q && uv run ruff check .`
Expected: 11 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/domain tests/test_money.py tests/test_mapping.py tests/test_periods.py
git commit -m "feat(domain): models, policy constants, Stripe mapping with the demo_created_at concession"
```

### Task 3: Domain — daily summary facts

**Files:**
- Create: `app/domain/summary.py`
- Test: `tests/test_summary.py`

**Interfaces:**
- Consumes: `Payment`, `Invoice`, `Window`, `today_window`, `yesterday_window` (Task 2).
- Produces: `PeriodTotals(label, succeeded_count, succeeded_total_cents, refunded_total_cents, declined_count, declined_reasons)`, `OpenInvoiceFact(customer_name, number, amount_remaining_cents, due_date, overdue)`, `PaymentFact(customer_name, amount_cents, description)`, `DailyFacts(today, yesterday, open_invoices, open_invoice_total_cents, largest_payment)`, `period_totals(payments, window) -> PeriodTotals`, `build_daily_facts(payments, invoices, now) -> DailyFacts`. All are frozen dataclasses so `dataclasses.asdict` serialises them for the narrator.

- [ ] **Step 1: Write the failing tests**

`tests/test_summary.py`:

```python
"""The numbers in the daily summary are computed in Python, never by the model."""

from datetime import datetime, timedelta, timezone

from app.domain.models import Invoice, Payment
from app.domain.summary import build_daily_facts, period_totals
from app.domain.periods import today_window

TZ = timezone(timedelta(hours=-4))
NOW = datetime(2026, 9, 1, 15, 0, tzinfo=TZ)


def _payment(
    amount: int, when: datetime, status: str = "succeeded", reason: str | None = None,
    refunded: int = 0, name: str = "Acme Corp",
) -> Payment:
    """A payment with only the fields the summary reads varied."""
    return Payment(
        id=f"pi_{amount}_{when.timestamp()}", charge_id="ch", customer_id="cus", customer_name=name,
        amount_cents=amount, amount_refunded_cents=refunded, status=status,  # type: ignore[arg-type]
        failure_reason=reason, description=None, occurred_at=when,
    )


def _invoice(remaining: int, due: datetime | None, status: str = "open") -> Invoice:
    """An invoice for Acme with a given remaining balance and due date."""
    return Invoice(
        id="in", number="F-1", customer_id="cus", customer_name="Acme Corp", total_cents=remaining,
        amount_remaining_cents=remaining, status=status, due_at=due, hosted_url=None,
        description=None, occurred_at=NOW,
    )


def test_period_totals_counts_only_successes_and_separates_declines() -> None:
    """Declines never inflate revenue; refunds are netted separately."""
    payments = [
        _payment(10000, NOW), _payment(5000, NOW, refunded=5000, status="refunded"),
        _payment(7000, NOW, status="failed", reason="insufficient_funds"),
        _payment(9999, NOW - timedelta(days=1)),
    ]
    totals = period_totals(payments, today_window(NOW))
    assert totals.succeeded_count == 2
    assert totals.succeeded_total_cents == 15000
    assert totals.refunded_total_cents == 5000
    assert totals.declined_count == 1
    assert totals.declined_reasons == {"insufficient_funds": 1}


def test_daily_facts_compare_with_yesterday_and_list_open_invoices() -> None:
    """The example summary needs today, yesterday, declines, and the unpaid Acme invoice."""
    yesterday = NOW - timedelta(days=1)
    payments = [_payment(4280, NOW, name="Maya Chen"), _payment(1000, yesterday)]
    invoices = [
        _invoice(120000, NOW + timedelta(days=10)),
        _invoice(5000, NOW - timedelta(days=2)),
        _invoice(0, None, status="paid"),
    ]
    facts = build_daily_facts(payments, invoices, NOW)
    assert facts.today.succeeded_total_cents == 4280
    assert facts.yesterday.succeeded_total_cents == 1000
    assert [i.amount_remaining_cents for i in facts.open_invoices] == [120000, 5000]
    assert facts.open_invoices[1].overdue is True
    assert facts.open_invoice_total_cents == 125000
    assert facts.largest_payment is not None
    assert facts.largest_payment.customer_name == "Maya Chen"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_summary.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.domain.summary'`.

- [ ] **Step 3: Implement `app/domain/summary.py`**

```python
"""Deterministic facts behind the daily summary.

The LLM narrates these numbers; it never computes them. Everything here is
plain dataclasses so the result can be serialised with `dataclasses.asdict`.
"""

from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from app.domain.models import Invoice, Payment
from app.domain.periods import Window, today_window, yesterday_window


@dataclass(frozen=True)
class PeriodTotals:
    """Revenue figures for one window."""

    label: str
    succeeded_count: int
    succeeded_total_cents: int
    refunded_total_cents: int
    declined_count: int
    declined_reasons: dict[str, int]


@dataclass(frozen=True)
class OpenInvoiceFact:
    """An unpaid invoice as the summary mentions it."""

    customer_name: str | None
    number: str | None
    amount_remaining_cents: int
    due_date: str | None
    overdue: bool


@dataclass(frozen=True)
class PaymentFact:
    """A single notable payment."""

    customer_name: str | None
    amount_cents: int
    description: str | None


@dataclass(frozen=True)
class DailyFacts:
    """Everything the narrator may mention about today."""

    today: PeriodTotals
    yesterday: PeriodTotals
    open_invoices: list[OpenInvoiceFact]
    open_invoice_total_cents: int
    largest_payment: PaymentFact | None


def period_totals(payments: Sequence[Payment], window: Window) -> PeriodTotals:
    """Sum a window's payments.

    Refunds are attributed to the day of the original payment, which is the
    simplest rule that keeps "you took $X" and "you refunded $Y" consistent.
    """
    inside = [p for p in payments if window.contains(p.occurred_at)]
    succeeded = [p for p in inside if p.status != "failed"]
    declined = [p for p in inside if p.status == "failed"]
    reasons = Counter(p.failure_reason or "unknown" for p in declined)
    return PeriodTotals(
        label=window.label,
        succeeded_count=len(succeeded),
        succeeded_total_cents=sum(p.amount_cents for p in succeeded),
        refunded_total_cents=sum(p.amount_refunded_cents for p in succeeded),
        declined_count=len(declined),
        declined_reasons=dict(reasons),
    )


def build_daily_facts(
    payments: Sequence[Payment], invoices: Sequence[Invoice], now: datetime
) -> DailyFacts:
    """Assemble today's facts, the comparison with yesterday, and what is still unpaid."""
    today = today_window(now)
    open_invoices = sorted(
        (i for i in invoices if i.status == "open" and i.amount_remaining_cents > 0),
        key=lambda i: i.amount_remaining_cents,
        reverse=True,
    )
    todays_successes = [
        p for p in payments if today.contains(p.occurred_at) and p.status != "failed"
    ]
    largest = max(todays_successes, key=lambda p: p.amount_cents, default=None)
    return DailyFacts(
        today=period_totals(payments, today),
        yesterday=period_totals(payments, yesterday_window(now)),
        open_invoices=[
            OpenInvoiceFact(
                customer_name=i.customer_name,
                number=i.number,
                amount_remaining_cents=i.amount_remaining_cents,
                due_date=i.due_at.date().isoformat() if i.due_at else None,
                overdue=bool(i.due_at and i.due_at < now),
            )
            for i in open_invoices
        ],
        open_invoice_total_cents=sum(i.amount_remaining_cents for i in open_invoices),
        largest_payment=(
            PaymentFact(largest.customer_name, largest.amount_cents, largest.description)
            if largest
            else None
        ),
    )
```

- [ ] **Step 4: Run tests and lint**

Run: `uv run pytest tests/test_summary.py -q && uv run ruff check .`
Expected: 2 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/domain/summary.py tests/test_summary.py
git commit -m "feat(domain): deterministic daily summary facts"
```

### Task 4: Stripe gateway protocol, in-memory fake, and the customer-scoped client

**Files:**
- Create: `app/stripe_/__init__.py`, `app/stripe_/gateway.py`, `app/stripe_/customer_client.py`, `tests/fakes/__init__.py`, `tests/fakes/stripe_fake.py`
- Test: `tests/test_scoped_gateway.py`

**Interfaces:**
- Produces: `StripeGatewayError(message, hint)`, `NotFound`, `CardDeclined`, `NotYourInvoice`; `StripeGateway` Protocol with `list_payments()`, `get_payment(payment_id)`, `list_invoices(*, customer_id=None, status=None)`, `get_invoice(invoice_id)`, `list_customers()`, `get_customer(customer_id)`, `find_customer_by_bind_token(token)`, `refund(payment_id, amount_cents, *, idempotency_key) -> Refund`, `create_invoice(*, customer_id, amount_cents, description, due_date, idempotency_key) -> Invoice`, `create_payment_link(*, amount_cents, description, idempotency_key) -> str`, `pay_invoice(invoice_id, *, idempotency_key) -> Invoice`; `CustomerScopedGateway(owner, customer_id)` with `customer_id`, `my_customer()`, `my_invoices(*, status=None)`, `my_invoice(invoice_id)`, `pay_my_invoice(invoice_id, *, idempotency_key)`; `FakeStripeGateway` with `add_customer`, `add_payment`, `add_invoice`, `calls`.

- [ ] **Step 1: Write the failing tests**

`tests/fakes/__init__.py`: `"""In-memory stand-ins for Stripe and the LLM so tests need no network."""`

`tests/test_scoped_gateway.py`:

```python
"""Part 2's whole point: a bound customer cannot reach anyone else's data."""

import inspect

import pytest

from app.stripe_.customer_client import CustomerScopedGateway, NotYourInvoice
from tests.fakes.stripe_fake import FakeStripeGateway


def _two_customers() -> FakeStripeGateway:
    """Acme and Maya, each with one open invoice."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_invoice("in_acme", "cus_acme", 120000)
    fake.add_invoice("in_maya", "cus_maya", 18000)
    return fake


def test_scoped_gateway_lists_only_the_bound_customers_invoices() -> None:
    """Every list call carries the bound id; the other customer's invoice never appears."""
    scoped = CustomerScopedGateway(_two_customers(), "cus_acme")
    assert [i.id for i in scoped.my_invoices()] == ["in_acme"]
    assert scoped.my_customer().name == "Acme Corp"


def test_scoped_gateway_refuses_another_customers_invoice_before_any_payment_call() -> None:
    """Ownership is checked first, so a guessed invoice id cannot be paid or even read."""
    fake = _two_customers()
    scoped = CustomerScopedGateway(fake, "cus_acme")
    with pytest.raises(NotYourInvoice):
        scoped.my_invoice("in_maya")
    with pytest.raises(NotYourInvoice):
        scoped.pay_my_invoice("in_maya", idempotency_key="k")
    assert not [c for c in fake.calls if c[0] == "pay_invoice"]


def test_scoped_gateway_exposes_no_customer_id_parameter() -> None:
    """Structural check: no public method can be steered towards another customer."""
    for name, member in inspect.getmembers(CustomerScopedGateway, inspect.isfunction):
        if name.startswith("_"):
            continue
        assert "customer_id" not in inspect.signature(member).parameters, name
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_scoped_gateway.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.stripe_'`.

- [ ] **Step 3: Implement the protocol and errors**

`app/stripe_/__init__.py`: `"""Stripe access: a narrow gateway protocol, the real client, and the scoped client."""`

`app/stripe_/gateway.py`:

```python
"""The narrow Stripe surface the rest of the application depends on.

Actions and the agent loop are written against this Protocol; tests supply
`tests.fakes.stripe_fake.FakeStripeGateway`, production supplies
`app.stripe_.owner_client.StripeOwnerGateway`.
"""

from datetime import date
from typing import Protocol

from app.domain.models import Customer, Invoice, Payment, Refund


class StripeGatewayError(RuntimeError):
    """A Stripe call failed in a way the user can act on.

    `hint` is surfaced in the API error envelope; keep it concrete.
    """

    def __init__(self, message: str, hint: str = "") -> None:
        """Store the message and an optional fix."""
        super().__init__(message)
        self.hint = hint


class NotFound(StripeGatewayError):
    """The referenced object does not exist in this account."""


class CardDeclined(StripeGatewayError):
    """The card on file was declined when paying an invoice."""


class StripeGateway(Protocol):
    """Everything the owner assistant may do to Stripe. Amounts are cents."""

    def list_payments(self) -> list[Payment]:
        """All payment attempts, newest first. Never filtered by `created`."""
        ...

    def get_payment(self, payment_id: str) -> Payment:
        """One payment by PaymentIntent id."""
        ...

    def list_invoices(
        self, *, customer_id: str | None = None, status: str | None = None
    ) -> list[Invoice]:
        """Invoices, optionally for one customer and/or one status."""
        ...

    def get_invoice(self, invoice_id: str) -> Invoice:
        """One invoice by id."""
        ...

    def list_customers(self) -> list[Customer]:
        """Every customer in the account."""
        ...

    def get_customer(self, customer_id: str) -> Customer:
        """One customer by id."""
        ...

    def find_customer_by_bind_token(self, token: str) -> Customer | None:
        """The customer whose `metadata.telegram_bind_token` equals `token`, if any."""
        ...

    def refund(self, payment_id: str, amount_cents: int | None, *, idempotency_key: str) -> Refund:
        """Refund a payment, fully when `amount_cents` is None."""
        ...

    def create_invoice(
        self,
        *,
        customer_id: str,
        amount_cents: int,
        description: str,
        due_date: date,
        idempotency_key: str,
    ) -> Invoice:
        """Create and finalise a send-by-email invoice with one line item."""
        ...

    def create_payment_link(self, *, amount_cents: int, description: str, idempotency_key: str) -> str:
        """Create a one-off payment link and return its URL."""
        ...

    def pay_invoice(self, invoice_id: str, *, idempotency_key: str) -> Invoice:
        """Pay an open invoice with the customer's default payment method."""
        ...
```

`app/stripe_/customer_client.py`:

```python
"""A Stripe view bound to one customer.

Constructed with the id from the Telegram binding row. Every method either
passes that id to Stripe or verifies ownership before acting. No public
method accepts a customer id — see `tests/test_scoped_gateway.py`.
"""

from app.domain.models import Customer, Invoice
from app.stripe_.gateway import StripeGateway, StripeGatewayError


class NotYourInvoice(StripeGatewayError):
    """The invoice exists but belongs to a different customer."""


class CustomerScopedGateway:
    """The only Stripe surface the customer bot's actions can reach."""

    def __init__(self, owner: StripeGateway, customer_id: str) -> None:
        """Bind an owner gateway to a single customer id."""
        self._owner = owner
        self._customer_id = customer_id

    @property
    def customer_id(self) -> str:
        """The bound customer id (read-only)."""
        return self._customer_id

    def my_customer(self) -> Customer:
        """The bound customer's record."""
        return self._owner.get_customer(self._customer_id)

    def my_invoices(self, *, status: str | None = None) -> list[Invoice]:
        """Invoices for the bound customer only; the id is supplied by us, never by input."""
        return self._owner.list_invoices(customer_id=self._customer_id, status=status)

    def my_invoice(self, invoice_id: str) -> Invoice:
        """One invoice, after proving it belongs to the bound customer.

        Raises:
            NotYourInvoice: The id resolves to another customer's invoice. Raised
                with the same message as a missing invoice so ids cannot be probed.
        """
        invoice = self._owner.get_invoice(invoice_id)
        if invoice.customer_id != self._customer_id:
            raise NotYourInvoice("No such invoice on your account.")
        return invoice

    def pay_my_invoice(self, invoice_id: str, *, idempotency_key: str) -> Invoice:
        """Pay one of the bound customer's invoices with their card on file.

        The ownership check runs before any payment call, so a guessed id
        fails without touching Stripe's payment endpoint.
        """
        self.my_invoice(invoice_id)
        return self._owner.pay_invoice(invoice_id, idempotency_key=idempotency_key)
```

- [ ] **Step 4: Implement the fake**

`tests/fakes/stripe_fake.py`:

```python
"""An in-memory StripeGateway that records every call.

Tests build a small account with `add_*`, exercise actions, and assert on
`calls` — a list of (method_name, kwargs) tuples in call order.
"""

from datetime import UTC, datetime, timedelta
from datetime import date as date_type
from typing import Any

from app.domain.models import Customer, Invoice, Payment, Refund
from app.stripe_.gateway import NotFound


class FakeStripeGateway:
    """Deterministic stand-in for Stripe; see module docstring."""

    def __init__(self) -> None:
        """Start with an empty account."""
        self.customers: dict[str, Customer] = {}
        self.payments: dict[str, Payment] = {}
        self.invoices: dict[str, Invoice] = {}
        self.bind_tokens: dict[str, str] = {}
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._counter = 0

    def _next(self, prefix: str) -> str:
        """Generate a predictable id like `re_1`."""
        self._counter += 1
        return f"{prefix}_{self._counter}"

    def add_customer(self, customer_id: str, name: str, bind_token: str | None = None) -> Customer:
        """Register a customer, optionally with a Telegram bind token."""
        customer = Customer(id=customer_id, name=name, email=f"{customer_id}@example.com")
        self.customers[customer_id] = customer
        if bind_token:
            self.bind_tokens[bind_token] = customer_id
        return customer

    def add_payment(
        self,
        payment_id: str,
        customer_id: str,
        amount_cents: int,
        *,
        occurred_at: datetime | None = None,
        status: str = "succeeded",
        failure_reason: str | None = None,
    ) -> Payment:
        """Register a payment attempt."""
        customer = self.customers.get(customer_id)
        payment = Payment(
            id=payment_id, charge_id=f"ch_{payment_id}", customer_id=customer_id,
            customer_name=customer.name if customer else None, amount_cents=amount_cents,
            amount_refunded_cents=0, status=status, failure_reason=failure_reason,  # type: ignore[arg-type]
            description=None, occurred_at=occurred_at or datetime.now(UTC),
        )
        self.payments[payment_id] = payment
        return payment

    def add_invoice(
        self, invoice_id: str, customer_id: str, amount_cents: int, *, status: str = "open"
    ) -> Invoice:
        """Register an invoice; open invoices have the full amount remaining."""
        customer = self.customers.get(customer_id)
        invoice = Invoice(
            id=invoice_id, number=invoice_id.upper(), customer_id=customer_id,
            customer_name=customer.name if customer else None, total_cents=amount_cents,
            amount_remaining_cents=amount_cents if status == "open" else 0, status=status,
            due_at=datetime.now(UTC) + timedelta(days=14),
            hosted_url=f"https://invoice.example/{invoice_id}", description="Services",
            occurred_at=datetime.now(UTC),
        )
        self.invoices[invoice_id] = invoice
        return invoice

    def _record(self, name: str, **kwargs: Any) -> None:
        """Append a call for later assertions."""
        self.calls.append((name, kwargs))

    def list_payments(self) -> list[Payment]:
        """Newest first, like Stripe."""
        self._record("list_payments")
        return sorted(self.payments.values(), key=lambda p: p.occurred_at, reverse=True)

    def get_payment(self, payment_id: str) -> Payment:
        """Lookup or NotFound."""
        self._record("get_payment", payment_id=payment_id)
        if payment_id not in self.payments:
            raise NotFound(f"No payment {payment_id}")
        return self.payments[payment_id]

    def list_invoices(
        self, *, customer_id: str | None = None, status: str | None = None
    ) -> list[Invoice]:
        """Filter by customer and/or status."""
        self._record("list_invoices", customer_id=customer_id, status=status)
        return [
            i for i in self.invoices.values()
            if (customer_id is None or i.customer_id == customer_id)
            and (status is None or i.status == status)
        ]

    def get_invoice(self, invoice_id: str) -> Invoice:
        """Lookup or NotFound."""
        self._record("get_invoice", invoice_id=invoice_id)
        if invoice_id not in self.invoices:
            raise NotFound(f"No invoice {invoice_id}")
        return self.invoices[invoice_id]

    def list_customers(self) -> list[Customer]:
        """Every registered customer."""
        self._record("list_customers")
        return list(self.customers.values())

    def get_customer(self, customer_id: str) -> Customer:
        """Lookup or NotFound."""
        self._record("get_customer", customer_id=customer_id)
        if customer_id not in self.customers:
            raise NotFound(f"No customer {customer_id}")
        return self.customers[customer_id]

    def find_customer_by_bind_token(self, token: str) -> Customer | None:
        """Resolve a seed-minted token."""
        self._record("find_customer_by_bind_token", token=token)
        customer_id = self.bind_tokens.get(token)
        return self.customers.get(customer_id) if customer_id else None

    def refund(self, payment_id: str, amount_cents: int | None, *, idempotency_key: str) -> Refund:
        """Mark the payment refunded and return a receipt."""
        self._record("refund", payment_id=payment_id, amount_cents=amount_cents, idempotency_key=idempotency_key)
        payment = self.get_payment(payment_id)
        amount = payment.refundable_cents if amount_cents is None else amount_cents
        refunded = payment.amount_refunded_cents + amount
        status = "refunded" if refunded >= payment.amount_cents else "partially_refunded"
        self.payments[payment_id] = Payment(
            **{**payment.__dict__, "amount_refunded_cents": refunded, "status": status}
        )
        return Refund(id=self._next("re"), payment_id=payment_id, amount_cents=amount, status="succeeded")

    def create_invoice(
        self, *, customer_id: str, amount_cents: int, description: str, due_date: date_type, idempotency_key: str
    ) -> Invoice:
        """Create an open invoice."""
        self._record("create_invoice", customer_id=customer_id, amount_cents=amount_cents, description=description, due_date=due_date, idempotency_key=idempotency_key)
        return self.add_invoice(self._next("in"), customer_id, amount_cents)

    def create_payment_link(self, *, amount_cents: int, description: str, idempotency_key: str) -> str:
        """Return a fake URL."""
        self._record("create_payment_link", amount_cents=amount_cents, description=description, idempotency_key=idempotency_key)
        return f"https://buy.example/{self._next('plink')}"

    def pay_invoice(self, invoice_id: str, *, idempotency_key: str) -> Invoice:
        """Mark paid and record a matching payment."""
        self._record("pay_invoice", invoice_id=invoice_id, idempotency_key=idempotency_key)
        invoice = self.get_invoice(invoice_id)
        paid = Invoice(**{**invoice.__dict__, "status": "paid", "amount_remaining_cents": 0})
        self.invoices[invoice_id] = paid
        self.add_payment(self._next("pi"), invoice.customer_id, invoice.total_cents)
        return paid
```

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/test_scoped_gateway.py -q && uv run ruff check .`
Expected: 3 passed; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add app/stripe_ tests/fakes tests/test_scoped_gateway.py
git commit -m "feat(stripe): gateway protocol, customer-scoped client, and in-memory fake"
```

### Task 5: The real Stripe owner client

**Files:**
- Create: `app/stripe_/owner_client.py`
- Test: `tests/test_owner_client_errors.py`

**Interfaces:**
- Consumes: `StripeGateway` protocol and error classes (Task 4), mapping functions (Task 2).
- Produces: `STRIPE_API_VERSION = "2026-08-26.dahlia"`, `StripeOwnerGateway(api_key)` implementing `StripeGateway`, `translate_stripe_errors()` context manager (also used by the seed script).
- SDK facts (verified against stripe 15.6): `stripe.StripeClient(api_key, stripe_version=...)`; resources under `client.v1.*`; params are the first positional dict; per-request `options={"idempotency_key": ...}`; `invoices.pay(id, params, options)`, `invoices.finalize_invoice(id, params, options)`; `refunds.create` accepts `payment_intent`; `invoice_items.create` accepts `amount`, `currency`, `customer`, `invoice`, `description`; `ListObject.auto_paging_iter()` reuses the original params (including `expand`) across pages; typed errors are `stripe.AuthenticationError`, `stripe.CardError`, `stripe.InvalidRequestError` (with `.code`), `stripe.StripeError`.

- [ ] **Step 1: Write the failing test**

`tests/test_owner_client_errors.py`:

```python
"""Stripe's exceptions become errors that carry a fix the reviewer can apply."""

import pytest
import stripe

from app.stripe_.gateway import CardDeclined, NotFound, StripeGatewayError
from app.stripe_.owner_client import STRIPE_API_VERSION, StripeOwnerGateway, translate_stripe_errors


def test_authentication_error_names_the_env_variable() -> None:
    """A bad key must tell the reviewer which variable to fix, not say 'unauthorized'."""
    with pytest.raises(StripeGatewayError) as excinfo:
        with translate_stripe_errors():
            raise stripe.AuthenticationError("Invalid API Key provided")
    assert "STRIPE_SECRET_KEY" in excinfo.value.hint


def test_missing_resource_becomes_not_found() -> None:
    """resource_missing is the one InvalidRequestError callers branch on."""
    with pytest.raises(NotFound):
        with translate_stripe_errors():
            raise stripe.InvalidRequestError("No such invoice: in_x", "id", code="resource_missing")


def test_card_error_becomes_card_declined() -> None:
    """A decline while paying an invoice is a user-facing outcome, not a crash."""
    with pytest.raises(CardDeclined):
        with translate_stripe_errors():
            raise stripe.CardError("Your card was declined.", "payment_method", "card_declined")


def test_client_pins_the_api_version() -> None:
    """The API version is pinned explicitly rather than drifting with the account default."""
    gateway = StripeOwnerGateway("sk_test_placeholder")
    assert gateway.api_version == STRIPE_API_VERSION == "2026-08-26.dahlia"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/test_owner_client_errors.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.stripe_.owner_client'`.

- [ ] **Step 3: Implement `app/stripe_/owner_client.py`**

```python
"""The production StripeGateway, and the only module that imports `stripe`.

Every public method maps SDK objects through `app.domain.mapping` and
translates SDK exceptions into `StripeGatewayError`s with a usable hint.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime, time

import stripe

from app.domain.mapping import to_customer, to_invoice, to_payment, to_refund
from app.domain.models import Customer, Invoice, Payment, Refund
from app.domain.periods import local_timezone
from app.stripe_.gateway import CardDeclined, NotFound, StripeGatewayError

STRIPE_API_VERSION = "2026-08-26.dahlia"
"""Pinned so behaviour does not change when the reviewer's account default moves."""

PAGE = 100


@contextmanager
def translate_stripe_errors() -> Iterator[None]:
    """Turn Stripe SDK exceptions into gateway errors that say what to do next.

    Raises:
        StripeGatewayError: Authentication and generic API failures, with a hint.
        NotFound: `resource_missing`, the one invalid-request code callers handle.
        CardDeclined: A card declined while paying an invoice.
    """
    try:
        yield
    except stripe.AuthenticationError as exc:
        raise StripeGatewayError(
            "Stripe rejected the API key.",
            hint="Set STRIPE_SECRET_KEY in .env to your test-mode secret key (sk_test_...).",
        ) from exc
    except stripe.CardError as exc:
        raise CardDeclined(exc.user_message or "The card was declined.") from exc
    except stripe.InvalidRequestError as exc:
        if exc.code == "resource_missing":
            raise NotFound(exc.user_message or str(exc)) from exc
        raise StripeGatewayError(exc.user_message or str(exc)) from exc
    except stripe.StripeError as exc:
        raise StripeGatewayError(str(exc), hint="Check the Stripe dashboard logs for the request.") from exc


class StripeOwnerGateway:
    """Full-account Stripe access for the owner assistant and the seed script."""

    def __init__(self, api_key: str) -> None:
        """Create a pinned-version client. Retries are left to the SDK (2 attempts)."""
        self._client = stripe.StripeClient(
            api_key, stripe_version=STRIPE_API_VERSION, max_network_retries=2
        )

    @property
    def api_version(self) -> str:
        """The pinned API version, exposed for tests and the seed report."""
        return STRIPE_API_VERSION

    @property
    def client(self) -> stripe.StripeClient:
        """The underlying SDK client; the seed script needs write calls this gateway does not."""
        return self._client

    def list_payments(self) -> list[Payment]:
        """Every attempted PaymentIntent, newest first.

        Not filtered by `created` on purpose: seeded history is dated by
        `occurred_at`, so period filtering happens in Python on the mapped result.
        """
        with translate_stripe_errors():
            page = self._client.v1.payment_intents.list(
                {"limit": PAGE, "expand": ["data.latest_charge", "data.customer"]}
            )
            mapped = [to_payment(intent) for intent in page.auto_paging_iter()]
        return [payment for payment in mapped if payment is not None]

    def get_payment(self, payment_id: str) -> Payment:
        """One PaymentIntent with its charge and customer expanded.

        Raises:
            NotFound: Unknown id, or an intent that was never attempted.
        """
        with translate_stripe_errors():
            intent = self._client.v1.payment_intents.retrieve(
                payment_id, {"expand": ["latest_charge", "customer"]}
            )
        payment = to_payment(intent)
        if payment is None:
            raise NotFound(f"{payment_id} has no payment attempt to act on.")
        return payment

    def list_invoices(
        self, *, customer_id: str | None = None, status: str | None = None
    ) -> list[Invoice]:
        """Invoices with customers expanded, optionally filtered."""
        params: dict[str, object] = {"limit": PAGE, "expand": ["data.customer"]}
        if customer_id:
            params["customer"] = customer_id
        if status:
            params["status"] = status
        with translate_stripe_errors():
            page = self._client.v1.invoices.list(params)  # type: ignore[arg-type]
            return [to_invoice(invoice) for invoice in page.auto_paging_iter()]

    def get_invoice(self, invoice_id: str) -> Invoice:
        """One invoice with its customer expanded."""
        with translate_stripe_errors():
            return to_invoice(self._client.v1.invoices.retrieve(invoice_id, {"expand": ["customer"]}))

    def list_customers(self) -> list[Customer]:
        """Every customer; a demo account has tens, not thousands."""
        with translate_stripe_errors():
            page = self._client.v1.customers.list({"limit": PAGE})
            return [to_customer(customer) for customer in page.auto_paging_iter()]

    def get_customer(self, customer_id: str) -> Customer:
        """One customer by id."""
        with translate_stripe_errors():
            return to_customer(self._client.v1.customers.retrieve(customer_id))

    def find_customer_by_bind_token(self, token: str) -> Customer | None:
        """Scan customer metadata for a seed-minted Telegram token.

        A list-scan rather than Customer Search because search indexing lags
        by up to a minute — unacceptable in the reviewer's first session.
        """
        with translate_stripe_errors():
            page = self._client.v1.customers.list({"limit": PAGE})
            for customer in page.auto_paging_iter():
                if (customer.get("metadata") or {}).get("telegram_bind_token") == token:
                    return to_customer(customer)
        return None

    def refund(self, payment_id: str, amount_cents: int | None, *, idempotency_key: str) -> Refund:
        """Refund against the PaymentIntent; Stripe resolves the charge."""
        params: dict[str, object] = {"payment_intent": payment_id}
        if amount_cents is not None:
            params["amount"] = amount_cents
        with translate_stripe_errors():
            return to_refund(
                self._client.v1.refunds.create(params, options={"idempotency_key": idempotency_key})  # type: ignore[arg-type]
            )

    def create_invoice(
        self,
        *,
        customer_id: str,
        amount_cents: int,
        description: str,
        due_date: date,
        idempotency_key: str,
    ) -> Invoice:
        """Create, itemise, and finalise a send-by-email invoice.

        Three requests, each with its own derived idempotency key so a retry
        after a partial failure resumes rather than duplicates. The due date
        is the end of the given local day, which Stripe requires to be in the future.
        """
        due_at = datetime.combine(due_date, time(23, 59), tzinfo=local_timezone())
        with translate_stripe_errors():
            invoice = self._client.v1.invoices.create(
                {
                    "customer": customer_id,
                    "collection_method": "send_invoice",
                    "due_date": int(due_at.timestamp()),
                    "description": description,
                    "metadata": {"created_by": "assistant"},
                },
                options={"idempotency_key": f"{idempotency_key}:invoice"},
            )
            self._client.v1.invoice_items.create(
                {
                    "customer": customer_id,
                    "invoice": invoice.id,
                    "amount": amount_cents,
                    "currency": "usd",
                    "description": description,
                },
                options={"idempotency_key": f"{idempotency_key}:item"},
            )
            finalized = self._client.v1.invoices.finalize_invoice(
                invoice.id, {"expand": ["customer"]}, options={"idempotency_key": f"{idempotency_key}:finalize"}
            )
        return to_invoice(finalized)

    def create_payment_link(self, *, amount_cents: int, description: str, idempotency_key: str) -> str:
        """A payment link needs a Price; create an ad-hoc one with inline product data."""
        with translate_stripe_errors():
            price = self._client.v1.prices.create(
                {"unit_amount": amount_cents, "currency": "usd", "product_data": {"name": description}},
                options={"idempotency_key": f"{idempotency_key}:price"},
            )
            link = self._client.v1.payment_links.create(
                {
                    "line_items": [{"price": price.id, "quantity": 1}],
                    "metadata": {"created_by": "assistant"},
                },
                options={"idempotency_key": f"{idempotency_key}:link"},
            )
        return link.url

    def pay_invoice(self, invoice_id: str, *, idempotency_key: str) -> Invoice:
        """Charge the customer's default payment method for an open invoice."""
        with translate_stripe_errors():
            paid = self._client.v1.invoices.pay(
                invoice_id, {"expand": ["customer"]}, options={"idempotency_key": idempotency_key}
            )
        return to_invoice(paid)
```

- [ ] **Step 4: Run tests and lint**

Run: `uv run pytest tests/test_owner_client_errors.py -q && uv run ruff check .`
Expected: 4 passed; ruff clean.

- [ ] **Step 5: Commit**

```bash
git add app/stripe_/owner_client.py tests/test_owner_client_errors.py
git commit -m "feat(stripe): owner gateway over StripeClient with pinned API version and error translation"
```

### Task 6: SQLite — models and repositories

**Files:**
- Create: `app/db/__init__.py`, `app/db/engine.py`, `app/db/clock.py`, `app/db/models.py`, `app/db/conversations.py`, `app/db/pending_actions.py`, `app/db/bindings.py`, `app/db/escalations.py`, `app/db/audit.py`, `tests/conftest.py`
- Test: `tests/test_db.py`

**Interfaces:**
- Consumes: `BINDING_INACTIVITY` (Task 2).
- Produces: `make_engine(url) -> Engine`, `session_scope(engine)` context manager, `utcnow() -> datetime` (naive UTC — SQLite drops tzinfo, so the DB layer stores naive UTC consistently); ORM classes `Conversation`, `Message`, `PendingAction`, `TelegramBinding`, `Escalation`, `AuditEntry`; repository functions listed in each module below. Fixture `engine` in `tests/conftest.py`.

- [ ] **Step 1: Write the fixture and failing tests**

`tests/conftest.py`:

```python
"""Shared fixtures: a throwaway SQLite engine per test."""

from pathlib import Path

import pytest
from sqlalchemy import Engine

from app.db.engine import make_engine


@pytest.fixture
def engine(tmp_path: Path) -> Engine:
    """A fresh file-backed SQLite database with all tables created."""
    return make_engine(f"sqlite:///{tmp_path / 'test.db'}")
```

`tests/test_db.py`:

```python
"""Persistence invariants: a pending action executes once; bindings expire."""

from datetime import datetime, timedelta

from sqlalchemy import Engine

from app.db import bindings, conversations, escalations, pending_actions
from app.db.engine import session_scope

NOW = datetime(2026, 9, 1, 12, 0)


def test_pending_action_can_be_claimed_exactly_once(engine: Engine) -> None:
    """Two approvals of the same action_id must not produce two refunds."""
    with session_scope(engine) as session:
        action = pending_actions.create(
            session, conversation_id="c1", channel="web", actor="owner", action="refund_payment",
            parameters={"payment_id": "pi_1", "amount_cents": None}, summary="Refund $45.00", prompt="refund",
        )
        action_id = action.id
    with session_scope(engine) as session:
        assert pending_actions.claim(session, action_id) is True
    with session_scope(engine) as session:
        assert pending_actions.claim(session, action_id) is False
        assert pending_actions.get(session, action_id).status == "executed"  # type: ignore[union-attr]


def test_binding_expires_after_inactivity(engine: Engine) -> None:
    """Fourteen idle days revoke the binding; activity inside the window renews it."""
    with session_scope(engine) as session:
        bindings.bind(session, telegram_id=42, customer_id="cus_acme", customer_name="Acme Corp", now=NOW)
    with session_scope(engine) as session:
        assert bindings.resolve(session, 42, NOW + timedelta(days=13)) is not None
    with session_scope(engine) as session:
        # last_seen_at moved to day 13, so day 26 is still inside the window; day 28 is not.
        assert bindings.resolve(session, 42, NOW + timedelta(days=26)) is not None
        assert bindings.resolve(session, 42, NOW + timedelta(days=41)) is None
    with session_scope(engine) as session:
        assert bindings.resolve(session, 42, NOW + timedelta(days=41, hours=1)) is None


def test_owner_revocation_covers_every_binding_for_a_customer(engine: Engine) -> None:
    """DELETE /api/customers/{id}/telegram-binding must cut off every device."""
    with session_scope(engine) as session:
        bindings.bind(session, telegram_id=1, customer_id="cus_acme", customer_name="Acme Corp", now=NOW)
        bindings.bind(session, telegram_id=2, customer_id="cus_acme", customer_name="Acme Corp", now=NOW)
        bindings.bind(session, telegram_id=3, customer_id="cus_maya", customer_name="Maya Chen", now=NOW)
    with session_scope(engine) as session:
        assert bindings.revoke_for_customer(session, "cus_acme", NOW) == 2
        assert bindings.resolve(session, 1, NOW) is None
        assert bindings.resolve(session, 3, NOW) is not None


def test_escalation_is_approved_once(engine: Engine) -> None:
    """Approving twice is a no-op the second time so the customer is not notified twice."""
    with session_scope(engine) as session:
        esc = escalations.file(
            session, telegram_id=42, customer_id="cus_acme", customer_name="Acme Corp",
            invoice_id="in_1", amount_cents=240000, reason="Above the bot's limit", now=NOW,
        )
        esc_id = esc.id
    with session_scope(engine) as session:
        assert escalations.mark_approved(session, esc_id, NOW) is not None
        assert escalations.mark_approved(session, esc_id, NOW) is None
        assert escalations.pending(session) == []


def test_conversation_history_is_oldest_first_and_bounded(engine: Engine) -> None:
    """The planner sees the last N turns in chronological order."""
    with session_scope(engine) as session:
        for i in range(5):
            conversations.append(session, "c1", "user" if i % 2 == 0 else "assistant", f"m{i}")
    with session_scope(engine) as session:
        assert [m.content for m in conversations.history(session, "c1", limit=3)] == ["m2", "m3", "m4"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_db.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 3: Implement engine, clock, and models**

`app/db/__init__.py`: `"""SQLite persistence for what Stripe cannot hold: conversations, confirmations, bindings, escalations, audit."""`

`app/db/clock.py`:

```python
"""One clock for the database layer."""

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Current time as naive UTC.

    SQLite has no timezone type and SQLAlchemy hands back naive datetimes, so
    the whole DB layer stores and compares naive UTC rather than mixing.
    """
    return datetime.now(UTC).replace(tzinfo=None)
```

`app/db/engine.py`:

```python
"""Engine construction and the session context manager."""

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session

from app.db.models import Base

SQLITE_PREFIX = "sqlite:///"


def make_engine(database_url: str) -> Engine:
    """Create the engine, its parent directory, and every table.

    Two processes (API and bot) share the file, so WAL mode and a busy
    timeout are set on every connection.
    """
    if database_url.startswith(SQLITE_PREFIX) and not database_url.endswith(":memory:"):
        Path(database_url.removeprefix(SQLITE_PREFIX)).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _configure(dbapi_connection: Any, _record: Any) -> None:
        """Enable concurrent readers alongside one writer."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()

    Base.metadata.create_all(engine)
    return engine


@contextmanager
def session_scope(engine: Engine) -> Iterator[Session]:
    """A transaction: commit on success, roll back on any exception."""
    session = Session(engine)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
```

`app/db/models.py`:

```python
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
    """A proposed mutation awaiting approval. Approval executes exactly these parameters."""

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
```

- [ ] **Step 4: Implement the repositories**

`app/db/conversations.py`:

```python
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
    message = Message(conversation_id=conversation_id, role=role, content=content, created_at=utcnow())
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
```

`app/db/pending_actions.py`:

```python
"""Proposed mutations awaiting approval.

`claim` is the safety-critical function: it flips `pending → executed` in a
single conditional UPDATE, so two concurrent approvals cannot both proceed.
"""

import json
import secrets
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.clock import utcnow
from app.db.models import PendingAction


def new_action_id() -> str:
    """Short, unguessable id shown in the UI, e.g. `act_7f3a9c1d`."""
    return f"act_{secrets.token_hex(4)}"


def create(
    session: Session,
    *,
    conversation_id: str,
    channel: str,
    actor: str,
    action: str,
    parameters: dict[str, Any],
    summary: str,
    prompt: str,
) -> PendingAction:
    """Store a fully resolved proposal."""
    row = PendingAction(
        id=new_action_id(), conversation_id=conversation_id, channel=channel, actor=actor,
        action=action, parameters_json=json.dumps(parameters, default=str), summary=summary,
        prompt=prompt, status="pending", created_at=utcnow(),
    )
    session.add(row)
    session.flush()
    return row


def get(session: Session, action_id: str) -> PendingAction | None:
    """Lookup by id."""
    return session.get(PendingAction, action_id)


def claim(session: Session, action_id: str) -> bool:
    """Atomically move a pending action to executed. False if it was not pending."""
    result = session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.status == "pending")
        .values(status="executed", executed_at=utcnow())
    )
    return result.rowcount == 1


def finish(session: Session, action_id: str, result: Any) -> None:
    """Attach the execution result for the history view."""
    session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id)
        .values(result_json=json.dumps(result, default=str))
    )


def cancel(session: Session, action_id: str) -> bool:
    """Dismiss a pending action. False if it had already been decided."""
    result = session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id, PendingAction.status == "pending")
        .values(status="cancelled", executed_at=utcnow())
    )
    return result.rowcount == 1


def latest_pending(session: Session, conversation_id: str) -> PendingAction | None:
    """The proposal a reloaded UI should still show, if any."""
    return session.scalars(
        select(PendingAction)
        .where(PendingAction.conversation_id == conversation_id, PendingAction.status == "pending")
        .order_by(PendingAction.created_at.desc())
        .limit(1)
    ).first()
```

`app/db/bindings.py`:

```python
"""Telegram identity bindings and their lifecycle (bind, renew, expire, revoke)."""

from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import TelegramBinding
from app.domain.policy import BINDING_INACTIVITY


def bind(
    session: Session, *, telegram_id: int, customer_id: str, customer_name: str, now: datetime
) -> TelegramBinding:
    """Create or replace the binding for a Telegram account (a re-bind supersedes)."""
    row = session.get(TelegramBinding, telegram_id)
    if row is None:
        row = TelegramBinding(telegram_id=telegram_id, stripe_customer_id=customer_id,
                              customer_name=customer_name, bound_at=now, last_seen_at=now)
        session.add(row)
    else:
        row.stripe_customer_id = customer_id
        row.customer_name = customer_name
        row.bound_at = now
        row.last_seen_at = now
        row.revoked_at = None
    session.flush()
    return row


def resolve(session: Session, telegram_id: int, now: datetime) -> TelegramBinding | None:
    """The active binding for a Telegram account, renewing its activity window.

    An idle binding past `BINDING_INACTIVITY` is revoked here, on first
    contact after expiry, so nothing needs a background job.
    """
    row = session.get(TelegramBinding, telegram_id)
    if row is None or row.revoked_at is not None:
        return None
    if now - row.last_seen_at > BINDING_INACTIVITY:
        row.revoked_at = now
        session.flush()
        return None
    row.last_seen_at = now
    session.flush()
    return row


def revoke(session: Session, telegram_id: int, now: datetime) -> bool:
    """Customer-side `/logout`."""
    result = session.execute(
        update(TelegramBinding)
        .where(TelegramBinding.telegram_id == telegram_id, TelegramBinding.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return result.rowcount == 1


def revoke_for_customer(session: Session, customer_id: str, now: datetime) -> int:
    """Owner-side revocation of every device bound to a customer."""
    result = session.execute(
        update(TelegramBinding)
        .where(TelegramBinding.stripe_customer_id == customer_id, TelegramBinding.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    return result.rowcount


def active_for_customer(session: Session, customer_id: str) -> TelegramBinding | None:
    """Where to notify a customer, if they are bound anywhere."""
    return session.scalars(
        select(TelegramBinding)
        .where(TelegramBinding.stripe_customer_id == customer_id, TelegramBinding.revoked_at.is_(None))
        .order_by(TelegramBinding.last_seen_at.desc())
        .limit(1)
    ).first()
```

`app/db/escalations.py`:

```python
"""Requests handed from the bot to the owner."""

import secrets
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.models import Escalation


def file(
    session: Session,
    *,
    telegram_id: int,
    customer_id: str,
    customer_name: str,
    invoice_id: str | None,
    amount_cents: int,
    reason: str,
    now: datetime,
) -> Escalation:
    """Record a new pending escalation."""
    row = Escalation(
        id=f"esc_{secrets.token_hex(4)}", telegram_id=telegram_id, stripe_customer_id=customer_id,
        customer_name=customer_name, invoice_id=invoice_id, amount_cents=amount_cents,
        reason=reason, status="pending", created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def pending(session: Session) -> list[Escalation]:
    """Everything awaiting the owner, oldest first."""
    return list(session.scalars(
        select(Escalation).where(Escalation.status == "pending").order_by(Escalation.created_at)
    ).all())


def get(session: Session, escalation_id: str) -> Escalation | None:
    """Lookup by id."""
    return session.get(Escalation, escalation_id)


def mark_approved(session: Session, escalation_id: str, now: datetime) -> Escalation | None:
    """Approve once; returns None when it was not pending so callers do not re-notify."""
    result = session.execute(
        update(Escalation)
        .where(Escalation.id == escalation_id, Escalation.status == "pending")
        .values(status="approved", resolved_at=now)
    )
    if result.rowcount != 1:
        return None
    return session.get(Escalation, escalation_id)
```

`app/db/audit.py`:

```python
"""The audit log: every executed action and the prompt behind it."""

import json
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.clock import utcnow
from app.db.models import AuditEntry


def record(
    session: Session,
    *,
    channel: str,
    actor: str,
    prompt: str,
    action: str,
    parameters: dict[str, Any],
    result: Any,
    mutation: bool,
) -> AuditEntry:
    """Append one entry. Results are serialised with `default=str` so datetimes survive."""
    row = AuditEntry(
        created_at=utcnow(), channel=channel, actor=actor, prompt=prompt, action=action,
        parameters_json=json.dumps(parameters, default=str),
        result_json=json.dumps(result, default=str), mutation=mutation,
    )
    session.add(row)
    session.flush()
    return row


def recent(session: Session, limit: int = 100) -> list[AuditEntry]:
    """Newest first for the API."""
    return list(session.scalars(
        select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit)
    ).all())
```

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/test_db.py -q && uv run ruff check .`
Expected: 5 passed; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add app/db tests/conftest.py tests/test_db.py
git commit -m "feat(db): SQLite models and repositories with claim-once confirmations and binding expiry"
```

### Task 7: LLM backends behind one `complete()` interface

**Files:**
- Create: `app/llm/__init__.py`, `app/llm/base.py`, `app/llm/anthropic_backend.py`, `app/llm/openai_backend.py`, `app/llm/factory.py`, `tests/fakes/llm_fake.py`
- Test: `tests/test_llm_base.py`, `tests/test_llm_smoke.py`

**Interfaces:**
- Consumes: `Settings.llm_provider`, `.anthropic_api_key`, `.openai_api_key`, `.resolved_model` (Task 1).
- Produces: `ChatMessage(role, content)`, `LLMError(message, hint)`, `LLMBackend` Protocol with `complete(*, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048) -> str`, `extract_json_object(text) -> dict[str, Any]`, `AnthropicBackend(api_key, model)`, `OpenAIBackend(api_key, model)`, `build_backend(settings) -> LLMBackend`, `ScriptedLLM(responses)` with `.calls`.
- SDK facts: anthropic 1.x — `anthropic.Anthropic(api_key=..., timeout=..., max_retries=...)`, `client.messages.create(model, max_tokens, system, messages, output_config={"effort": "low"})`, text in `block.text` for blocks with `type == "text"`, `response.stop_reason == "refusal"` must be checked, assistant prefill is rejected on current models (so JSON is requested in the system prompt and parsed leniently). openai 3.x — `openai.OpenAI(api_key=..., timeout=..., max_retries=...)`, `client.chat.completions.create(model, messages, max_completion_tokens)`, text in `response.choices[0].message.content`.

- [ ] **Step 1: Write the failing tests**

`tests/fakes/llm_fake.py`:

```python
"""A scripted LLM: returns canned responses in order and records every call."""

from collections.abc import Sequence

from app.llm.base import ChatMessage


class ScriptedLLM:
    """Pops one scripted response per `complete()`; fails loudly when the script runs out."""

    def __init__(self, responses: Sequence[str]) -> None:
        """Queue the responses the test expects the planner to produce."""
        self._responses = list(responses)
        self.calls: list[tuple[str, list[ChatMessage]]] = []

    def complete(self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048) -> str:
        """Return the next scripted response."""
        self.calls.append((system, list(messages)))
        if not self._responses:
            raise AssertionError("Unexpected LLM call: the script is exhausted")
        return self._responses.pop(0)
```

`tests/test_llm_base.py`:

```python
"""JSON extraction tolerates the ways models wrap JSON, and rejects the rest."""

import pytest

from app.llm.base import extract_json_object


def test_extracts_from_code_fence_and_surrounding_prose() -> None:
    """Models sometimes fence or preface JSON despite instructions; both must parse."""
    fenced = 'Sure:\n```json\n{"action": "answer", "parameters": {"text": "hi"}}\n```'
    assert extract_json_object(fenced)["action"] == "answer"
    plain = '{"action": "clarify", "parameters": {"question": "Which Maya?"}} trailing'
    assert extract_json_object(plain)["parameters"]["question"] == "Which Maya?"


def test_non_object_or_garbage_raises() -> None:
    """A list, or no JSON at all, is a planner failure the loop reports back to the model."""
    with pytest.raises(ValueError):
        extract_json_object("[1, 2]")
    with pytest.raises(ValueError):
        extract_json_object("I refuse to answer in JSON")
```

`tests/test_llm_smoke.py`:

```python
"""One real call per provider, deselected by default. Nondeterministic assertions are theatre."""

import pytest

from app.llm.base import ChatMessage, extract_json_object
from app.llm.factory import build_backend
from app.settings import ConfigError, Settings


@pytest.mark.live_llm
def test_configured_backend_returns_parseable_json() -> None:
    """The configured provider answers a trivial JSON request end to end."""
    settings = Settings()
    try:
        settings.require_llm()
    except ConfigError as exc:
        pytest.skip(str(exc))
    backend = build_backend(settings)
    text = backend.complete(
        system='Reply with exactly this JSON and nothing else: {"ok": true}',
        messages=[ChatMessage(role="user", content="go")],
        max_tokens=64,
    )
    assert extract_json_object(text) == {"ok": True}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_llm_base.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.llm'`.

- [ ] **Step 3: Implement the LLM package**

`app/llm/__init__.py`: `"""LLM providers behind one text-completion protocol."""`

`app/llm/base.py`:

```python
"""The one interface the agent uses to talk to a model.

Deliberately text-in, text-out: the planner asks for JSON in its system
prompt and `extract_json_object` parses it. That keeps both providers on an
identical code path and keeps every guardrail in Python.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol


@dataclass(frozen=True)
class ChatMessage:
    """A prior turn in the conversation as sent to the model."""

    role: Literal["user", "assistant"]
    content: str


class LLMError(RuntimeError):
    """The model call failed in a way the user should hear about, with a hint."""

    def __init__(self, message: str, hint: str = "") -> None:
        """Store the message and an optional fix."""
        super().__init__(message)
        self.hint = hint


class LLMBackend(Protocol):
    """A provider that completes a chat transcript into text."""

    def complete(self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048) -> str:
        """Return the model's text for the given system prompt and transcript."""
        ...


def extract_json_object(text: str) -> dict[str, Any]:
    """Parse the first JSON object in a model reply.

    Tolerates code fences and prose around the object because models do
    both occasionally, and the loop would rather recover than fail a turn.

    Raises:
        ValueError: No object could be parsed. The loop feeds this back to the
            planner as an observation so it can try again.
    """
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("No JSON object found in the model reply")
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed JSON in the model reply: {exc.msg}") from exc
    if not isinstance(parsed, dict):
        raise ValueError("The model reply must be a JSON object")
    return parsed
```

`app/llm/anthropic_backend.py`:

```python
"""Anthropic Messages API backend."""

from collections.abc import Sequence

import anthropic

from app.llm.base import ChatMessage, LLMError


class AnthropicBackend:
    """Calls Claude with low effort: planner turns are short and latency-sensitive."""

    def __init__(self, api_key: str, model: str) -> None:
        """Create a client with a bounded timeout so a stuck call cannot hang a turn."""
        self._client = anthropic.Anthropic(api_key=api_key, timeout=60.0, max_retries=2)
        self._model = model

    def complete(self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048) -> str:
        """Complete the transcript; concatenates text blocks.

        Raises:
            LLMError: Bad key, API failure, connectivity, or a refusal stop reason.
        """
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=max_tokens,
                system=system,
                messages=[{"role": m.role, "content": m.content} for m in messages],
                output_config={"effort": "low"},
            )
        except anthropic.AuthenticationError as exc:
            raise LLMError("Anthropic rejected the API key.", hint="Check ANTHROPIC_API_KEY in .env.") from exc
        except anthropic.APIStatusError as exc:
            raise LLMError(f"Anthropic API error {exc.status_code}.", hint=str(exc.message)) from exc
        except anthropic.APIConnectionError as exc:
            raise LLMError("Could not reach the Anthropic API.", hint="Check your network connection.") from exc
        if response.stop_reason == "refusal":
            raise LLMError("The model declined this request.")
        return "".join(block.text for block in response.content if block.type == "text")
```

`app/llm/openai_backend.py`:

```python
"""OpenAI Chat Completions backend."""

from collections.abc import Sequence

import openai

from app.llm.base import ChatMessage, LLMError


class OpenAIBackend:
    """Calls an OpenAI chat model with the system prompt as the first message."""

    def __init__(self, api_key: str, model: str) -> None:
        """Create a client with a bounded timeout."""
        self._client = openai.OpenAI(api_key=api_key, timeout=60.0, max_retries=2)
        self._model = model

    def complete(self, *, system: str, messages: Sequence[ChatMessage], max_tokens: int = 2048) -> str:
        """Complete the transcript.

        Raises:
            LLMError: Bad key, API failure, or connectivity.
        """
        try:
            response = self._client.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    *({"role": m.role, "content": m.content} for m in messages),
                ],
                max_completion_tokens=max_tokens,
            )
        except openai.AuthenticationError as exc:
            raise LLMError("OpenAI rejected the API key.", hint="Check OPENAI_API_KEY in .env.") from exc
        except openai.APIStatusError as exc:
            raise LLMError(f"OpenAI API error {exc.status_code}.", hint=str(exc.message)) from exc
        except openai.APIConnectionError as exc:
            raise LLMError("Could not reach the OpenAI API.", hint="Check your network connection.") from exc
        return response.choices[0].message.content or ""
```

`app/llm/factory.py`:

```python
"""Pick a backend from settings."""

from app.llm.anthropic_backend import AnthropicBackend
from app.llm.base import LLMBackend
from app.llm.openai_backend import OpenAIBackend
from app.settings import Settings


def build_backend(settings: Settings) -> LLMBackend:
    """Instantiate the provider named by LLM_PROVIDER with its resolved model."""
    if settings.llm_provider == "anthropic":
        return AnthropicBackend(settings.anthropic_api_key, settings.resolved_model)
    return OpenAIBackend(settings.openai_api_key, settings.resolved_model)
```

- [ ] **Step 4: Run tests and lint**

Run: `uv run pytest tests/test_llm_base.py -q && uv run pytest -m live_llm tests/test_llm_smoke.py -q && uv run ruff check .`
Expected: 2 passed; the smoke test passes if a key is present in `.env`, otherwise 1 skipped; ruff clean. Also confirm `uv run pytest -q` alone reports the smoke test as deselected.

- [ ] **Step 5: Commit**

```bash
git add app/llm tests/fakes/llm_fake.py tests/test_llm_base.py tests/test_llm_smoke.py
git commit -m "feat(llm): Anthropic and OpenAI backends behind one complete() protocol"
```

### Task 8: Agent core — schema, registry, executor, and the loop

**Files:**
- Create: `app/agent/__init__.py`, `app/agent/schema.py`, `app/agent/events.py`, `app/agent/executor.py`, `app/agent/loop.py`
- Test: `tests/test_executor.py`, `tests/test_agent_loop.py`

**Interfaces:**
- Consumes: `LLMBackend`, `ChatMessage`, `extract_json_object` (Task 7); `MAX_AGENT_ITERATIONS` (Task 2); `StripeGatewayError` (Task 4).
- Produces: `ActionCall(reasoning, action, parameters)`, `AnswerParams(text)`, `ClarifyParams(question)`, `TERMINAL_ACTIONS`, `Proposal(summary=None, resolved=None)`, `ActionSpec(name, description, params, handler, mutation=False, describe=None)`, `Registry(specs)` with `get(name)`, `names()`, `specs()`, `prompt_catalog()`; `AgentEvent(type, data)` with types `planning | action | observation | confirmation | answer | clarify | error`, `to_jsonable(value)`; `ActionError`, `parse_call(raw) -> ActionCall`, `resolve(registry, call) -> tuple[ActionSpec, BaseModel]`; `TurnHooks(propose, audit)`, `run_turn(*, llm, registry, ctx, system, history, prompt, hooks) -> Iterator[AgentEvent]`, `GIVE_UP_TEXT`.
- Handler signature everywhere: `handler(ctx, params) -> Any` where `ctx` is the channel's context object (Task 10/11) and `params` is an instance of `spec.params`. `describe(ctx, params) -> Proposal`: `Proposal(summary=...)` asks for confirmation; `Proposal(resolved=...)` means the mutation resolved itself into a non-mutating result (used by the ceiling guard).

- [ ] **Step 1: Write the failing tests**

`tests/test_executor.py`:

```python
"""The LLM boundary: anything that is not a known, well-formed action is rejected."""

import pytest
from pydantic import BaseModel

from app.agent.executor import ActionError, parse_call, resolve
from app.agent.schema import ActionCall, ActionSpec, Registry


class EchoParams(BaseModel):
    """Parameters for the test-only echo action."""

    text: str


def _echo(_ctx: object, params: EchoParams) -> dict[str, str]:
    """Return the text it was given."""
    return {"echo": params.text}


REGISTRY = Registry([ActionSpec("echo", "Echo text back", EchoParams, _echo)])


def test_malformed_call_is_rejected() -> None:
    """Wrong types or unexpected keys never reach a handler."""
    with pytest.raises(ActionError):
        parse_call({"action": 42})
    with pytest.raises(ActionError):
        parse_call({"action": "echo", "parameters": {}, "surprise": True})


def test_unknown_action_lists_the_valid_ones() -> None:
    """The error is written for the planner: it names what it may call instead."""
    with pytest.raises(ActionError, match="echo"):
        resolve(REGISTRY, ActionCall(action="read_other_customer", parameters={}))


def test_invalid_parameters_are_rejected_with_field_names() -> None:
    """Missing or mistyped parameters fail validation before execution."""
    with pytest.raises(ActionError, match="text"):
        resolve(REGISTRY, ActionCall(action="echo", parameters={}))


def test_mutation_requires_describe() -> None:
    """A mutation with no describe() could never be confirmed; refuse to register it."""
    with pytest.raises(ValueError):
        ActionSpec("boom", "x", EchoParams, _echo, mutation=True)
```

`tests/test_agent_loop.py`:

```python
"""The loop: observe and iterate, stop on answer/clarify, pause on mutations, cap at five."""

import json
from typing import Any

from pydantic import BaseModel

from app.agent.loop import GIVE_UP_TEXT, TurnHooks, run_turn
from app.agent.schema import ActionSpec, Proposal, Registry
from app.domain.policy import MAX_AGENT_ITERATIONS
from tests.fakes.llm_fake import ScriptedLLM


class EchoParams(BaseModel):
    """Echo parameters."""

    text: str


class RefundParams(BaseModel):
    """Refund parameters."""

    payment_id: str
    amount_cents: int | None = None


def _echo(_ctx: dict[str, Any], params: EchoParams) -> dict[str, str]:
    """Non-mutating action."""
    return {"echo": params.text}


def _describe_refund(_ctx: dict[str, Any], params: RefundParams) -> Proposal:
    """Resolve the refund into a human summary."""
    return Proposal(summary=f"Refund {params.payment_id}")


def _refund(ctx: dict[str, Any], params: RefundParams) -> dict[str, bool]:
    """Mutating action; records that it ran."""
    ctx["refunds"].append(params.payment_id)
    return {"ok": True}


REGISTRY = Registry([
    ActionSpec("echo", "Echo text", EchoParams, _echo),
    ActionSpec("refund", "Refund a payment", RefundParams, _refund, mutation=True, describe=_describe_refund),
])


def _call(action: str, **parameters: Any) -> str:
    """Serialise a planner step."""
    return json.dumps({"reasoning": f"do {action}", "action": action, "parameters": parameters})


def _hooks(proposals: list[str], audits: list[str]) -> TurnHooks:
    """Hooks that record instead of persisting."""
    return TurnHooks(
        propose=lambda spec, params, summary: (proposals.append(summary), "act_1")[1],
        audit=lambda action, parameters, result, mutation: audits.append(action),
    )


def _run(llm: ScriptedLLM, ctx: dict[str, Any] | None = None, hooks: TurnHooks | None = None) -> list[Any]:
    """Drive a turn to completion and collect events."""
    return list(run_turn(
        llm=llm, registry=REGISTRY, ctx=ctx or {"refunds": []}, system="sys", history=[],
        prompt="hello", hooks=hooks or _hooks([], []),
    ))


def test_observation_then_answer() -> None:
    """A read action produces an observation the planner sees before answering."""
    llm = ScriptedLLM([_call("echo", text="hi"), _call("answer", text="Done")])
    audits: list[str] = []
    events = _run(llm, hooks=_hooks([], audits))
    assert [e.type for e in events] == ["planning", "action", "observation", "planning", "answer"]
    assert events[2].data["result"] == {"echo": "hi"}
    assert events[-1].data["text"] == "Done"
    assert audits == ["echo"]
    assert "Observation for echo" in llm.calls[1][1][-1].content


def test_mutation_pauses_for_confirmation_without_executing() -> None:
    """Proposing a refund stores it and stops; nothing is refunded and the LLM is not re-asked."""
    llm = ScriptedLLM([_call("refund", payment_id="pi_1")])
    ctx: dict[str, Any] = {"refunds": []}
    proposals: list[str] = []
    events = _run(llm, ctx, _hooks(proposals, []))
    assert events[-1].type == "confirmation"
    assert events[-1].data == {
        "action_id": "act_1", "action": "refund", "summary": "Refund pi_1",
        "parameters": {"payment_id": "pi_1", "amount_cents": None},
    }
    assert ctx["refunds"] == []
    assert proposals == ["Refund pi_1"]
    assert len(llm.calls) == 1


def test_loop_is_capped() -> None:
    """A model that never answers is cut off after MAX_AGENT_ITERATIONS steps."""
    llm = ScriptedLLM([_call("echo", text="again")] * (MAX_AGENT_ITERATIONS + 3))
    events = _run(llm)
    assert len(llm.calls) == MAX_AGENT_ITERATIONS
    assert events[-1].type == "answer"
    assert events[-1].data["text"] == GIVE_UP_TEXT


def test_bad_json_and_unknown_actions_are_fed_back_not_fatal() -> None:
    """The planner gets one chance per mistake to correct itself."""
    llm = ScriptedLLM(["not json at all", _call("nope"), _call("answer", text="ok")])
    events = _run(llm)
    assert [e.type for e in events] == ["error", "planning", "error", "planning", "answer"]
    assert "Unknown action" in llm.calls[2][1][-1].content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_executor.py tests/test_agent_loop.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent'`.

- [ ] **Step 3: Implement schema and events**

`app/agent/__init__.py`: `"""The propose→execute→narrate agent: schema, executor, loop, confirmation, prompts."""`

`app/agent/schema.py`:

```python
"""The action vocabulary: what a planner step looks like and how actions are declared."""

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class ActionCall(BaseModel):
    """One planner step. Unknown keys are an error so drift is caught, not ignored."""

    model_config = ConfigDict(extra="forbid")

    reasoning: str = ""
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class AnswerParams(BaseModel):
    """Terminal: reply to the user."""

    text: str


class ClarifyParams(BaseModel):
    """Terminal: ask the user one question."""

    question: str


TERMINAL_ACTIONS: dict[str, type[BaseModel]] = {"answer": AnswerParams, "clarify": ClarifyParams}


class ActionHandler(Protocol):
    """Executes an action against the channel's context object."""

    def __call__(self, ctx: Any, params: Any) -> Any:
        """Run the action and return a JSON-serialisable result."""
        ...


class DescribeHandler(Protocol):
    """Resolves a proposed mutation into a Proposal before anything executes."""

    def __call__(self, ctx: Any, params: Any) -> "Proposal":
        """Summarise for confirmation, or resolve without a mutation."""
        ...


@dataclass(frozen=True)
class Proposal:
    """The outcome of describing a mutation before it runs.

    Exactly one field is set. `summary` asks the user to confirm; `resolved`
    means no mutation is needed after all (the ceiling guard uses this to
    turn a payment into an escalation record).
    """

    summary: str | None = None
    resolved: Any = None


@dataclass(frozen=True)
class ActionSpec:
    """A registered action: schema, handler, and whether it needs confirmation."""

    name: str
    description: str
    params: type[BaseModel]
    handler: ActionHandler
    mutation: bool = False
    describe: DescribeHandler | None = None

    def __post_init__(self) -> None:
        """A mutation without describe() could never be confirmed; reject it at import time."""
        if self.mutation and self.describe is None:
            raise ValueError(f"mutation '{self.name}' must provide describe()")


def _params_outline(model: type[BaseModel]) -> str:
    """Compact `name: type (required?) — description` lines from a model's JSON schema."""
    schema = model.model_json_schema()
    required = set(schema.get("required", []))
    lines = []
    for name, prop in schema.get("properties", {}).items():
        kind = prop.get("type") or " | ".join(o.get("type", "null") for o in prop.get("anyOf", []))
        flag = "required" if name in required else "optional"
        note = f" — {prop['description']}" if prop.get("description") else ""
        lines.append(f"    {name}: {kind} ({flag}){note}")
    return "\n".join(lines) or "    (none)"


class Registry:
    """An ordered set of actions plus the two terminals, rendered for the planner."""

    def __init__(self, specs: Iterable[ActionSpec]) -> None:
        """Index specs by name."""
        self._specs = {spec.name: spec for spec in specs}

    def get(self, name: str) -> ActionSpec | None:
        """Lookup by action name."""
        return self._specs.get(name)

    def names(self) -> list[str]:
        """Action names in declaration order."""
        return list(self._specs)

    def specs(self) -> list[ActionSpec]:
        """All specs in declaration order."""
        return list(self._specs.values())

    def prompt_catalog(self) -> str:
        """The action list as the planner sees it, terminals included."""
        blocks = [
            f"- {spec.name}: {spec.description}\n  parameters:\n{_params_outline(spec.params)}"
            for spec in self._specs.values()
        ]
        blocks.append("- answer: reply to the user and stop\n  parameters:\n    text: string (required)")
        blocks.append("- clarify: ask the user one question and stop\n  parameters:\n    question: string (required)")
        return "\n".join(blocks)
```

`app/agent/events.py`:

```python
"""Typed events the loop emits, and JSON coercion for results."""

import dataclasses
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel

EventType = Literal["planning", "action", "observation", "confirmation", "answer", "clarify", "error"]


@dataclass(frozen=True)
class AgentEvent:
    """One step of the agent's work, streamable as an SSE event."""

    type: EventType
    data: dict[str, Any]


def to_jsonable(value: Any) -> Any:
    """Recursively convert dataclasses, models, and dates into JSON-safe values."""
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {f.name: to_jsonable(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [to_jsonable(v) for v in value]
    return value
```

- [ ] **Step 4: Implement the executor and the loop**

`app/agent/executor.py`:

```python
"""Validation at the LLM boundary. Nothing unvalidated reaches a handler."""

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ValidationError

from app.agent.schema import ActionCall, ActionSpec, Registry


class ActionError(Exception):
    """A recoverable problem, phrased for the planner, returned as an observation."""


def _compact(exc: ValidationError) -> str:
    """Render pydantic errors as `field: message` pairs."""
    return "; ".join(
        f"{'.'.join(str(p) for p in err['loc']) or 'body'}: {err['msg']}" for err in exc.errors()
    )


def parse_call(raw: Mapping[str, Any]) -> ActionCall:
    """Validate the shape of a planner step.

    Raises:
        ActionError: The object is not `{reasoning?, action, parameters?}`.
    """
    try:
        return ActionCall.model_validate(dict(raw))
    except ValidationError as exc:
        raise ActionError(f"Malformed action: {_compact(exc)}") from exc


def resolve(registry: Registry, call: ActionCall) -> tuple[ActionSpec, BaseModel]:
    """Find the action and validate its parameters.

    Raises:
        ActionError: Unknown action (lists the valid names) or invalid parameters.
    """
    spec = registry.get(call.action)
    if spec is None:
        raise ActionError(
            f"Unknown action '{call.action}'. Valid actions: {', '.join(registry.names())}, answer, clarify"
        )
    try:
        params = spec.params.model_validate(call.parameters)
    except ValidationError as exc:
        raise ActionError(f"Invalid parameters for {spec.name}: {_compact(exc)}") from exc
    return spec, params
```

`app/agent/loop.py`:

```python
"""The propose→execute loop.

The model proposes one JSON action per step; Python executes it and feeds
the typed observation back. `answer` and `clarify` end the turn. A mutation
ends the turn with a `confirmation` event and nothing executed. The loop is
capped so a confused model cannot spin.
"""

import json
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import BaseModel, ValidationError

from app.agent.events import AgentEvent, to_jsonable
from app.agent.executor import ActionError, parse_call, resolve
from app.agent.schema import TERMINAL_ACTIONS, ActionSpec, Registry
from app.domain.policy import MAX_AGENT_ITERATIONS
from app.llm.base import ChatMessage, LLMBackend, extract_json_object
from app.stripe_.gateway import StripeGatewayError

GIVE_UP_TEXT = "I couldn't finish that in a few steps. Could you rephrase or narrow it down?"


class ProposeHook(Protocol):
    """Stores a fully resolved proposal and returns its action_id."""

    def __call__(self, spec: ActionSpec, params: BaseModel, summary: str) -> str:
        """Persist the proposal and return the id shown to the user."""
        ...


class AuditHook(Protocol):
    """Records one executed action."""

    def __call__(self, action: str, parameters: dict[str, Any], result: Any, mutation: bool) -> None:
        """Append one audit entry."""
        ...


@dataclass(frozen=True)
class TurnHooks:
    """Side effects the loop needs but must not own: storing proposals and auditing."""

    propose: ProposeHook
    audit: AuditHook


def _feedback(transcript: list[ChatMessage], raw: str, observation: dict[str, Any], label: str) -> None:
    """Append the model's step and our observation so the next call sees both."""
    transcript.append(ChatMessage(role="assistant", content=raw))
    transcript.append(ChatMessage(role="user", content=f"Observation for {label}: {json.dumps(observation)}"))


def run_turn(
    *,
    llm: LLMBackend,
    registry: Registry,
    ctx: Any,
    system: str,
    history: Sequence[ChatMessage],
    prompt: str,
    hooks: TurnHooks,
) -> Iterator[AgentEvent]:
    """Run one user turn, yielding events as they happen.

    Args:
        llm: The planner model.
        registry: The channel's actions — owner or customer, never both.
        ctx: Passed verbatim to handlers; carries the (scoped) gateway and session.
        system: The planner system prompt for this channel.
        history: Prior turns, oldest first.
        prompt: The user's new message.
        hooks: How to store a proposal and how to audit an execution.
    """
    transcript: list[ChatMessage] = [*history, ChatMessage(role="user", content=prompt)]
    for _ in range(MAX_AGENT_ITERATIONS):
        raw = llm.complete(system=system, messages=transcript)
        try:
            call = parse_call(extract_json_object(raw))
        except (ValueError, ActionError) as exc:
            yield AgentEvent("error", {"message": str(exc)})
            _feedback(transcript, raw, {"error": str(exc)}, "invalid step")
            continue
        if call.reasoning:
            yield AgentEvent("planning", {"reasoning": call.reasoning})
        if call.action in TERMINAL_ACTIONS:
            try:
                terminal = TERMINAL_ACTIONS[call.action].model_validate(call.parameters)
            except ValidationError as exc:
                yield AgentEvent("error", {"message": str(exc)})
                _feedback(transcript, raw, {"error": f"Invalid {call.action}: {exc}"}, call.action)
                continue
            yield AgentEvent(call.action, terminal.model_dump())  # type: ignore[arg-type]
            return
        try:
            spec, params = resolve(registry, call)
        except ActionError as exc:
            yield AgentEvent("error", {"message": str(exc)})
            _feedback(transcript, raw, {"error": str(exc)}, call.action)
            continue
        args = params.model_dump(mode="json")
        yield AgentEvent("action", {"name": spec.name, "args": args})
        try:
            if spec.mutation:
                assert spec.describe is not None  # enforced by ActionSpec.__post_init__
                proposal = spec.describe(ctx, params)
                if proposal.summary is not None:
                    action_id = hooks.propose(spec, params, proposal.summary)
                    yield AgentEvent("confirmation", {
                        "action_id": action_id, "action": spec.name,
                        "summary": proposal.summary, "parameters": args,
                    })
                    return
                result: Any = proposal.resolved
            else:
                result = spec.handler(ctx, params)
        except ActionError as exc:
            result = {"error": str(exc)}
        except StripeGatewayError as exc:
            result = {"error": str(exc), "hint": exc.hint}
        else:
            hooks.audit(spec.name, args, to_jsonable(result), False)
        observation = to_jsonable(result)
        yield AgentEvent("observation", {"name": spec.name, "result": observation})
        _feedback(transcript, raw, observation, spec.name)
    yield AgentEvent("answer", {"text": GIVE_UP_TEXT})
```

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/test_executor.py tests/test_agent_loop.py -q && uv run ruff check .`
Expected: 8 passed; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add app/agent tests/test_executor.py tests/test_agent_loop.py
git commit -m "feat(agent): action schema, validating executor, and the capped propose-execute loop"
```

### Task 9: Confirmation execution, prompts, and the narrator

**Files:**
- Create: `app/agent/confirm.py`, `app/agent/prompts.py`, `app/agent/narrator.py`
- Modify: `app/db/pending_actions.py` (add `fail()`)
- Test: `tests/test_confirm.py`, `tests/test_narrator.py`

**Interfaces:**
- Consumes: `pending_actions`, `audit` repositories (Task 6); `Registry`, `to_jsonable` (Task 8); `DailyFacts` (Task 3); `LLMBackend`, `ChatMessage` (Task 7).
- Produces: `ConfirmationError(code, message)`, `UnknownAction`, `AlreadyDecided`, `Execution(action, parameters, summary, result)`, `execute_pending(*, session, action_id, registry, ctx, expected_actor, idempotency_key=None) -> Execution`; `PERSONALITY`, `OWNER_NOTES`, `CUSTOMER_NOTES`, `planner_system(*, registry, today, channel_notes) -> str`, `summary_system() -> str`, `result_system() -> str`; `narrate_summary(llm, facts) -> str`, `narrate_result(llm, *, action, summary, result) -> str`; `pending_actions.fail(session, action_id, error) -> None`.
- **Context contract** (binding on Tasks 10 and 11): every `ctx` passed to handlers is a dataclass with an `idempotency_key: str | None` field. `execute_pending` uses `dataclasses.replace(ctx, idempotency_key=...)` to inject the key, so mutation handlers read `ctx.idempotency_key` and pass it to the gateway.
- `execute_pending` has **no LLM parameter**. That absence is the safety claim; a test asserts it.

- [ ] **Step 1: Write the failing tests**

`tests/test_confirm.py`:

```python
"""Approval executes the stored action — the same parameters, exactly once, with no re-plan."""

import inspect
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel
from sqlalchemy import Engine

from app.agent.confirm import AlreadyDecided, UnknownAction, execute_pending
from app.agent.schema import ActionSpec, Proposal, Registry
from app.db import pending_actions
from app.db.engine import session_scope
from app.stripe_.gateway import NotFound
from tests.fakes.stripe_fake import FakeStripeGateway


@dataclass
class Ctx:
    """Minimal handler context honouring the idempotency_key contract."""

    gateway: FakeStripeGateway
    idempotency_key: str | None = None


class RefundParams(BaseModel):
    """Refund parameters."""

    payment_id: str
    amount_cents: int | None = None


def _refund(ctx: Ctx, params: RefundParams) -> dict[str, Any]:
    """Refund through the gateway with the injected idempotency key."""
    refund = ctx.gateway.refund(params.payment_id, params.amount_cents, idempotency_key=ctx.idempotency_key or "")
    return {"refund_id": refund.id, "amount_cents": refund.amount_cents}


REGISTRY = Registry([
    ActionSpec("refund", "Refund", RefundParams, _refund, mutation=True,
               describe=lambda ctx, p: Proposal(summary="Refund")),
])


def _stored_refund(engine: Engine, actor: str = "owner") -> str:
    """Store a pending refund of $45.00 on pi_1 and return its action_id."""
    with session_scope(engine) as session:
        row = pending_actions.create(
            session, conversation_id="c1", channel="web", actor=actor, action="refund",
            parameters={"payment_id": "pi_1", "amount_cents": 4500}, summary="Refund $45.00",
            prompt="refund Maya's last payment",
        )
        return row.id


def test_executes_the_stored_parameters_once(engine: Engine) -> None:
    """The gateway receives exactly what was approved; a second approval is refused."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_payment("pi_1", "cus_maya", 9000)
    action_id = _stored_refund(engine)
    with session_scope(engine) as session:
        execution = execute_pending(
            session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(fake), expected_actor="owner",
        )
    assert execution.result == {"refund_id": "re_1", "amount_cents": 4500}
    refund_calls = [c for c in fake.calls if c[0] == "refund"]
    assert refund_calls == [("refund", {"payment_id": "pi_1", "amount_cents": 4500, "idempotency_key": action_id})]
    with session_scope(engine) as session:
        with pytest.raises(AlreadyDecided):
            execute_pending(session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(fake), expected_actor="owner")
    assert len([c for c in fake.calls if c[0] == "refund"]) == 1


def test_execute_pending_cannot_consult_a_model() -> None:
    """Structural proof of 'never a freshly planned action': there is no way to pass an LLM."""
    assert "llm" not in inspect.signature(execute_pending).parameters


def test_wrong_actor_or_unknown_id_is_indistinguishable(engine: Engine) -> None:
    """Another actor's action_id is treated as nonexistent so ids cannot be probed."""
    action_id = _stored_refund(engine, actor="telegram:1")
    with session_scope(engine) as session:
        with pytest.raises(UnknownAction):
            execute_pending(session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(FakeStripeGateway()), expected_actor="owner")
        with pytest.raises(UnknownAction):
            execute_pending(session=session, action_id="act_nope", registry=REGISTRY, ctx=Ctx(FakeStripeGateway()), expected_actor="owner")


def test_handler_failure_marks_the_action_failed(engine: Engine) -> None:
    """A Stripe error after claiming must not leave the action re-approvable."""
    action_id = _stored_refund(engine)
    with pytest.raises(NotFound):
        with session_scope(engine) as session:
            execute_pending(session=session, action_id=action_id, registry=REGISTRY, ctx=Ctx(FakeStripeGateway()), expected_actor="owner")
    with session_scope(engine) as session:
        assert pending_actions.get(session, action_id).status == "failed"  # type: ignore[union-attr]
```

`tests/test_narrator.py`:

```python
"""The narrator receives facts as JSON and returns the model's text, trimmed."""

import json
from datetime import datetime, timezone

from app.agent.narrator import narrate_result, narrate_summary
from app.domain.summary import build_daily_facts
from tests.fakes.llm_fake import ScriptedLLM


def test_summary_narration_sends_facts_json() -> None:
    """Every number the model may quote is in the JSON it receives."""
    facts = build_daily_facts([], [], datetime(2026, 9, 1, tzinfo=timezone.utc))
    llm = ScriptedLLM(["  Quiet day so far.  "])
    assert narrate_summary(llm, facts) == "Quiet day so far."
    payload = json.loads(llm.calls[0][1][0].content)
    assert payload["today"]["succeeded_count"] == 0


def test_result_narration_includes_the_approved_summary() -> None:
    """The narration is anchored to what the user approved, not a re-interpretation."""
    llm = ScriptedLLM(["Refunded."])
    assert narrate_result(llm, action="refund_payment", summary="Refund $45.00 to Maya Chen", result={"ok": True}) == "Refunded."
    assert "Refund $45.00 to Maya Chen" in llm.calls[0][1][0].content
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_confirm.py tests/test_narrator.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.agent.confirm'`.

- [ ] **Step 3: Add `fail()` to `app/db/pending_actions.py`**

Append after `cancel`:

```python
def fail(session: Session, action_id: str, error: str) -> None:
    """Record that execution raised after the claim; the action is not re-approvable."""
    session.execute(
        update(PendingAction)
        .where(PendingAction.id == action_id)
        .values(status="failed", result_json=json.dumps({"error": error}))
    )
```

- [ ] **Step 4: Implement `app/agent/confirm.py`**

```python
"""Execute a previously proposed mutation.

The stored action is the contract: approval runs exactly the parameters the
user saw, under the registry that produced them. No model is consulted here,
which is why this module cannot import an LLM.
"""

import dataclasses
import json
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.agent.events import to_jsonable
from app.agent.schema import Registry
from app.db import audit, pending_actions


class ConfirmationError(Exception):
    """A confirmation could not proceed; `code` is stable for the API envelope."""

    def __init__(self, code: str, message: str) -> None:
        """Store a machine code and a human message."""
        super().__init__(message)
        self.code = code


class UnknownAction(ConfirmationError):
    """No pending action with this id for this actor."""

    def __init__(self) -> None:
        """Same wording for missing and foreign ids so they cannot be told apart."""
        super().__init__("unknown_action", "That confirmation has expired or does not exist.")


class AlreadyDecided(ConfirmationError):
    """The action was already executed, cancelled, or failed."""

    def __init__(self, status: str) -> None:
        """Name the status so a double-click shows 'already executed', not an error."""
        super().__init__("already_decided", f"That action was already {status}.")


@dataclass(frozen=True)
class Execution:
    """What ran and what it produced."""

    action: str
    parameters: dict[str, Any]
    summary: str
    result: Any


def execute_pending(
    *,
    session: Session,
    action_id: str,
    registry: Registry,
    ctx: Any,
    expected_actor: str,
    idempotency_key: str | None = None,
) -> Execution:
    """Claim and run a pending action.

    Args:
        session: Open transaction; the claim and the audit entry commit together.
        action_id: The id the user approved.
        registry: The same channel's registry that proposed the action.
        ctx: Handler context (a dataclass with `idempotency_key`).
        expected_actor: Who is approving; must match the proposer.
        idempotency_key: Client-supplied key (the `Idempotency-Key` header);
            defaults to the action id, which is itself unique per proposal.

    Raises:
        UnknownAction: No such action for this actor.
        AlreadyDecided: The action is no longer pending.
        ConfirmationError: The action name is no longer registered.
        Exception: Whatever the handler raised; the action is marked failed first.
    """
    row = pending_actions.get(session, action_id)
    if row is None or row.actor != expected_actor:
        raise UnknownAction()
    if not pending_actions.claim(session, action_id):
        raise AlreadyDecided(row.status)
    spec = registry.get(row.action)
    if spec is None:
        pending_actions.fail(session, action_id, "action no longer registered")
        raise ConfirmationError("unknown_action", f"Action '{row.action}' is no longer available.")
    parameters = json.loads(row.parameters_json)
    params = spec.params.model_validate(parameters)
    exec_ctx = dataclasses.replace(ctx, idempotency_key=idempotency_key or action_id)
    try:
        result = spec.handler(exec_ctx, params)
    except Exception as exc:
        pending_actions.fail(session, action_id, str(exc))
        session.commit()
        raise
    jsonable = to_jsonable(result)
    pending_actions.finish(session, action_id, jsonable)
    audit.record(
        session, channel=row.channel, actor=row.actor, prompt=row.prompt, action=row.action,
        parameters=parameters, result=jsonable, mutation=True,
    )
    return Execution(action=row.action, parameters=parameters, summary=row.summary, result=jsonable)
```

- [ ] **Step 5: Implement `app/agent/prompts.py` and `app/agent/narrator.py`**

`app/agent/prompts.py`:

```python
"""System prompts. The personality is defined once and shared by planner and narrator."""

from datetime import date

from app.agent.schema import Registry

PERSONALITY = (
    "You are Ledger, the payments assistant for a small business. Voice: precise, calm, a "
    "little dry. Speak in dollars like $1,200.00, never in cents. Never invent a number: every "
    "figure you state must come from an observation you were given. Prefer one clear sentence "
    "to three hedged ones."
)

OWNER_NOTES = (
    "You serve the business owner. You may discuss any customer, total revenue, and comparisons "
    "between periods. Ids: payments pi_..., customers cus_..., invoices in_..., escalations esc_.... "
    "Before acting on a person's name, find their customer id; if several match, clarify. "
    "For 'last week' style questions state the dates you used."
)

CUSTOMER_NOTES = (
    "You serve one customer of the business, chatting on Telegram. You only have actions for "
    "their own account. Never speculate about other customers or the business's finances; if "
    "asked, say you can only help with their own invoices. Keep replies to one or two short "
    "sentences. Do not state invoice amounts in replies; the customer can tap to view them."
)

PROTOCOL = (
    "Reply with exactly one JSON object and nothing else:\n"
    '{"reasoning": "why this step", "action": "<name>", "parameters": {...}}\n'
    "Rules: amounts in parameters are integer cents; dates are YYYY-MM-DD; call read actions "
    "to get facts before answering; mutations are shown to the user for confirmation after you "
    "propose them, so propose once you have the ids and amounts; use clarify when a request is "
    "ambiguous; use answer to finish. Each observation you receive is the typed result of your "
    "previous action."
)


def planner_system(*, registry: Registry, today: date, channel_notes: str) -> str:
    """The planner prompt: personality, protocol, today's date, the action catalog, channel notes."""
    return "\n\n".join([
        PERSONALITY,
        f"Today is {today.strftime('%A')}, {today.isoformat()}. Resolve relative dates against it.",
        PROTOCOL,
        "Available actions:\n" + registry.prompt_catalog(),
        channel_notes,
    ])


def summary_system() -> str:
    """The daily-summary narrator prompt."""
    return "\n\n".join([
        PERSONALITY,
        "Write the owner's daily summary from the JSON facts you are given: two or three sentences, "
        "human, not a list. Compare today with yesterday in words (well ahead, behind, about level). "
        "Mention declines and their reason if any, and the largest unpaid invoice by customer name. "
        "If there is no activity yet, say so plainly. Output plain text only.",
    ])


def result_system() -> str:
    """The post-confirmation narrator prompt."""
    return "\n\n".join([
        PERSONALITY,
        "An action the user approved has just executed. In one or two sentences, confirm what "
        "happened using only the JSON you are given. Include a URL if the result has one. Plain text.",
    ])
```

`app/agent/narrator.py`:

```python
"""Turn typed results into a sentence or two, where no planner is in the loop."""

import json
from typing import Any

from app.agent.events import to_jsonable
from app.agent.prompts import result_system, summary_system
from app.domain.summary import DailyFacts
from app.llm.base import ChatMessage, LLMBackend


def narrate_summary(llm: LLMBackend, facts: DailyFacts) -> str:
    """The daily summary paragraph, from facts computed in Python."""
    return llm.complete(
        system=summary_system(),
        messages=[ChatMessage(role="user", content=json.dumps(to_jsonable(facts)))],
        max_tokens=400,
    ).strip()


def narrate_result(llm: LLMBackend, *, action: str, summary: str, result: Any) -> str:
    """Confirm an executed action, anchored to the summary the user approved."""
    payload = {"action": action, "approved_summary": summary, "result": to_jsonable(result)}
    return llm.complete(
        system=result_system(),
        messages=[ChatMessage(role="user", content=json.dumps(payload))],
        max_tokens=300,
    ).strip()
```

- [ ] **Step 6: Run tests and lint**

Run: `uv run pytest tests/test_confirm.py tests/test_narrator.py tests/test_db.py -q && uv run ruff check .`
Expected: 11 passed; ruff clean.

- [ ] **Step 7: Commit**

```bash
git add app/agent/confirm.py app/agent/prompts.py app/agent/narrator.py app/db/pending_actions.py tests/test_confirm.py tests/test_narrator.py
git commit -m "feat(agent): execute stored confirmations without a model; prompts and narrator"
```

### Task 10: Owner actions, owner registry, and the escalation-approval service

**Files:**
- Create: `app/actions/__init__.py`, `app/actions/context.py`, `app/actions/owner_reads.py`, `app/actions/owner_mutations.py`, `app/actions/owner_registry.py`, `app/services/__init__.py`, `app/services/escalations.py`
- Test: `tests/test_owner_actions.py`

**Interfaces:**
- Consumes: `StripeGateway`, `CustomerScopedGateway`, domain models, `format_usd`, `build_daily_facts`, `date_range_window`, `period_totals`, `escalations`/`bindings` repositories, `ActionSpec`, `Proposal`, `Registry`, `ActionError`.
- Produces: `Notifier` Protocol — `(telegram_id: int, text: str, url: str | None) -> bool`, True when delivered; `OwnerContext(gateway, session, now, notify, idempotency_key=None)`; `CustomerContext(gateway, session, telegram_id, customer_name, now, idempotency_key=None)` (used by Task 11); `build_owner_registry() -> Registry` with actions `summarize_day, query_payments, find_customer, list_invoices, create_invoice, refund_payment, create_payment_link, list_escalations, approve_escalation`; `EscalationNotFound(LookupError)`, `ApprovalOutcome(escalation_id, customer_name, amount_cents, invoice_id, hosted_url, notified, already_approved)`, `approve_and_notify(session, escalation_id, *, gateway, notify, now) -> ApprovalOutcome`.

- [ ] **Step 1: Write the failing tests**

`tests/test_owner_actions.py`:

```python
"""Owner actions resolve proposals with concrete details and execute with the injected key."""

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import Engine

from app.actions.context import OwnerContext
from app.actions.owner_mutations import (
    CreateInvoiceParams, RefundParams, ApproveEscalationParams,
    describe_create_invoice, describe_refund, refund_payment, approve_escalation, describe_approve_escalation,
)
from app.actions.owner_reads import FindCustomerParams, QueryPaymentsParams, find_customer, query_payments
from app.actions.owner_registry import build_owner_registry
from app.agent.executor import ActionError
from app.db import escalations
from app.db.engine import session_scope
from tests.fakes.stripe_fake import FakeStripeGateway

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)


@pytest.fixture
def account() -> FakeStripeGateway:
    """Maya paid $90 today, Acme paid $50 last week, one Acme invoice is open."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_payment("pi_maya", "cus_maya", 9000, occurred_at=NOW - timedelta(hours=1))
    fake.add_payment("pi_acme", "cus_acme", 5000, occurred_at=NOW - timedelta(days=6))
    fake.add_invoice("in_acme", "cus_acme", 120000)
    return fake


def test_refund_describe_names_customer_amount_and_date(engine: Engine, account: FakeStripeGateway) -> None:
    """The confirmation card shows resolved facts, not ids."""
    with session_scope(engine) as session:
        ctx = OwnerContext(gateway=account, session=session, now=NOW, notify=lambda *_: True)
        proposal = describe_refund(ctx, RefundParams(payment_id="pi_maya", amount_cents=4500))
        assert proposal.summary == "Refund $45.00 to Maya Chen — $90.00 payment from Sep 01"
        with pytest.raises(ActionError, match="refundable"):
            describe_refund(ctx, RefundParams(payment_id="pi_maya", amount_cents=999900))


def test_refund_executes_with_the_context_idempotency_key(engine: Engine, account: FakeStripeGateway) -> None:
    """The key injected by execute_pending reaches Stripe; None means refund the remainder."""
    with session_scope(engine) as session:
        ctx = OwnerContext(gateway=account, session=session, now=NOW, notify=lambda *_: True, idempotency_key="act_x")
        result = refund_payment(ctx, RefundParams(payment_id="pi_maya"))
    assert result["amount_cents"] == 9000
    assert account.calls[-1] == ("refund", {"payment_id": "pi_maya", "amount_cents": None, "idempotency_key": "act_x"})


def test_create_invoice_rejects_past_due_dates(engine: Engine, account: FakeStripeGateway) -> None:
    """Stripe would reject it later with a worse message; catch it at proposal time."""
    with session_scope(engine) as session:
        ctx = OwnerContext(gateway=account, session=session, now=NOW, notify=lambda *_: True)
        params = CreateInvoiceParams(customer_id="cus_acme", amount_cents=25000, description="Consulting", due_date=date(2026, 8, 1))
        with pytest.raises(ActionError, match="future"):
            describe_create_invoice(ctx, params)
        ok = describe_create_invoice(ctx, CreateInvoiceParams(customer_id="cus_acme", amount_cents=25000, description="Consulting", due_date=date(2026, 9, 4)))
        assert ok.summary == "Create a $250.00 invoice for Acme Corp due Fri Sep 04, 2026 — Consulting"


def test_query_payments_filters_and_totals(engine: Engine, account: FakeStripeGateway) -> None:
    """Totals are computed in Python so the planner never adds numbers itself."""
    with session_scope(engine) as session:
        ctx = OwnerContext(gateway=account, session=session, now=NOW, notify=lambda *_: True)
        today = query_payments(ctx, QueryPaymentsParams(start_date=date(2026, 9, 1), end_date=date(2026, 9, 1)))
        assert today["succeeded_count"] == 1 and today["succeeded_total_cents"] == 9000
        maya = query_payments(ctx, QueryPaymentsParams(customer_id="cus_maya"))
        assert [p["id"] for p in maya["payments"]] == ["pi_maya"]


def test_find_customer_is_case_insensitive_substring(engine: Engine, account: FakeStripeGateway) -> None:
    """"maya" finds Maya Chen; the planner clarifies if several match."""
    with session_scope(engine) as session:
        ctx = OwnerContext(gateway=account, session=session, now=NOW, notify=lambda *_: True)
        assert [c["id"] for c in find_customer(ctx, FindCustomerParams(query="maya"))["matches"]] == ["cus_maya"]


def test_approve_escalation_notifies_once_with_the_hosted_url(engine: Engine, account: FakeStripeGateway) -> None:
    """Approval sends the customer a payment link; a repeat approval sends nothing."""
    sent: list[tuple[int, str, str | None]] = []
    with session_scope(engine) as session:
        esc = escalations.file(session, telegram_id=7, customer_id="cus_acme", customer_name="Acme Corp",
                               invoice_id="in_acme", amount_cents=120000, reason="ceiling", now=NOW.replace(tzinfo=None))
        esc_id = esc.id
    with session_scope(engine) as session:
        ctx = OwnerContext(gateway=account, session=session, now=NOW, notify=lambda tid, text, url: (sent.append((tid, text, url)), True)[1])
        assert "Acme Corp" in describe_approve_escalation(ctx, ApproveEscalationParams(escalation_id=esc_id)).summary  # type: ignore[arg-type]
        first = approve_escalation(ctx, ApproveEscalationParams(escalation_id=esc_id))
        second = approve_escalation(ctx, ApproveEscalationParams(escalation_id=esc_id))
    assert first["notified"] is True and first["hosted_url"] == "https://invoice.example/in_acme"
    assert second["already_approved"] is True
    assert len(sent) == 1
    assert sent[0][0] == 7 and sent[0][2] == "https://invoice.example/in_acme"


def test_owner_registry_matches_the_design() -> None:
    """The action names are the spec's table, with refund_payment for refund_charge."""
    assert build_owner_registry().names() == [
        "summarize_day", "query_payments", "find_customer", "list_invoices", "create_invoice",
        "refund_payment", "create_payment_link", "list_escalations", "approve_escalation",
    ]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_owner_actions.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.actions'`.

- [ ] **Step 3: Implement contexts and the escalation service**

`app/actions/__init__.py`: `"""Action handlers, one registry per channel."""`
`app/services/__init__.py`: `"""Operations shared by more than one entrypoint."""`

`app/actions/context.py`:

```python
"""What handlers receive. One context type per channel; both carry `idempotency_key`."""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from sqlalchemy.orm import Session

from app.stripe_.customer_client import CustomerScopedGateway
from app.stripe_.gateway import StripeGateway


class Notifier(Protocol):
    """Sends a Telegram message with an optional URL button; True when delivered."""

    def __call__(self, telegram_id: int, text: str, url: str | None) -> bool:
        """Deliver one message to one customer."""
        ...


@dataclass
class OwnerContext:
    """Full-account access for the owner's web assistant."""

    gateway: StripeGateway
    session: Session
    now: datetime
    notify: Notifier
    idempotency_key: str | None = None


@dataclass
class CustomerContext:
    """Access bound to one customer. The gateway cannot be pointed elsewhere."""

    gateway: CustomerScopedGateway
    session: Session
    telegram_id: int
    customer_name: str
    now: datetime
    idempotency_key: str | None = None
```

`app/services/escalations.py`:

```python
"""Owner approval of an escalation: mark it, then hand the customer a payment link.

Shared by the chat action `approve_escalation` and `POST /api/escalations/{id}/approve`.
"""

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.orm import Session

from app.actions.context import Notifier
from app.db import escalations
from app.stripe_.gateway import StripeGateway


class EscalationNotFound(LookupError):
    """No escalation with that id."""


@dataclass(frozen=True)
class ApprovalOutcome:
    """What happened, in a shape both the chat narrator and the REST route can return."""

    escalation_id: str
    customer_name: str
    amount_cents: int
    invoice_id: str | None
    hosted_url: str | None
    notified: bool
    already_approved: bool


APPROVED_TEXT = (
    "Good news — the business owner approved your request. Tap below to pay securely on Stripe."
)
APPROVED_TEXT_NO_LINK = "The business owner has approved your request and will follow up directly."


def approve_and_notify(
    session: Session, escalation_id: str, *, gateway: StripeGateway, notify: Notifier, now: datetime
) -> ApprovalOutcome:
    """Approve once and notify the customer on Telegram.

    A second approval is a no-op (`already_approved=True`) so a double-click
    or a chat-plus-panel race never messages the customer twice.

    Raises:
        EscalationNotFound: Unknown id.
    """
    row = escalations.get(session, escalation_id)
    if row is None:
        raise EscalationNotFound(escalation_id)
    approved = escalations.mark_approved(session, escalation_id, now.replace(tzinfo=None))
    if approved is None:
        return ApprovalOutcome(row.id, row.customer_name, row.amount_cents, row.invoice_id, None, False, True)
    hosted_url = gateway.get_invoice(row.invoice_id).hosted_url if row.invoice_id else None
    text = APPROVED_TEXT if hosted_url else APPROVED_TEXT_NO_LINK
    delivered = notify(row.telegram_id, text, hosted_url)
    return ApprovalOutcome(row.id, row.customer_name, row.amount_cents, row.invoice_id, hosted_url, delivered, False)
```

- [ ] **Step 4: Implement owner reads**

`app/actions/owner_reads.py`:

```python
"""Read-only owner actions. Every number returned is computed here, not by the model."""

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field

from app.actions.context import OwnerContext
from app.agent.events import to_jsonable
from app.db import escalations
from app.domain.models import Invoice, Payment
from app.domain.periods import date_range_window
from app.domain.summary import DailyFacts, build_daily_facts, period_totals


class NoParams(BaseModel):
    """For actions that take nothing."""


class QueryPaymentsParams(BaseModel):
    """Filters for a payment query; all optional."""

    start_date: date | None = Field(None, description="First day, inclusive")
    end_date: date | None = Field(None, description="Last day, inclusive")
    customer_id: str | None = Field(None, description="cus_... to restrict to one customer")
    status: Literal["succeeded", "failed", "refunded", "partially_refunded"] | None = None
    limit: int = Field(20, ge=1, le=100, description="Max payments to list (totals cover all matches)")


class FindCustomerParams(BaseModel):
    """Free-text customer lookup."""

    query: str = Field(..., description="Part of a name, email, or a cus_ id")


class ListInvoicesParams(BaseModel):
    """Invoice filters."""

    customer_id: str | None = None
    status: Literal["draft", "open", "paid", "void", "uncollectible"] | None = None


def _payment_row(p: Payment) -> dict[str, Any]:
    """The fields the planner needs to reason and to reference a payment later."""
    return {
        "id": p.id, "customer_id": p.customer_id, "customer_name": p.customer_name,
        "amount_cents": p.amount_cents, "amount_refunded_cents": p.amount_refunded_cents,
        "status": p.status, "failure_reason": p.failure_reason, "description": p.description,
        "occurred_at": p.occurred_at.isoformat(),
    }


def _invoice_row(i: Invoice) -> dict[str, Any]:
    """Invoice fields for the planner and the result cards."""
    return {
        "id": i.id, "number": i.number, "customer_id": i.customer_id, "customer_name": i.customer_name,
        "total_cents": i.total_cents, "amount_remaining_cents": i.amount_remaining_cents,
        "status": i.status, "due_date": i.due_at.date().isoformat() if i.due_at else None,
        "hosted_url": i.hosted_url, "description": i.description,
    }


def summarize_day(ctx: OwnerContext, _params: NoParams) -> DailyFacts:
    """Today's facts versus yesterday, plus open invoices."""
    return build_daily_facts(ctx.gateway.list_payments(), ctx.gateway.list_invoices(status="open"), ctx.now)


def query_payments(ctx: OwnerContext, params: QueryPaymentsParams) -> dict[str, Any]:
    """Payments matching the filters, newest first, with totals over every match."""
    payments = ctx.gateway.list_payments()
    if params.customer_id:
        payments = [p for p in payments if p.customer_id == params.customer_id]
    if params.status:
        payments = [p for p in payments if p.status == params.status]
    label = "all time"
    if params.start_date or params.end_date:
        start = params.start_date or date(2000, 1, 1)
        end = params.end_date or ctx.now.date()
        window = date_range_window(start, end, ctx.now.tzinfo)
        payments = [p for p in payments if window.contains(p.occurred_at)]
        label = window.label
        totals = period_totals(payments, window)
    else:
        totals = None
    succeeded = [p for p in payments if p.status != "failed"]
    return {
        "period": label,
        "succeeded_count": totals.succeeded_count if totals else len(succeeded),
        "succeeded_total_cents": totals.succeeded_total_cents if totals else sum(p.amount_cents for p in succeeded),
        "refunded_total_cents": sum(p.amount_refunded_cents for p in succeeded),
        "declined_count": len([p for p in payments if p.status == "failed"]),
        "payments": [_payment_row(p) for p in payments[: params.limit]],
    }


def find_customer(ctx: OwnerContext, params: FindCustomerParams) -> dict[str, Any]:
    """Case-insensitive substring match over name, email, and id."""
    needle = params.query.strip().lower()
    matches = [
        c for c in ctx.gateway.list_customers()
        if needle in c.name.lower() or needle in (c.email or "").lower() or needle == c.id.lower()
    ]
    return {"matches": [to_jsonable(c) for c in matches], "count": len(matches)}


def list_invoices(ctx: OwnerContext, params: ListInvoicesParams) -> dict[str, Any]:
    """Invoices with optional customer/status filters."""
    invoices = ctx.gateway.list_invoices(customer_id=params.customer_id, status=params.status)
    return {"count": len(invoices), "invoices": [_invoice_row(i) for i in invoices]}


def list_escalations(ctx: OwnerContext, _params: NoParams) -> dict[str, Any]:
    """Pending customer requests awaiting the owner."""
    rows = escalations.pending(ctx.session)
    return {
        "count": len(rows),
        "escalations": [
            {"id": r.id, "customer_name": r.customer_name, "invoice_id": r.invoice_id,
             "amount_cents": r.amount_cents, "reason": r.reason, "created_at": r.created_at.isoformat()}
            for r in rows
        ],
    }
```

- [ ] **Step 5: Implement owner mutations and the registry**

`app/actions/owner_mutations.py`:

```python
"""Owner actions that change Stripe or approve an escalation.

Each has a `describe_*` that resolves ids into a sentence for the
confirmation card and validates what Stripe would otherwise reject later,
and a handler that executes with the injected idempotency key.
"""

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from app.actions.context import OwnerContext
from app.actions.owner_reads import _invoice_row
from app.agent.executor import ActionError
from app.agent.schema import Proposal
from app.domain.money import format_usd
from app.services.escalations import EscalationNotFound, approve_and_notify
from app.db import escalations


def _key(ctx: OwnerContext) -> str:
    """The idempotency key execute_pending injected; empty only in direct tests."""
    return ctx.idempotency_key or ""


class RefundParams(BaseModel):
    """Refund a payment fully or partially."""

    payment_id: str = Field(..., description="pi_... from query_payments")
    amount_cents: int | None = Field(None, gt=0, description="Omit to refund the remaining balance")


def describe_refund(ctx: OwnerContext, params: RefundParams) -> Proposal:
    """Resolve the payment and check the amount before asking for approval.

    Raises:
        ActionError: Not refundable, or more than the refundable balance.
    """
    payment = ctx.gateway.get_payment(params.payment_id)
    if payment.status == "failed" or payment.refundable_cents == 0:
        raise ActionError(f"{params.payment_id} has nothing refundable (status {payment.status}).")
    amount = payment.refundable_cents if params.amount_cents is None else params.amount_cents
    if amount > payment.refundable_cents:
        raise ActionError(
            f"Only {format_usd(payment.refundable_cents)} is refundable on {params.payment_id}."
        )
    who = payment.customer_name or "the customer"
    return Proposal(summary=(
        f"Refund {format_usd(amount)} to {who} — {format_usd(payment.amount_cents)} payment from "
        f"{payment.occurred_at:%b %d}"
    ))


def refund_payment(ctx: OwnerContext, params: RefundParams) -> dict[str, Any]:
    """Execute the refund."""
    payment = ctx.gateway.get_payment(params.payment_id)
    refund = ctx.gateway.refund(params.payment_id, params.amount_cents, idempotency_key=_key(ctx))
    return {
        "refund_id": refund.id, "payment_id": params.payment_id, "amount_cents": refund.amount_cents,
        "customer_name": payment.customer_name, "status": refund.status,
    }


class CreateInvoiceParams(BaseModel):
    """Create a send-by-email invoice with one line."""

    customer_id: str = Field(..., description="cus_... from find_customer")
    amount_cents: int = Field(..., gt=0)
    description: str = Field(..., min_length=1, description="Line item text")
    due_date: date = Field(..., description="YYYY-MM-DD, after today")


def describe_create_invoice(ctx: OwnerContext, params: CreateInvoiceParams) -> Proposal:
    """Resolve the customer name and check the due date.

    Raises:
        ActionError: Due date is today or earlier.
    """
    if params.due_date <= ctx.now.date():
        raise ActionError("The due date must be in the future.")
    customer = ctx.gateway.get_customer(params.customer_id)
    return Proposal(summary=(
        f"Create a {format_usd(params.amount_cents)} invoice for {customer.name} due "
        f"{params.due_date:%a %b %d, %Y} — {params.description}"
    ))


def create_invoice(ctx: OwnerContext, params: CreateInvoiceParams) -> dict[str, Any]:
    """Create and finalise the invoice."""
    invoice = ctx.gateway.create_invoice(
        customer_id=params.customer_id, amount_cents=params.amount_cents,
        description=params.description, due_date=params.due_date, idempotency_key=_key(ctx),
    )
    return _invoice_row(invoice)


class PaymentLinkParams(BaseModel):
    """A one-off Stripe payment link."""

    amount_cents: int = Field(..., gt=0)
    description: str = Field(..., min_length=1, description="What is being paid for")


def describe_payment_link(_ctx: OwnerContext, params: PaymentLinkParams) -> Proposal:
    """Nothing to resolve; state the amount and purpose."""
    return Proposal(summary=f"Create a payment link for {format_usd(params.amount_cents)} — {params.description}")


def create_payment_link(ctx: OwnerContext, params: PaymentLinkParams) -> dict[str, Any]:
    """Create the link."""
    url = ctx.gateway.create_payment_link(
        amount_cents=params.amount_cents, description=params.description, idempotency_key=_key(ctx)
    )
    return {"url": url, "amount_cents": params.amount_cents, "description": params.description}


class ApproveEscalationParams(BaseModel):
    """Approve a customer's escalated request."""

    escalation_id: str = Field(..., description="esc_... from list_escalations")


def describe_approve_escalation(ctx: OwnerContext, params: ApproveEscalationParams) -> Proposal:
    """Name the customer and amount being approved.

    Raises:
        ActionError: Unknown or already decided.
    """
    row = escalations.get(ctx.session, params.escalation_id)
    if row is None or row.status != "pending":
        raise ActionError(f"No pending escalation {params.escalation_id}.")
    return Proposal(summary=(
        f"Approve {row.customer_name}'s request to pay {format_usd(row.amount_cents)} and send them "
        "the payment link on Telegram"
    ))


def approve_escalation(ctx: OwnerContext, params: ApproveEscalationParams) -> dict[str, Any]:
    """Approve and notify via the shared service."""
    try:
        outcome = approve_and_notify(
            ctx.session, params.escalation_id, gateway=ctx.gateway, notify=ctx.notify, now=ctx.now
        )
    except EscalationNotFound as exc:
        raise ActionError(f"No escalation {params.escalation_id}.") from exc
    return outcome.__dict__.copy()
```

`app/actions/owner_registry.py`:

```python
"""The owner's action set, in the order the design lists them."""

from app.actions import owner_mutations as m
from app.actions import owner_reads as r
from app.agent.schema import ActionSpec, Registry


def build_owner_registry() -> Registry:
    """Everything the web assistant may do."""
    return Registry([
        ActionSpec("summarize_day", "Today's payment facts versus yesterday, plus open invoices", r.NoParams, r.summarize_day),
        ActionSpec("query_payments", "List payments with totals, filtered by dates, customer, or status", r.QueryPaymentsParams, r.query_payments),
        ActionSpec("find_customer", "Find customers by name, email, or id", r.FindCustomerParams, r.find_customer),
        ActionSpec("list_invoices", "List invoices, optionally by customer or status", r.ListInvoicesParams, r.list_invoices),
        ActionSpec("create_invoice", "Create and send an invoice (asks for confirmation)", m.CreateInvoiceParams, m.create_invoice, mutation=True, describe=m.describe_create_invoice),
        ActionSpec("refund_payment", "Refund a payment fully or partially (asks for confirmation)", m.RefundParams, m.refund_payment, mutation=True, describe=m.describe_refund),
        ActionSpec("create_payment_link", "Create a shareable payment link (asks for confirmation)", m.PaymentLinkParams, m.create_payment_link, mutation=True, describe=m.describe_payment_link),
        ActionSpec("list_escalations", "Customer requests waiting for the owner's approval", r.NoParams, r.list_escalations),
        ActionSpec("approve_escalation", "Approve an escalated payment and send the customer a link (asks for confirmation)", m.ApproveEscalationParams, m.approve_escalation, mutation=True, describe=m.describe_approve_escalation),
    ])
```

- [ ] **Step 6: Run tests and lint**

Run: `uv run pytest tests/test_owner_actions.py -q && uv run ruff check .`
Expected: 7 passed; ruff clean.

- [ ] **Step 7: Commit**

```bash
git add app/actions app/services tests/test_owner_actions.py
git commit -m "feat(actions): owner reads and confirmed mutations; escalation approval service"
```

### Task 11: Customer actions and the customer registry

**Files:**
- Create: `app/actions/customer.py`
- Modify: `app/agent/schema.py` (add `NoParams`), `app/actions/owner_reads.py` (import `NoParams` from `app.agent.schema` instead of defining it)
- Test: `tests/test_customer_actions.py`

**Interfaces:**
- Consumes: `CustomerContext` (Task 10), `CustomerScopedGateway` (Task 4), `TELEGRAM_PAYMENT_CEILING_CENTS` (Task 2), `escalations` repository (Task 6), `Proposal`, `ActionSpec`, `Registry`, `ActionError`.
- Produces: `NoParams` (moved to `app.agent.schema`), `PayInvoiceParams(invoice_id)`, `EscalateParams(reason)`, handlers `my_balance`, `my_invoices`, `pay_invoice`, `escalate_to_owner`, `describe_pay_invoice`, `CEILING_MESSAGE`, `build_customer_registry() -> Registry` with actions `my_balance, my_invoices, pay_invoice, escalate_to_owner`.
- **Invariant:** `pay_invoice` and `describe_pay_invoice` both call `_guard_ceiling` before any payment call. Above the ceiling, describe returns `Proposal(resolved=<escalation record>)` (no confirmation is offered) and the handler raises `ActionError` after filing the escalation. Observations returned by `my_balance`/`my_invoices` contain **no amount fields**.

- [ ] **Step 1: Move `NoParams` to `app/agent/schema.py`**

Add to `app/agent/schema.py` after `ClarifyParams`:

```python
class NoParams(BaseModel):
    """For actions that take nothing."""
```

In `app/actions/owner_reads.py` delete the local `NoParams` class and add `NoParams` to the import from `app.agent.schema` (`from app.agent.schema import NoParams`). Run `uv run pytest tests/test_owner_actions.py -q` — still 7 passed.

- [ ] **Step 2: Write the failing tests**

`tests/test_customer_actions.py`:

```python
"""The bot's guardrails are Python invariants: the ceiling, the scope, and amount-free replies."""

import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine

from app.actions.context import CustomerContext
from app.actions.customer import (
    PayInvoiceParams, build_customer_registry, describe_pay_invoice, my_invoices, pay_invoice,
)
from app.agent.executor import ActionError
from app.agent.schema import NoParams
from app.db import escalations
from app.db.engine import session_scope
from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS
from app.stripe_.customer_client import CustomerScopedGateway, NotYourInvoice
from tests.fakes.stripe_fake import FakeStripeGateway

NOW = datetime(2026, 9, 1, 15, 0, tzinfo=UTC)


@pytest.fixture
def account() -> FakeStripeGateway:
    """Acme has one invoice exactly at the ceiling and one just under; Maya has one."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_invoice("in_big", "cus_acme", TELEGRAM_PAYMENT_CEILING_CENTS)
    fake.add_invoice("in_small", "cus_acme", TELEGRAM_PAYMENT_CEILING_CENTS - 1)
    fake.add_invoice("in_maya", "cus_maya", 18000)
    return fake


def _acme(engine_session: object, fake: FakeStripeGateway) -> CustomerContext:
    """A context bound to Acme."""
    return CustomerContext(
        gateway=CustomerScopedGateway(fake, "cus_acme"), session=engine_session,  # type: ignore[arg-type]
        telegram_id=7, customer_name="Acme Corp", now=NOW,
    )


def test_ceiling_escalates_before_any_stripe_payment_call(engine: Engine, account: FakeStripeGateway) -> None:
    """At exactly $2,000 the bot files an escalation and never reaches invoices.pay."""
    with session_scope(engine) as session:
        ctx = _acme(session, account)
        proposal = describe_pay_invoice(ctx, PayInvoiceParams(invoice_id="in_big"))
        assert proposal.summary is None and proposal.resolved["escalated"] is True
        with pytest.raises(ActionError):
            pay_invoice(ctx, PayInvoiceParams(invoice_id="in_big"))
        assert len(escalations.pending(session)) == 1  # the second attempt reused the first
    assert not [c for c in account.calls if c[0] == "pay_invoice"]


def test_under_ceiling_confirms_with_amount_then_pays(engine: Engine, account: FakeStripeGateway) -> None:
    """Just under the ceiling is payable; the amount appears on the confirmation and nowhere else."""
    with session_scope(engine) as session:
        ctx = _acme(session, account)
        proposal = describe_pay_invoice(ctx, PayInvoiceParams(invoice_id="in_small"))
        assert proposal.summary == "Pay invoice IN_SMALL for $1,999.99 with your card on file"
        ctx.idempotency_key = "act_9"
        result = pay_invoice(ctx, PayInvoiceParams(invoice_id="in_small"))
    assert result["paid"] is True
    assert account.calls[-1] == ("pay_invoice", {"invoice_id": "in_small", "idempotency_key": "act_9"})


def test_another_customers_invoice_is_unreachable(engine: Engine, account: FakeStripeGateway) -> None:
    """A guessed invoice id belonging to Maya fails ownership before anything else."""
    with session_scope(engine) as session:
        with pytest.raises(NotYourInvoice):
            pay_invoice(_acme(session, account), PayInvoiceParams(invoice_id="in_maya"))


def test_customer_observations_carry_no_amounts(engine: Engine, account: FakeStripeGateway) -> None:
    """The planner cannot restate what it never sees."""
    with session_scope(engine) as session:
        result = json.dumps(my_invoices(_acme(session, account), NoParams()))
    assert "amount" not in result and "total" not in result and str(TELEGRAM_PAYMENT_CEILING_CENTS) not in result
    assert "view_url" in result


def test_customer_registry_has_no_customer_id_anywhere() -> None:
    """Structural: no customer action accepts a customer id, so no prompt can supply one."""
    registry = build_customer_registry()
    assert registry.names() == ["my_balance", "my_invoices", "pay_invoice", "escalate_to_owner"]
    for spec in registry.specs():
        assert "customer_id" not in spec.params.model_fields, spec.name
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_customer_actions.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.actions.customer'`.

- [ ] **Step 4: Implement `app/actions/customer.py`**

```python
"""Everything the customer bot can do, scoped to the bound customer.

No action here takes a customer id; the gateway in the context is already
bound. The $2,000 ceiling is enforced in `_guard_ceiling`, called by both
the proposal and the execution path, before any payment call.
"""

from typing import Any

from pydantic import BaseModel, Field

from app.actions.context import CustomerContext
from app.agent.executor import ActionError
from app.agent.schema import ActionSpec, NoParams, Proposal, Registry
from app.db import escalations
from app.domain.models import Invoice
from app.domain.money import format_usd
from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS

CEILING_MESSAGE = (
    "This invoice is above the amount I can take here, so I've asked the business owner to "
    "approve it. You'll get a payment link in this chat once they do."
)


def _invoice_row(invoice: Invoice) -> dict[str, Any]:
    """An invoice as the customer planner sees it: no amounts, a link to view them."""
    return {
        "invoice_id": invoice.id,
        "number": invoice.number,
        "status": invoice.status,
        "due_date": invoice.due_at.date().isoformat() if invoice.due_at else None,
        "description": invoice.description,
        "view_url": invoice.hosted_url,
    }


def my_balance(ctx: CustomerContext, _params: NoParams) -> dict[str, Any]:
    """How many invoices are unpaid and when the next is due."""
    unpaid = [i for i in ctx.gateway.my_invoices(status="open") if i.amount_remaining_cents > 0]
    due_dates = sorted(i.due_at for i in unpaid if i.due_at)
    return {
        "unpaid_count": len(unpaid),
        "overdue_count": len([i for i in unpaid if i.due_at and i.due_at < ctx.now]),
        "next_due_date": due_dates[0].date().isoformat() if due_dates else None,
        "invoices": [_invoice_row(i) for i in unpaid],
    }


def my_invoices(ctx: CustomerContext, _params: NoParams) -> dict[str, Any]:
    """Every invoice on the account, open first."""
    invoices = sorted(ctx.gateway.my_invoices(), key=lambda i: (i.status != "open", i.occurred_at), reverse=False)
    return {"count": len(invoices), "invoices": [_invoice_row(i) for i in invoices]}


class PayInvoiceParams(BaseModel):
    """Pay one of the customer's own invoices."""

    invoice_id: str = Field(..., description="invoice_id from my_balance or my_invoices")


def _payable(ctx: CustomerContext, invoice_id: str) -> Invoice:
    """Resolve an invoice the customer owns and can still pay.

    Raises:
        ActionError: Not open, or nothing remaining.
        NotYourInvoice: Propagates from the scoped gateway.
    """
    invoice = ctx.gateway.my_invoice(invoice_id)
    if invoice.status != "open" or invoice.amount_remaining_cents <= 0:
        raise ActionError(f"Invoice {invoice.number or invoice.id} is {invoice.status}; nothing to pay.")
    return invoice


def _guard_ceiling(ctx: CustomerContext, invoice: Invoice) -> dict[str, Any] | None:
    """File an escalation and return it when the invoice is at or above the ceiling.

    Reuses a pending escalation for the same invoice so repeated attempts do
    not pile up on the owner's panel. Returns None when the invoice is payable.
    """
    if invoice.amount_remaining_cents < TELEGRAM_PAYMENT_CEILING_CENTS:
        return None
    existing = next(
        (e for e in escalations.pending(ctx.session)
         if e.telegram_id == ctx.telegram_id and e.invoice_id == invoice.id),
        None,
    )
    row = existing or escalations.file(
        ctx.session, telegram_id=ctx.telegram_id, customer_id=ctx.gateway.customer_id,
        customer_name=ctx.customer_name, invoice_id=invoice.id,
        amount_cents=invoice.amount_remaining_cents, reason="Payment at or above the bot's limit",
        now=ctx.now.replace(tzinfo=None),
    )
    return {"escalated": True, "escalation_id": row.id, "message": CEILING_MESSAGE}


def describe_pay_invoice(ctx: CustomerContext, params: PayInvoiceParams) -> Proposal:
    """Either a confirmation with the amount, or an escalation instead of a confirmation."""
    invoice = _payable(ctx, params.invoice_id)
    escalated = _guard_ceiling(ctx, invoice)
    if escalated:
        return Proposal(resolved=escalated)
    return Proposal(summary=(
        f"Pay invoice {invoice.number or invoice.id} for {format_usd(invoice.amount_remaining_cents)} "
        "with your card on file"
    ))


def pay_invoice(ctx: CustomerContext, params: PayInvoiceParams) -> dict[str, Any]:
    """Charge the card on file. The ceiling is re-checked here; this path is what approval runs.

    Raises:
        ActionError: At or above the ceiling (after filing the escalation).
    """
    invoice = _payable(ctx, params.invoice_id)
    if _guard_ceiling(ctx, invoice):
        raise ActionError(CEILING_MESSAGE)
    paid = ctx.gateway.pay_my_invoice(params.invoice_id, idempotency_key=ctx.idempotency_key or "")
    return {
        "paid": True, "invoice_id": paid.id, "number": paid.number,
        "amount_cents": paid.total_cents, "receipt_url": paid.hosted_url,
    }


class EscalateParams(BaseModel):
    """Hand something the bot cannot do to the owner."""

    reason: str = Field(..., min_length=1, description="What the customer is asking for, in their words")


def escalate_to_owner(ctx: CustomerContext, params: EscalateParams) -> dict[str, Any]:
    """File a general escalation (disputes, questions, anything outside paying invoices)."""
    row = escalations.file(
        ctx.session, telegram_id=ctx.telegram_id, customer_id=ctx.gateway.customer_id,
        customer_name=ctx.customer_name, invoice_id=None, amount_cents=0, reason=params.reason,
        now=ctx.now.replace(tzinfo=None),
    )
    return {"escalated": True, "escalation_id": row.id,
            "message": "I've passed this to the business owner; they'll follow up here."}


def build_customer_registry() -> Registry:
    """The bot's action set. Note what is absent: any way to name another customer."""
    return Registry([
        ActionSpec("my_balance", "How many invoices the customer has unpaid and when the next is due", NoParams, my_balance),
        ActionSpec("my_invoices", "The customer's invoices with links to view each one", NoParams, my_invoices),
        ActionSpec("pay_invoice", "Pay one of the customer's open invoices with their card on file (asks for confirmation)", PayInvoiceParams, pay_invoice, mutation=True, describe=describe_pay_invoice),
        ActionSpec("escalate_to_owner", "Hand a request the bot cannot fulfil to the business owner", EscalateParams, escalate_to_owner),
    ])
```

- [ ] **Step 5: Run tests and lint**

Run: `uv run pytest tests/test_customer_actions.py tests/test_owner_actions.py -q && uv run ruff check .`
Expected: 12 passed; ruff clean.

- [ ] **Step 6: Commit**

```bash
git add app/actions/customer.py app/actions/owner_reads.py app/agent/schema.py tests/test_customer_actions.py
git commit -m "feat(actions): customer registry with the ceiling as an executor invariant"
```

### Task 12: FastAPI — SSE turns, confirmation, summary, escalations, bindings, audit

**Files:**
- Create: `app/api/__init__.py`, `app/api/errors.py`, `app/api/auth.py`, `app/api/sse.py`, `app/api/app.py`, `app/api/conversations.py`, `app/api/summary.py`, `app/api/escalations.py`, `app/api/customers.py`, `app/api/audit.py`, `app/main.py`
- Modify: `app/actions/context.py` (add `no_notifier`)
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: everything from Tasks 1–11.
- Produces: `Services(settings, gateway, llm, engine, notify)`, `create_app(services) -> FastAPI`, `ApiError(status, code, message, hint="")`, `require_owner` dependency, `sse_response(events) -> EventSourceResponse`, `no_notifier` (returns False; replaced by the Telegram notifier in Task 13), `app.main:app` for uvicorn and `build_services()`.
- Routes (all under `/api`, all requiring `Authorization: Bearer <OWNER_API_TOKEN>`): `POST /conversations/{id}/messages` (body `{text}`) → SSE; `POST /conversations/{id}/confirm` (body `{action_id}`, optional `Idempotency-Key` header) → SSE; `POST /conversations/{id}/cancel` (body `{action_id}`) → JSON; `GET /conversations/{id}` → `{conversation_id, messages, pending}`; `GET /summary/today?narrate=true|false` → `{facts, text}`; `GET /escalations`; `POST /escalations/{id}/approve`; `DELETE /customers/{id}/telegram-binding` → `{revoked}`; `GET /audit?limit=`.
- Error envelope everywhere: `{"error": {"code", "message", "hint"}}`. Inside an SSE stream, failures are `event: error` with the same fields.
- SQLite locking rule: hooks `commit()` after each write so the write lock is never held across an LLM call (the bot process shares the file).

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:

```python
"""HTTP contract: auth with a hint, typed SSE events, stored-action confirmation, resources."""

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from app.api.app import Services, create_app
from app.db import escalations
from app.db.engine import session_scope
from app.settings import Settings
from tests.fakes.llm_fake import ScriptedLLM
from tests.fakes.stripe_fake import FakeStripeGateway

AUTH = {"Authorization": "Bearer test-token"}
NOW = datetime.now(UTC)


def _step(action: str, **parameters: Any) -> str:
    """A planner step as the LLM would emit it."""
    return json.dumps({"reasoning": "r", "action": action, "parameters": parameters})


def _events(response: Any) -> list[tuple[str, dict[str, Any]]]:
    """Parse an SSE body into (event, data) pairs."""
    out: list[tuple[str, dict[str, Any]]] = []
    event = ""
    for line in response.iter_lines():
        if line.startswith("event:"):
            event = line.split(":", 1)[1].strip()
        elif line.startswith("data:"):
            out.append((event, json.loads(line.split(":", 1)[1].strip())))
    return out


@pytest.fixture
def world(engine: Engine) -> Iterator[tuple[TestClient, FakeStripeGateway, ScriptedLLM, list[Any]]]:
    """A test app over fakes: Maya paid $90 today; the LLM script is filled per test."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_maya", "Maya Chen")
    fake.add_customer("cus_acme", "Acme Corp")
    fake.add_payment("pi_1", "cus_maya", 9000, occurred_at=NOW - timedelta(minutes=5))
    fake.add_invoice("in_1", "cus_acme", 120000)
    llm = ScriptedLLM([])
    sent: list[Any] = []
    services = Services(
        settings=Settings(_env_file=None, owner_api_token="test-token", stripe_secret_key="sk_test_x"),
        gateway=fake, llm=llm, engine=engine,
        notify=lambda tid, text, url: (sent.append((tid, text, url)), True)[1],
    )
    with TestClient(create_app(services)) as client:
        yield client, fake, llm, sent


def test_missing_token_returns_envelope_with_hint(world: Any) -> None:
    """401 tells the reviewer exactly which header and variable to use."""
    client, *_ = world
    response = client.get("/api/summary/today")
    assert response.status_code == 401
    body = response.json()["error"]
    assert body["code"] == "unauthorized" and "OWNER_API_TOKEN" in body["hint"]


def test_message_turn_streams_typed_events_and_persists_history(world: Any) -> None:
    """planning → action → observation → answer, then the transcript is retrievable."""
    client, _fake, llm, _ = world
    llm._responses.extend([_step("find_customer", query="maya"), _step("answer", text="Found Maya Chen.")])
    with client.stream("POST", "/api/conversations/c1/messages", json={"text": "who is maya"}, headers=AUTH) as r:
        assert r.status_code == 200
        events = _events(r)
    assert [e for e, _ in events] == ["planning", "action", "observation", "planning", "answer"]
    assert events[1][1] == {"name": "find_customer", "args": {"query": "maya"}}
    history = client.get("/api/conversations/c1", headers=AUTH).json()
    assert [m["role"] for m in history["messages"]] == ["user", "assistant"]
    assert history["pending"] is None


def test_confirmation_executes_the_stored_action_once_with_the_header_key(world: Any) -> None:
    """Approve runs exactly the proposal; the header becomes Stripe's idempotency key; repeats 409."""
    client, fake, llm, _ = world
    llm._responses.extend([_step("refund_payment", payment_id="pi_1", amount_cents=4500), "Refunded $45.00."])
    with client.stream("POST", "/api/conversations/c1/messages", json={"text": "refund maya 45"}, headers=AUTH) as r:
        events = _events(r)
    assert events[-1][0] == "confirmation"
    action_id = events[-1][1]["action_id"]
    assert events[-1][1]["summary"].startswith("Refund $45.00 to Maya Chen")
    assert client.get("/api/conversations/c1", headers=AUTH).json()["pending"]["action_id"] == action_id
    with client.stream("POST", "/api/conversations/c1/confirm", json={"action_id": action_id},
                       headers={**AUTH, "Idempotency-Key": "idem-1"}) as r:
        confirmed = _events(r)
    assert [e for e, _ in confirmed] == ["action", "observation", "answer"]
    assert confirmed[-1][1]["text"] == "Refunded $45.00."
    assert [c for c in fake.calls if c[0] == "refund"] == [
        ("refund", {"payment_id": "pi_1", "amount_cents": 4500, "idempotency_key": "idem-1"})
    ]
    again = client.post("/api/conversations/c1/confirm", json={"action_id": action_id}, headers=AUTH)
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_decided"
    assert len([c for c in fake.calls if c[0] == "refund"]) == 1
    audit = client.get("/api/audit", headers=AUTH).json()
    assert audit[0]["action"] == "refund_payment" and audit[0]["mutation"] is True


def test_cancel_dismisses_a_pending_action(world: Any) -> None:
    """Cancel is a resource change: the action can no longer be confirmed."""
    client, _fake, llm, _ = world
    llm._responses.append(_step("create_payment_link", amount_cents=5000, description="Deposit"))
    with client.stream("POST", "/api/conversations/c2/messages", json={"text": "link for 50"}, headers=AUTH) as r:
        action_id = _events(r)[-1][1]["action_id"]
    assert client.post("/api/conversations/c2/cancel", json={"action_id": action_id}, headers=AUTH).json() == {"status": "cancelled"}
    assert client.post("/api/conversations/c2/confirm", json={"action_id": action_id}, headers=AUTH).status_code == 409


def test_summary_facts_without_narration(world: Any) -> None:
    """narrate=false returns facts only, for the live rail, without an LLM call."""
    client, _fake, llm, _ = world
    body = client.get("/api/summary/today?narrate=false", headers=AUTH).json()
    assert body["text"] is None and body["facts"]["today"]["succeeded_total_cents"] == 9000
    assert llm.calls == []
    llm._responses.append("You took $90.00 today.")
    assert client.get("/api/summary/today", headers=AUTH).json()["text"] == "You took $90.00 today."


def test_escalation_approval_and_binding_revocation(world: Any, engine: Engine) -> None:
    """The bonus loop's owner side and the owner-side revoke, as plain resources."""
    client, _fake, _llm, sent = world
    with session_scope(engine) as session:
        esc_id = escalations.file(session, telegram_id=7, customer_id="cus_acme", customer_name="Acme Corp",
                                  invoice_id="in_1", amount_cents=120000, reason="ceiling", now=datetime.utcnow()).id
    assert [e["id"] for e in client.get("/api/escalations", headers=AUTH).json()] == [esc_id]
    approved = client.post(f"/api/escalations/{esc_id}/approve", headers=AUTH).json()
    assert approved["notified"] is True and sent[0][2] == "https://invoice.example/in_1"
    assert client.get("/api/escalations", headers=AUTH).json() == []
    assert client.post("/api/escalations/esc_nope/approve", headers=AUTH).status_code == 404
    assert client.delete("/api/customers/cus_acme/telegram-binding", headers=AUTH).json() == {"revoked": 0}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.api'`.

- [ ] **Step 3: Implement errors, auth, SSE, and the app factory**

Add to `app/actions/context.py`:

```python
def no_notifier(_telegram_id: int, _text: str, _url: str | None) -> bool:
    """Notifier used when no Telegram token is configured: nothing is sent."""
    return False
```

`app/api/__init__.py`: `"""HTTP surface for the owner web app."""`

`app/api/errors.py`:

```python
"""One error envelope for every failure: {error: {code, message, hint}}."""

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.agent.confirm import ConfirmationError
from app.llm.base import LLMError
from app.services.escalations import EscalationNotFound
from app.stripe_.gateway import NotFound, StripeGatewayError


class ApiError(Exception):
    """A deliberate HTTP failure with a stable code and a hint."""

    def __init__(self, status: int, code: str, message: str, hint: str = "") -> None:
        """Store status, code, message, hint."""
        super().__init__(message)
        self.status, self.code, self.hint = status, code, hint


def envelope(code: str, message: str, hint: str = "") -> dict[str, dict[str, str]]:
    """The wire shape."""
    return {"error": {"code": code, "message": message, "hint": hint}}


def install_error_handlers(app: FastAPI) -> None:
    """Map every known exception family onto the envelope."""

    @app.exception_handler(ApiError)
    async def _api(_r: Request, exc: ApiError) -> JSONResponse:
        """Deliberate errors."""
        return JSONResponse(exc.status, envelope(exc.code, str(exc), exc.hint))

    @app.exception_handler(ConfirmationError)
    async def _confirm(_r: Request, exc: ConfirmationError) -> JSONResponse:
        """Expired/foreign ids are 404; decided ones are 409."""
        status = 404 if exc.code == "unknown_action" else 409
        return JSONResponse(status, envelope(exc.code, str(exc)))

    @app.exception_handler(EscalationNotFound)
    async def _esc(_r: Request, exc: EscalationNotFound) -> JSONResponse:
        """Unknown escalation."""
        return JSONResponse(404, envelope("not_found", f"No escalation {exc}."))

    @app.exception_handler(StripeGatewayError)
    async def _stripe(_r: Request, exc: StripeGatewayError) -> JSONResponse:
        """Stripe failures carry the gateway's hint; missing objects are 404."""
        status = 404 if isinstance(exc, NotFound) else 502
        return JSONResponse(status, envelope("stripe_error", str(exc), exc.hint))

    @app.exception_handler(LLMError)
    async def _llm(_r: Request, exc: LLMError) -> JSONResponse:
        """Model failures."""
        return JSONResponse(502, envelope("llm_error", str(exc), exc.hint))

    @app.exception_handler(RequestValidationError)
    async def _validation(_r: Request, exc: RequestValidationError) -> JSONResponse:
        """Body/query validation in the same envelope."""
        return JSONResponse(422, envelope("invalid_request", str(exc.errors()[0]["msg"]), "Check the request body."))
```

`app/api/auth.py`:

```python
"""Single-owner bearer auth on every /api route."""

import secrets

from fastapi import Request

from app.api.errors import ApiError


def require_owner(request: Request) -> None:
    """Compare the bearer token to OWNER_API_TOKEN in constant time.

    Raises:
        ApiError: 401 with the header format and the variable name.
    """
    expected = request.app.state.services.settings.owner_api_token
    header = request.headers.get("Authorization", "")
    supplied = header.removeprefix("Bearer ").strip()
    if not header.startswith("Bearer ") or not secrets.compare_digest(supplied, expected):
        raise ApiError(
            401, "unauthorized", "Missing or invalid owner token.",
            hint="Send 'Authorization: Bearer <OWNER_API_TOKEN>' using the value in .env.",
        )
```

`app/api/sse.py`:

```python
"""Serialise agent events as Server-Sent Events."""

import json
from collections.abc import Iterator

from sse_starlette.sse import EventSourceResponse

from app.agent.events import AgentEvent


def sse_response(events: Iterator[AgentEvent]) -> EventSourceResponse:
    """Stream events as `event: <type>` / `data: <json>` frames. Sync iterators run in a threadpool."""
    def frames() -> Iterator[dict[str, str]]:
        """Convert each event into an SSE frame."""
        for event in events:
            yield {"event": event.type, "data": json.dumps(event.data)}
    return EventSourceResponse(frames())
```

`app/api/app.py`:

```python
"""Application factory. Dependencies are injected so tests run over fakes."""

from dataclasses import dataclass

from fastapi import FastAPI
from sqlalchemy import Engine

from app.actions.context import Notifier
from app.api import audit, conversations, customers, escalations, summary
from app.api.errors import install_error_handlers
from app.llm.base import LLMBackend
from app.settings import Settings
from app.stripe_.gateway import StripeGateway


@dataclass
class Services:
    """Everything the routes need, built once per process."""

    settings: Settings
    gateway: StripeGateway
    llm: LLMBackend
    engine: Engine
    notify: Notifier


def create_app(services: Services) -> FastAPI:
    """Assemble routers and error handlers around the given services."""
    app = FastAPI(title="AI payments assistant", docs_url="/api/docs", openapi_url="/api/openapi.json")
    app.state.services = services
    install_error_handlers(app)
    for router in (conversations.router, summary.router, escalations.router, customers.router, audit.router):
        app.include_router(router)
    return app
```

`app/main.py`:

```python
"""uvicorn entrypoint: `uvicorn app.main:app`."""

from app.actions.context import no_notifier
from app.api.app import Services, create_app
from app.db.engine import make_engine
from app.llm.factory import build_backend
from app.settings import load_settings
from app.stripe_.owner_client import StripeOwnerGateway


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
        gateway=StripeOwnerGateway(settings.stripe_secret_key),
        llm=build_backend(settings),
        engine=make_engine(settings.database_url),
        notify=no_notifier,
    )


app = create_app(build_services())
```

- [ ] **Step 4: Implement the routers**

`app/api/conversations.py`:

```python
"""Conversational routes: send a turn, confirm or cancel a proposal, read history."""

import json
from collections.abc import Iterator
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.actions.context import OwnerContext
from app.actions.owner_registry import build_owner_registry
from app.agent.confirm import ConfirmationError, UnknownAction, execute_pending
from app.agent.events import AgentEvent
from app.agent.loop import TurnHooks, run_turn
from app.agent.narrator import narrate_result
from app.agent.prompts import OWNER_NOTES, planner_system
from app.api.auth import require_owner
from app.api.sse import sse_response
from app.db import audit, conversations, pending_actions
from app.db.engine import session_scope
from app.domain.periods import local_timezone
from app.llm.base import ChatMessage, LLMError
from app.stripe_.gateway import StripeGatewayError

router = APIRouter(prefix="/api/conversations", dependencies=[Depends(require_owner)])
OWNER_REGISTRY = build_owner_registry()
CHANNEL, ACTOR = "web", "owner"


class MessageIn(BaseModel):
    """A user turn."""

    text: str = Field(..., min_length=1, max_length=2000)


class ActionRef(BaseModel):
    """Reference to a pending action."""

    action_id: str


def _ctx(request: Request, session: Session, idempotency_key: str | None = None) -> OwnerContext:
    """Owner context over the process services."""
    services = request.app.state.services
    return OwnerContext(
        gateway=services.gateway, session=session, now=datetime.now(local_timezone()),
        notify=services.notify, idempotency_key=idempotency_key,
    )


def _hooks(session: Session, conversation_id: str, prompt: str) -> TurnHooks:
    """DB-backed hooks that commit immediately so the SQLite write lock is not held across LLM calls."""
    def propose(spec: Any, params: Any, summary: str) -> str:
        """Store the proposal."""
        row = pending_actions.create(
            session, conversation_id=conversation_id, channel=CHANNEL, actor=ACTOR, action=spec.name,
            parameters=params.model_dump(mode="json"), summary=summary, prompt=prompt,
        )
        session.commit()
        return row.id

    def record(action: str, parameters: dict[str, Any], result: Any, mutation: bool) -> None:
        """Audit an executed read."""
        audit.record(session, channel=CHANNEL, actor=ACTOR, prompt=prompt, action=action,
                     parameters=parameters, result=result, mutation=mutation)
        session.commit()

    return TurnHooks(propose=propose, audit=record)


@router.post("/{conversation_id}/messages")
def post_message(conversation_id: str, body: MessageIn, request: Request) -> Any:
    """Run one agent turn and stream its events."""
    services = request.app.state.services

    def events() -> Iterator[AgentEvent]:
        """Persist the user turn, run the loop, persist the assistant's terminal message."""
        with session_scope(services.engine) as session:
            conversations.ensure(session, conversation_id, CHANNEL)
            history = [ChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
                       for m in conversations.history(session, conversation_id)]
            conversations.append(session, conversation_id, "user", body.text)
            session.commit()
            ctx = _ctx(request, session)
            system = planner_system(registry=OWNER_REGISTRY, today=ctx.now.date(), channel_notes=OWNER_NOTES)
            try:
                for event in run_turn(llm=services.llm, registry=OWNER_REGISTRY, ctx=ctx, system=system,
                                      history=history, prompt=body.text, hooks=_hooks(session, conversation_id, body.text)):
                    if event.type in ("answer", "clarify"):
                        conversations.append(session, conversation_id, "assistant",
                                             event.data.get("text") or event.data.get("question", ""))
                    elif event.type == "confirmation":
                        conversations.append(session, conversation_id, "assistant", f"Waiting for approval: {event.data['summary']}")
                    yield event
            except LLMError as exc:
                yield AgentEvent("error", {"code": "llm_error", "message": str(exc), "hint": exc.hint})

    return sse_response(events())


@router.post("/{conversation_id}/confirm")
def confirm(
    conversation_id: str, body: ActionRef, request: Request,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> Any:
    """Execute the stored action and stream action → observation → answer."""
    services = request.app.state.services
    with session_scope(services.engine) as session:
        row = pending_actions.get(session, body.action_id)
        if row is None or row.actor != ACTOR or row.conversation_id != conversation_id:
            raise UnknownAction()
        if row.status != "pending":
            raise ConfirmationError("already_decided", f"That action was already {row.status}.")

    def events() -> Iterator[AgentEvent]:
        """Claim, execute, narrate."""
        with session_scope(services.engine) as session:
            try:
                execution = execute_pending(
                    session=session, action_id=body.action_id, registry=OWNER_REGISTRY,
                    ctx=_ctx(request, session, idempotency_key), expected_actor=ACTOR, idempotency_key=idempotency_key,
                )
            except ConfirmationError as exc:
                yield AgentEvent("error", {"code": exc.code, "message": str(exc)})
                return
            except StripeGatewayError as exc:
                yield AgentEvent("error", {"code": "stripe_error", "message": str(exc), "hint": exc.hint})
                return
            yield AgentEvent("action", {"name": execution.action, "args": execution.parameters})
            yield AgentEvent("observation", {"name": execution.action, "result": execution.result})
            try:
                text = narrate_result(services.llm, action=execution.action, summary=execution.summary, result=execution.result)
            except LLMError:
                text = f"Done: {execution.summary}."
            conversations.append(session, conversation_id, "assistant", text)
            yield AgentEvent("answer", {"text": text, "result": {"action": execution.action, "data": execution.result}})

    return sse_response(events())


@router.post("/{conversation_id}/cancel")
def cancel(conversation_id: str, body: ActionRef, request: Request) -> dict[str, str]:
    """Dismiss a pending action so it can never be approved."""
    with session_scope(request.app.state.services.engine) as session:
        row = pending_actions.get(session, body.action_id)
        if row is None or row.conversation_id != conversation_id:
            raise UnknownAction()
        if not pending_actions.cancel(session, body.action_id):
            raise ConfirmationError("already_decided", f"That action was already {row.status}.")
    return {"status": "cancelled"}


@router.get("/{conversation_id}")
def history(conversation_id: str, request: Request) -> dict[str, Any]:
    """Transcript plus the proposal a reloaded UI should still show."""
    with session_scope(request.app.state.services.engine) as session:
        messages = conversations.history(session, conversation_id, limit=200)
        pending = pending_actions.latest_pending(session, conversation_id)
        return {
            "conversation_id": conversation_id,
            "messages": [{"role": m.role, "content": m.content, "created_at": m.created_at.isoformat()} for m in messages],
            "pending": None if pending is None else {
                "action_id": pending.id, "action": pending.action, "summary": pending.summary,
                "parameters": json.loads(pending.parameters_json),
            },
        }
```

`app/api/summary.py`:

```python
"""The daily summary: facts always, narration on request."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.agent.events import to_jsonable
from app.agent.narrator import narrate_summary
from app.api.auth import require_owner
from app.domain.periods import local_timezone
from app.domain.summary import build_daily_facts

router = APIRouter(prefix="/api/summary", dependencies=[Depends(require_owner)])


@router.get("/today")
def today(request: Request, narrate: bool = True) -> dict[str, Any]:
    """Facts computed in Python; `narrate=false` skips the model for the live rail."""
    services = request.app.state.services
    facts = build_daily_facts(
        services.gateway.list_payments(), services.gateway.list_invoices(status="open"),
        datetime.now(local_timezone()),
    )
    text = narrate_summary(services.llm, facts) if narrate else None
    return {"facts": to_jsonable(facts), "text": text}
```

`app/api/escalations.py`:

```python
"""Escalations as resources: list pending, approve one."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.api.auth import require_owner
from app.db import audit, escalations
from app.db.engine import session_scope
from app.domain.periods import local_timezone
from app.services.escalations import approve_and_notify

router = APIRouter(prefix="/api/escalations", dependencies=[Depends(require_owner)])


@router.get("")
def pending(request: Request) -> list[dict[str, Any]]:
    """Everything waiting for the owner."""
    with session_scope(request.app.state.services.engine) as session:
        return [
            {"id": r.id, "customer_name": r.customer_name, "invoice_id": r.invoice_id, "amount_cents": r.amount_cents,
             "reason": r.reason, "created_at": r.created_at.isoformat()}
            for r in escalations.pending(session)
        ]


@router.post("/{escalation_id}/approve")
def approve(escalation_id: str, request: Request) -> dict[str, Any]:
    """Approve from the panel; the click is the confirmation."""
    services = request.app.state.services
    with session_scope(services.engine) as session:
        outcome = approve_and_notify(session, escalation_id, gateway=services.gateway, notify=services.notify,
                                     now=datetime.now(local_timezone()))
        if not outcome.already_approved:
            audit.record(session, channel="web", actor="owner", prompt="(escalations panel)", action="approve_escalation",
                         parameters={"escalation_id": escalation_id}, result=outcome.__dict__, mutation=True)
        return outcome.__dict__.copy()
```

`app/api/customers.py`:

```python
"""Owner-side control over customer Telegram bindings."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request

from app.api.auth import require_owner
from app.db import bindings
from app.db.engine import session_scope

router = APIRouter(prefix="/api/customers", dependencies=[Depends(require_owner)])


@router.delete("/{customer_id}/telegram-binding")
def revoke(customer_id: str, request: Request) -> dict[str, int]:
    """Revoke every active binding for a customer."""
    with session_scope(request.app.state.services.engine) as session:
        return {"revoked": bindings.revoke_for_customer(session, customer_id, datetime.now(UTC).replace(tzinfo=None))}
```

`app/api/audit.py`:

```python
"""Read the audit log."""

import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.auth import require_owner
from app.db import audit
from app.db.engine import session_scope

router = APIRouter(prefix="/api/audit", dependencies=[Depends(require_owner)])


@router.get("")
def recent(request: Request, limit: int = Query(100, ge=1, le=500)) -> list[dict[str, Any]]:
    """Newest first: who asked what, which action ran, and what came back."""
    with session_scope(request.app.state.services.engine) as session:
        return [
            {"id": r.id, "created_at": r.created_at.isoformat(), "channel": r.channel, "actor": r.actor,
             "prompt": r.prompt, "action": r.action, "parameters": json.loads(r.parameters_json),
             "result": json.loads(r.result_json), "mutation": r.mutation}
            for r in audit.recent(session, limit)
        ]
```

- [ ] **Step 5: Run tests and lint; start the server once**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all tests pass (the whole suite so far); ruff clean.

Then, with a real `.env` in place: `uv run uvicorn app.main:app --port 8000` and in another shell
`curl -s -H "Authorization: Bearer dev-owner-token" "localhost:8000/api/summary/today?narrate=false" | head -c 300`
Expected: JSON with `facts`. Stop the server.

- [ ] **Step 6: Commit**

```bash
git add app/api app/main.py app/actions/context.py tests/test_api.py
git commit -m "feat(api): SSE agent turns, stored-action confirmation, summary, escalations, bindings, audit"
```

### Task 13: Telegram bot — binding, turns, confirmations, notifications

**Files:**
- Create: `app/telegram/__init__.py`, `app/telegram/notify.py`, `app/telegram/render.py`, `app/telegram/turns.py`, `app/telegram/handlers.py`, `app/telegram/bot.py`
- Modify: `app/main.py` (use `make_notifier(settings.telegram_bot_token)` instead of `no_notifier`), `Makefile` (no change yet — `dev` arrives in Task 18)
- Test: `tests/test_render.py`, `tests/test_turns.py`

**Interfaces:**
- Consumes: `build_customer_registry`, `CustomerContext`, `CustomerScopedGateway`, `run_turn`, `TurnHooks`, `execute_pending`, `planner_system`, `CUSTOMER_NOTES`, repositories.
- Produces: `make_notifier(token) -> Notifier`; `Reply(text, buttons)` where `buttons: list[list[InlineKeyboardButton]]`; `reply_for(events) -> Reply`; `receipt_reply(result) -> Reply`; `BotDeps(settings, gateway, llm, engine)`; sync glue `bind_token(deps, telegram_id, token) -> str | None`, `resolve_customer(deps, telegram_id) -> TelegramBinding | None`, `customer_turn(deps, binding, text) -> list[AgentEvent]`, `propose_payment(deps, binding, invoice_id) -> list[AgentEvent]`, `confirm_action(deps, binding, action_id) -> Reply`, `cancel_action(deps, action_id) -> None`; `build_application(deps) -> Application`, `main()`.
- Callback data grammar: `pay:<invoice_id>`, `confirm:<action_id>`, `cancel:<action_id>`. The actor string for pending actions is `f"telegram:{telegram_id}"`.
- PTB 22.8 facts: `Application.builder().token(t).build()`, `CommandHandler`, `MessageHandler(filters.TEXT & ~filters.COMMAND, ...)`, `CallbackQueryHandler`, `update.effective_user.id`, `context.args`, `update.callback_query.data`, `await query.answer()`, `application.run_polling()`; `telegram.Bot.send_message` is async, so the sync notifier wraps it in `asyncio.run` (called from FastAPI's threadpool, never from the bot's own loop). Build keyboards as `rows: list[list[InlineKeyboardButton]]` variables — never write a nested list literal opening with two brackets; the docs CI wikilink guard would flag it in this plan, and the style carries over.

- [ ] **Step 1: Write the failing tests**

`tests/test_render.py`:

```python
"""Bot replies: amounts never appear in free text; invoices become buttons."""

from app.agent.events import AgentEvent
from app.telegram.render import receipt_reply, reply_for


def test_answer_with_invoice_buttons() -> None:
    """An answer after my_invoices carries View/Pay buttons per open invoice."""
    events = [
        AgentEvent("action", {"name": "my_invoices", "args": {}}),
        AgentEvent("observation", {"name": "my_invoices", "result": {"count": 1, "invoices": [
            {"invoice_id": "in_1", "number": "F-0001", "status": "open", "due_date": "2026-09-11",
             "description": "Q3 retainer", "view_url": "https://invoice.example/in_1"},
        ]}}),
        AgentEvent("answer", {"text": "You have 1 unpaid invoice, due Sep 11."}),
    ]
    reply = reply_for(events)
    assert reply.text == "You have 1 unpaid invoice, due Sep 11."
    labels = [b.text for row in reply.buttons for b in row]
    assert labels == ["View F-0001", "Pay F-0001"]
    assert reply.buttons[0][0].url == "https://invoice.example/in_1"
    assert reply.buttons[0][1].callback_data == "pay:in_1"


def test_confirmation_and_receipt() -> None:
    """A proposal shows the summary with Confirm/Cancel; a receipt links the hosted invoice."""
    reply = reply_for([AgentEvent("confirmation", {"action_id": "act_1", "action": "pay_invoice",
                                                   "summary": "Pay invoice F-0001 for $1,200.00 with your card on file",
                                                   "parameters": {}})])
    assert reply.text.endswith("?")
    assert [b.callback_data for b in reply.buttons[0]] == ["confirm:act_1", "cancel:act_1"]
    receipt = receipt_reply({"paid": True, "number": "F-0001", "receipt_url": "https://invoice.example/in_1"})
    assert "$" not in receipt.text and receipt.buttons[0][0].url == "https://invoice.example/in_1"
```

`tests/test_turns.py`:

```python
"""Sync glue between Telegram updates and the agent, over fakes."""

import json
from datetime import UTC, datetime

from sqlalchemy import Engine

from app.settings import Settings
from app.telegram.turns import BotDeps, bind_token, confirm_action, customer_turn, propose_payment, resolve_customer
from tests.fakes.llm_fake import ScriptedLLM
from tests.fakes.stripe_fake import FakeStripeGateway


def _deps(engine: Engine, llm: ScriptedLLM) -> tuple[BotDeps, FakeStripeGateway]:
    """Acme bound via token 'tok-acme' with one $1,200 invoice."""
    fake = FakeStripeGateway()
    fake.add_customer("cus_acme", "Acme Corp", bind_token="tok-acme")
    fake.add_invoice("in_1", "cus_acme", 120000)
    return BotDeps(settings=Settings(_env_file=None), gateway=fake, llm=llm, engine=engine), fake


def test_bind_then_turn_then_pay_via_buttons(engine: Engine) -> None:
    """/start <token> binds; a question runs the customer registry; Pay → Confirm charges once."""
    llm = ScriptedLLM([json.dumps({"reasoning": "", "action": "my_balance", "parameters": {}}),
                       json.dumps({"reasoning": "", "action": "answer", "parameters": {"text": "1 unpaid invoice."}})])
    deps, fake = _deps(engine, llm)
    assert bind_token(deps, 7, "nope") is None
    assert bind_token(deps, 7, "tok-acme") == "Acme Corp"
    binding = resolve_customer(deps, 7)
    assert binding is not None and binding.stripe_customer_id == "cus_acme"
    events = customer_turn(deps, binding, "what do I owe?")
    assert events[-1].data["text"] == "1 unpaid invoice."
    proposal = propose_payment(deps, binding, "in_1")
    assert proposal[-1].type == "confirmation"
    reply = confirm_action(deps, binding, proposal[-1].data["action_id"])
    assert "receipt" in reply.text.lower() or "paid" in reply.text.lower()
    assert len([c for c in fake.calls if c[0] == "pay_invoice"]) == 1
    assert "expired" in confirm_action(deps, binding, proposal[-1].data["action_id"]).text.lower() or \
        "already" in confirm_action(deps, binding, proposal[-1].data["action_id"]).text.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_render.py tests/test_turns.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.telegram'`.

- [ ] **Step 3: Implement notify and render**

`app/telegram/__init__.py`: `"""Customer-facing Telegram bot (long polling) and the owner→customer notifier."""`

`app/telegram/notify.py`:

```python
"""Send a message to a customer from outside the bot process (the API's approve path)."""

import asyncio
import logging

from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import TelegramError

from app.actions.context import Notifier, no_notifier

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
                await bot.send_message(chat_id=telegram_id, text=text, reply_markup=markup)
        try:
            asyncio.run(_go())
            return True
        except TelegramError as exc:
            log.warning("Telegram notification to %s failed: %s", telegram_id, exc)
            return False

    return send
```

`app/telegram/render.py`:

```python
"""Turn agent events into a Telegram reply.

Deterministic on purpose: the planner writes the sentence, but which
buttons appear and what a receipt says is decided here, in Python.
"""

from dataclasses import dataclass, field
from typing import Any

from telegram import InlineKeyboardButton

from app.agent.events import AgentEvent

ERROR_TEXT = "Something went wrong on my side. Please try again in a moment."
NOT_CONNECTED_TEXT = "I don't know which account you are yet. Open the link the business sent you to connect."


@dataclass
class Reply:
    """Text plus inline keyboard rows."""

    text: str
    buttons: list[list[InlineKeyboardButton]] = field(default_factory=list)


def _invoice_rows(events: list[AgentEvent]) -> list[list[InlineKeyboardButton]]:
    """View/Pay buttons for every open invoice seen in this turn's observations."""
    rows: list[list[InlineKeyboardButton]] = []
    seen: set[str] = set()
    for event in events:
        if event.type != "observation" or event.data.get("name") not in ("my_balance", "my_invoices"):
            continue
        for invoice in event.data["result"].get("invoices", []):
            if invoice["status"] != "open" or invoice["invoice_id"] in seen:
                continue
            seen.add(invoice["invoice_id"])
            label = invoice.get("number") or invoice["invoice_id"]
            row = [InlineKeyboardButton(f"View {label}", url=invoice["view_url"])] if invoice.get("view_url") else []
            row.append(InlineKeyboardButton(f"Pay {label}", callback_data=f"pay:{invoice['invoice_id']}"))
            rows.append(row)
    return rows


def reply_for(events: list[AgentEvent]) -> Reply:
    """The reply for a finished turn, keyed on its terminal event."""
    last = events[-1] if events else AgentEvent("error", {})
    if last.type == "confirmation":
        action_id = last.data["action_id"]
        row = [InlineKeyboardButton("Confirm", callback_data=f"confirm:{action_id}"),
               InlineKeyboardButton("Cancel", callback_data=f"cancel:{action_id}")]
        return Reply(f"{last.data['summary']}?", [row])
    if last.type == "answer":
        return Reply(last.data["text"], _invoice_rows(events))
    if last.type == "clarify":
        return Reply(last.data["question"])
    return Reply(ERROR_TEXT)


def receipt_reply(result: dict[str, Any]) -> Reply:
    """After a confirmed payment: no amount in the text, the receipt behind a button."""
    label = result.get("number") or result.get("invoice_id", "")
    rows: list[list[InlineKeyboardButton]] = []
    if result.get("receipt_url"):
        rows.append([InlineKeyboardButton("View receipt", url=result["receipt_url"])])
    return Reply(f"Paid — thank you. Invoice {label} is settled; your receipt is below.", rows)
```

- [ ] **Step 4: Implement the sync glue**

`app/telegram/turns.py`:

```python
"""Synchronous glue between Telegram updates and the agent.

Handlers call these through `asyncio.to_thread`. Everything here runs the
customer registry over a gateway bound to the customer from the binding row.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.actions.context import CustomerContext
from app.actions.customer import PayInvoiceParams, build_customer_registry
from app.agent.confirm import ConfirmationError, execute_pending
from app.agent.events import AgentEvent
from app.agent.executor import ActionError
from app.agent.loop import TurnHooks, run_turn
from app.agent.prompts import CUSTOMER_NOTES, planner_system
from app.db import audit, bindings, conversations, pending_actions
from app.db.clock import utcnow
from app.db.engine import session_scope
from app.db.models import TelegramBinding
from app.domain.periods import local_timezone
from app.llm.base import ChatMessage, LLMBackend, LLMError
from app.settings import Settings
from app.stripe_.customer_client import CustomerScopedGateway
from app.stripe_.gateway import StripeGateway, StripeGatewayError
from app.telegram.render import ERROR_TEXT, Reply, receipt_reply, reply_for

CUSTOMER_REGISTRY = build_customer_registry()
CHANNEL = "telegram"


@dataclass
class BotDeps:
    """Process-wide dependencies for the bot."""

    settings: Settings
    gateway: StripeGateway
    llm: LLMBackend
    engine: Engine


def _actor(telegram_id: int) -> str:
    """Actor string stored on pending actions and audit rows."""
    return f"telegram:{telegram_id}"


def _ctx(deps: BotDeps, session: Session, binding: TelegramBinding) -> CustomerContext:
    """A context whose gateway is bound to the customer on the binding row."""
    return CustomerContext(
        gateway=CustomerScopedGateway(deps.gateway, binding.stripe_customer_id), session=session,
        telegram_id=binding.telegram_id, customer_name=binding.customer_name, now=datetime.now(local_timezone()),
    )


def _hooks(session: Session, binding: TelegramBinding, prompt: str) -> TurnHooks:
    """Persist proposals and audit rows, committing immediately (shared SQLite file)."""
    def propose(spec: Any, params: Any, summary: str) -> str:
        """Store the proposal under this Telegram actor."""
        row = pending_actions.create(
            session, conversation_id=_actor(binding.telegram_id), channel=CHANNEL, actor=_actor(binding.telegram_id),
            action=spec.name, parameters=params.model_dump(mode="json"), summary=summary, prompt=prompt,
        )
        session.commit()
        return row.id

    def record(action: str, parameters: dict[str, Any], result: Any, mutation: bool) -> None:
        """Audit."""
        audit.record(session, channel=CHANNEL, actor=_actor(binding.telegram_id), prompt=prompt, action=action,
                     parameters=parameters, result=result, mutation=mutation)
        session.commit()

    return TurnHooks(propose=propose, audit=record)


def bind_token(deps: BotDeps, telegram_id: int, token: str) -> str | None:
    """Bind a Telegram account via a seed-minted token; returns the customer name or None."""
    customer = deps.gateway.find_customer_by_bind_token(token.strip())
    if customer is None:
        return None
    with session_scope(deps.engine) as session:
        bindings.bind(session, telegram_id=telegram_id, customer_id=customer.id, customer_name=customer.name, now=utcnow())
    return customer.name


def resolve_customer(deps: BotDeps, telegram_id: int) -> TelegramBinding | None:
    """The active binding, renewed, or None. Detached from its session for use in handlers."""
    with session_scope(deps.engine) as session:
        row = bindings.resolve(session, telegram_id, utcnow())
        if row is not None:
            session.expunge(row)
        return row


def revoke(deps: BotDeps, telegram_id: int) -> bool:
    """`/logout`."""
    with session_scope(deps.engine) as session:
        return bindings.revoke(session, telegram_id, utcnow())


def customer_turn(deps: BotDeps, binding: TelegramBinding, text: str) -> list[AgentEvent]:
    """Run one turn of the customer agent and return every event."""
    conversation_id = _actor(binding.telegram_id)
    with session_scope(deps.engine) as session:
        conversations.ensure(session, conversation_id, CHANNEL)
        history = [ChatMessage(role=m.role, content=m.content)  # type: ignore[arg-type]
                   for m in conversations.history(session, conversation_id)]
        conversations.append(session, conversation_id, "user", text)
        session.commit()
        ctx = _ctx(deps, session, binding)
        system = planner_system(registry=CUSTOMER_REGISTRY, today=ctx.now.date(), channel_notes=CUSTOMER_NOTES)
        try:
            events = list(run_turn(llm=deps.llm, registry=CUSTOMER_REGISTRY, ctx=ctx, system=system,
                                   history=history, prompt=text, hooks=_hooks(session, binding, text)))
        except LLMError as exc:
            return [AgentEvent("error", {"message": str(exc)})]
        last = events[-1]
        if last.type in ("answer", "clarify"):
            conversations.append(session, conversation_id, "assistant", last.data.get("text") or last.data.get("question", ""))
        return events


def propose_payment(deps: BotDeps, binding: TelegramBinding, invoice_id: str) -> list[AgentEvent]:
    """The Pay button: propose `pay_invoice` deterministically, no planner involved."""
    spec = CUSTOMER_REGISTRY.get("pay_invoice")
    assert spec is not None and spec.describe is not None
    params = PayInvoiceParams(invoice_id=invoice_id)
    with session_scope(deps.engine) as session:
        ctx = _ctx(deps, session, binding)
        try:
            proposal = spec.describe(ctx, params)
        except (ActionError, StripeGatewayError) as exc:
            return [AgentEvent("answer", {"text": str(exc)})]
        if proposal.summary is None:
            return [AgentEvent("answer", {"text": proposal.resolved["message"]})]
        action_id = _hooks(session, binding, f"(tapped Pay {invoice_id})").propose(spec, params, proposal.summary)
        return [AgentEvent("confirmation", {"action_id": action_id, "action": spec.name,
                                            "summary": proposal.summary, "parameters": params.model_dump()})]


def confirm_action(deps: BotDeps, binding: TelegramBinding, action_id: str) -> Reply:
    """The Confirm button: execute the stored action for this Telegram actor only."""
    with session_scope(deps.engine) as session:
        try:
            execution = execute_pending(session=session, action_id=action_id, registry=CUSTOMER_REGISTRY,
                                        ctx=_ctx(deps, session, binding), expected_actor=_actor(binding.telegram_id))
        except ConfirmationError as exc:
            return Reply(str(exc))
        except (ActionError, StripeGatewayError) as exc:
            return Reply(f"I couldn't complete that: {exc}")
        except Exception:
            return Reply(ERROR_TEXT)
    return receipt_reply(execution.result) if execution.action == "pay_invoice" else Reply(f"Done: {execution.summary}.")


def cancel_action(deps: BotDeps, action_id: str) -> None:
    """The Cancel button."""
    with session_scope(deps.engine) as session:
        pending_actions.cancel(session, action_id)
```

- [ ] **Step 5: Implement handlers and the entrypoint**

`app/telegram/handlers.py`:

```python
"""python-telegram-bot handlers. Thin: read the update, call sync glue in a thread, reply."""

import asyncio

from telegram import InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from app.telegram import turns
from app.telegram.render import NOT_CONNECTED_TEXT, Reply

WELCOME = ("Hi, I'm Ledger. I can tell you what you owe and take payment for your invoices. "
           "To connect your account, open the link the business sent you.")
HELP = "Ask me things like \"what do I owe?\" or \"show my invoices\". /logout disconnects this chat."


def _deps(context: ContextTypes.DEFAULT_TYPE) -> turns.BotDeps:
    """Dependencies stored on the application at startup."""
    return context.application.bot_data["deps"]


async def _send(update: Update, reply: Reply) -> None:
    """Send a Reply to the effective chat."""
    markup = InlineKeyboardMarkup(reply.buttons) if reply.buttons else None
    assert update.effective_chat is not None
    await update.effective_chat.send_message(reply.text, reply_markup=markup)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/start [token]`: bind when a token is present, otherwise explain."""
    assert update.effective_user is not None
    if not context.args:
        await _send(update, Reply(WELCOME))
        return
    name = await asyncio.to_thread(turns.bind_token, _deps(context), update.effective_user.id, context.args[0])
    if name is None:
        await _send(update, Reply("That link isn't valid. Ask the business for a new one."))
    else:
        await _send(update, Reply(f"Connected to {name}. Ask me what you owe, or /logout to disconnect."))


async def logout(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/logout`: revoke this chat's binding."""
    assert update.effective_user is not None
    revoked = await asyncio.to_thread(turns.revoke, _deps(context), update.effective_user.id)
    await _send(update, Reply("Disconnected." if revoked else "This chat wasn't connected."))


async def help_command(update: Update, _context: ContextTypes.DEFAULT_TYPE) -> None:
    """`/help`."""
    await _send(update, Reply(HELP))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Free text → agent turn, if bound."""
    assert update.effective_user is not None and update.message is not None and update.message.text
    deps = _deps(context)
    binding = await asyncio.to_thread(turns.resolve_customer, deps, update.effective_user.id)
    if binding is None:
        await _send(update, Reply(NOT_CONNECTED_TEXT))
        return
    events = await asyncio.to_thread(turns.customer_turn, deps, binding, update.message.text)
    await _send(update, turns.reply_for(events))


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Inline buttons: pay:<invoice>, confirm:<action>, cancel:<action>."""
    query = update.callback_query
    assert query is not None and query.data and update.effective_user is not None
    await query.answer()
    deps = _deps(context)
    kind, _, ref = query.data.partition(":")
    if kind == "cancel":
        await asyncio.to_thread(turns.cancel_action, deps, ref)
        await query.edit_message_text("Cancelled.")
        return
    binding = await asyncio.to_thread(turns.resolve_customer, deps, update.effective_user.id)
    if binding is None:
        await _send(update, Reply(NOT_CONNECTED_TEXT))
        return
    if kind == "pay":
        await _send(update, turns.reply_for(await asyncio.to_thread(turns.propose_payment, deps, binding, ref)))
    elif kind == "confirm":
        await query.edit_message_reply_markup(None)
        await _send(update, await asyncio.to_thread(turns.confirm_action, deps, binding, ref))
```

Note: `turns.reply_for` is `app.telegram.render.reply_for` re-exported by import in `turns.py`; import it directly from `render` in handlers if you prefer — either is fine, but use one consistently.

`app/telegram/bot.py`:

```python
"""Bot entrypoint: `python -m app.telegram.bot`. Long polling; no public URL needed."""

import logging

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from app.db.engine import make_engine
from app.llm.factory import build_backend
from app.settings import load_settings
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
    deps = BotDeps(settings=settings, gateway=StripeOwnerGateway(settings.stripe_secret_key),
                   llm=build_backend(settings), engine=make_engine(settings.database_url))
    build_application(deps).run_polling()


if __name__ == "__main__":
    main()
```

Update `app/main.py`: replace `from app.actions.context import no_notifier` with `from app.telegram.notify import make_notifier` and set `notify=make_notifier(settings.telegram_bot_token)`.

- [ ] **Step 6: Run tests and lint; poll once for real**

Run: `uv run pytest -q && uv run ruff check .`
Expected: all pass; ruff clean.

With `TELEGRAM_BOT_TOKEN` in `.env` (from agent-vault `replicant-assignment-telegram-bot-token`): `uv run python -m app.telegram.bot`, send `/start` to the bot from a Telegram client, expect the welcome text. Stop with Ctrl-C.

- [ ] **Step 7: Commit**

```bash
git add app/telegram app/main.py tests/test_render.py tests/test_turns.py
git commit -m "feat(telegram): long-polling bot with token binding, scoped turns, confirm buttons, notifier"
```

### Task 14: Seed script — deterministic dataset, idempotent writer, detection and clean-up

**Files:**
- Create: `seed/__init__.py`, `seed/dataset.py`, `seed/writer.py`, `seed/inventory.py`, `seed/report.py`, `seed/__main__.py`
- Modify: `Makefile` (add `seed`)
- Test: `tests/test_seed_dataset.py`

**Interfaces:**
- Consumes: `StripeOwnerGateway.client` (Task 5), `translate_stripe_errors`, `TELEGRAM_PAYMENT_CEILING_CENTS`, `format_usd`, `local_timezone`, `Settings.require_stripe`.
- Produces: `SeedCustomer(key, name, email)`, `SeedPayment(key, customer_key, amount_cents, occurred_at, decline, description)` (`occurred_at=None` means "today, real timestamp"), `SeedInvoice(key, customer_key, amount_cents, description, due_in_days, paid)`, `Dataset(today, customers, payments, invoices)` with `today_payments`/`history_payments`; `build_dataset(today, seed=42, tz=None) -> Dataset`; `Say` output-sink Protocol (defined in `seed/report.py`, imported by writer and inventory — create `report.py` before `writer.py`); writer functions `create_customers(client, dataset, run_id, say) -> dict[str, CreatedCustomer]`, `create_payments(client, payments, customer_ids, run_id, say) -> tuple[int, int]`, `create_invoices(client, dataset, customer_ids, run_id, say) -> int`; `Inventory(customers, seed_days, open_invoice_ids)`, `find_seeded(client) -> Inventory`, `clean(client, inventory, say) -> None`; `print_report(dataset, customers, say)`; CLI `python -m seed [--force] [--clean] [--today-only]`.
- Stripe facts used: test payment-method tokens `pm_card_visa` and `pm_card_chargeDeclinedInsufficientFunds` (the latter yields a real `card_declined` / `insufficient_funds` outcome and raises `stripe.CardError` on confirm); `payment_intents.create` with `confirm=True, off_session=True, payment_method_types=["card"]` (the explicit type list avoids the `return_url` requirement); `payment_methods.attach("pm_card_visa", {"customer": id})` creates a card on file; `invoices.pay(id, {"paid_out_of_band": True})` marks historical invoices paid without creating a charge. Every object carries `metadata.seed_run`; historical ones carry `metadata.demo_created_at`. Deterministic idempotency keys (`seed:<run_id>:<object key>`) make a same-day re-run after a crash resume instead of duplicate. `seed/` is allowed to import `stripe` directly (the "only `app/stripe_/owner_client.py` imports stripe" rule is about the application package).

- [ ] **Step 1: Write the failing tests**

`tests/test_seed_dataset.py`:

```python
"""The dataset is deterministic and contains every object the README and the demos rely on."""

from datetime import date, timedelta, timezone

from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS
from seed.dataset import build_dataset

TODAY = date(2026, 9, 1)
TZ = timezone(timedelta(hours=-4))


def test_dataset_is_deterministic() -> None:
    """Same seed, same objects, so the README's figures hold on the reviewer's account."""
    assert build_dataset(TODAY, tz=TZ) == build_dataset(TODAY, tz=TZ)


def test_dataset_contains_the_demo_fixtures() -> None:
    """Acme's $1,200 open invoice, a ceiling invoice, two declines, ~18 payments today, Maya today."""
    ds = build_dataset(TODAY, tz=TZ)
    names = {c.key: c.name for c in ds.customers}
    assert names["acme"] == "Acme Corp" and names["maya"] == "Maya Chen"
    assert all(c.email.endswith("@example.com") for c in ds.customers)
    today_ok = [p for p in ds.today_payments if not p.decline]
    today_declines = [p for p in ds.today_payments if p.decline]
    assert len(today_ok) == 18 and len(today_declines) == 2
    assert any(p.customer_key == "maya" for p in today_ok)
    open_acme = [i for i in ds.invoices if i.customer_key == "acme" and not i.paid]
    assert 120000 in [i.amount_cents for i in open_acme]
    assert any(i.amount_cents >= TELEGRAM_PAYMENT_CEILING_CENTS and not i.paid for i in ds.invoices)
    assert all(0 < i.due_in_days <= 30 for i in ds.invoices if not i.paid)


def test_history_is_dated_in_business_hours_over_three_weeks() -> None:
    """Historical payments carry past timestamps clustered into the working day."""
    ds = build_dataset(TODAY, tz=TZ)
    history = ds.history_payments
    assert history and all(p.occurred_at is not None for p in history)
    days_ago = {(TODAY - p.occurred_at.date()).days for p in history}  # type: ignore[union-attr]
    assert min(days_ago) == 1 and max(days_ago) == 21
    assert all(8 <= p.occurred_at.hour <= 18 for p in history)  # type: ignore[union-attr]
    yesterday = [p for p in history if (TODAY - p.occurred_at.date()).days == 1]  # type: ignore[union-attr]
    assert 8 <= len(yesterday) <= 14
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_seed_dataset.py -q`
Expected: FAIL with `ModuleNotFoundError: No module named 'seed'`.

- [ ] **Step 3: Implement `seed/dataset.py`**

`seed/__init__.py`: `"""Populate a fresh Stripe sandbox with the data the assistant expects."""`

```python
"""Generate the seed dataset. Pure and deterministic; no Stripe here.

Acme Corp and Maya Chen are pinned because the brief's example commands
name them. Everything else comes from Faker under a fixed seed.
"""

import random
from dataclasses import dataclass
from datetime import date, datetime, timedelta, tzinfo

from faker import Faker

from app.domain.periods import local_timezone

AMOUNT_BUCKETS: list[tuple[tuple[int, int], int]] = [((1500, 6000), 60), ((6000, 25000), 30), ((25000, 80000), 10)]
BUSINESS_HOURS = list(range(8, 19))
HOUR_WEIGHTS = [1, 2, 4, 5, 5, 3, 4, 5, 5, 3, 2]
DESCRIPTIONS = ["Consulting", "Monthly retainer", "Design sprint", "Support plan", "Workshop",
                "Licence renewal", "Onboarding", "Data migration"]
HISTORY_DAYS = 21
TODAY_SUCCESSES = 18
TODAY_DECLINES = 2


@dataclass(frozen=True)
class SeedCustomer:
    """A customer to create."""

    key: str
    name: str
    email: str


@dataclass(frozen=True)
class SeedPayment:
    """A payment attempt. `occurred_at=None` means today, with Stripe's own timestamp."""

    key: str
    customer_key: str
    amount_cents: int
    occurred_at: datetime | None
    decline: bool
    description: str


@dataclass(frozen=True)
class SeedInvoice:
    """An invoice; paid ones are marked paid out of band and dated in the past."""

    key: str
    customer_key: str
    amount_cents: int
    description: str
    due_in_days: int
    paid: bool


@dataclass(frozen=True)
class Dataset:
    """Everything the seed writes."""

    today: date
    customers: list[SeedCustomer]
    payments: list[SeedPayment]
    invoices: list[SeedInvoice]

    @property
    def today_payments(self) -> list[SeedPayment]:
        """Payments created with real timestamps."""
        return [p for p in self.payments if p.occurred_at is None]

    @property
    def history_payments(self) -> list[SeedPayment]:
        """Payments carrying `demo_created_at`."""
        return [p for p in self.payments if p.occurred_at is not None]


def _slug(name: str) -> str:
    """`Maya Chen` → `maya.chen`."""
    return ".".join(part.lower() for part in name.replace(",", "").split())


def _amount(rng: random.Random) -> int:
    """Weighted amount in cents, rounded to the dollar so figures read naturally."""
    (low, high), = rng.choices([b for b, _ in AMOUNT_BUCKETS], weights=[w for _, w in AMOUNT_BUCKETS])
    return rng.randint(low // 100, high // 100) * 100


def _customers(fake: Faker) -> list[SeedCustomer]:
    """Two pinned customers plus four companies and four people."""
    pinned = [SeedCustomer("acme", "Acme Corp", "billing@acme.example.com"),
              SeedCustomer("maya", "Maya Chen", "maya.chen@example.com")]
    generated = [fake.company() for _ in range(4)] + [fake.name() for _ in range(4)]
    return pinned + [SeedCustomer(f"c{i}", name, f"{_slug(name)}@example.com") for i, name in enumerate(generated)]


def build_dataset(today: date, seed: int = 42, tz: tzinfo | None = None) -> Dataset:
    """Build the dataset for `today`. Same inputs, same output."""
    zone = tz or local_timezone()
    Faker.seed(seed)
    fake = Faker()
    rng = random.Random(seed)
    customers = _customers(fake)
    keys = [c.key for c in customers]
    weights = [3, 3] + [1] * (len(keys) - 2)  # Acme and Maya show up more, so their stories are rich
    payments: list[SeedPayment] = []
    for days_ago in range(1, HISTORY_DAYS + 1):
        day = today - timedelta(days=days_ago)
        weekday = day.weekday() < 5
        count = 11 if days_ago == 1 else (rng.randint(5, 9) if weekday else rng.randint(1, 3))
        for n in range(count):
            hour = rng.choices(BUSINESS_HOURS, weights=HOUR_WEIGHTS)[0]
            when = datetime(day.year, day.month, day.day, hour, rng.randint(0, 59), tzinfo=zone)
            payments.append(SeedPayment(f"h{days_ago}-{n}", rng.choices(keys, weights=weights)[0],
                                        _amount(rng), when, False, rng.choice(DESCRIPTIONS)))
    for n in range(TODAY_SUCCESSES):
        customer = "maya" if n == 0 else rng.choices(keys, weights=weights)[0]
        payments.append(SeedPayment(f"t{n}", customer, _amount(rng), None, False, rng.choice(DESCRIPTIONS)))
    for n in range(TODAY_DECLINES):
        payments.append(SeedPayment(f"d{n}", keys[2 + n], _amount(rng), None, True, rng.choice(DESCRIPTIONS)))
    invoices = [
        SeedInvoice("acme_retainer", "acme", 120000, "Q3 retainer", 10, False),
        SeedInvoice("acme_licence", "acme", 240000, "Annual licence", 21, False),
        SeedInvoice("maya_workshop", "maya", 18000, "Workshop", 5, False),
        SeedInvoice("paid_c0", "c0", 45000, "Onboarding", -20, True),
        SeedInvoice("paid_c1", "c1", 32000, "Design sprint", -12, True),
    ]
    return Dataset(today=today, customers=customers, payments=payments, invoices=invoices)
```

- [ ] **Step 4: Implement the writer, inventory, and report**

`seed/writer.py`:

```python
"""Create the dataset in Stripe. Every call is idempotent per (run_id, object key)."""

import secrets
from dataclasses import dataclass
from datetime import timedelta

import stripe

from seed.dataset import Dataset, SeedPayment
from seed.report import Say

SUCCESS_CARD = "pm_card_visa"
DECLINE_CARD = "pm_card_chargeDeclinedInsufficientFunds"


@dataclass(frozen=True)
class CreatedCustomer:
    """What the report needs about a created customer."""

    key: str
    id: str
    name: str
    bind_token: str


def _opts(run_id: str, key: str) -> dict[str, str]:
    """Per-object idempotency options."""
    return {"idempotency_key": f"seed:{run_id}:{key}"}


def create_customers(client: stripe.StripeClient, dataset: Dataset, run_id: str, say: Say) -> dict[str, CreatedCustomer]:
    """Create customers with a card on file and a Telegram bind token in metadata."""
    created: dict[str, CreatedCustomer] = {}
    for customer in dataset.customers:
        token = secrets.token_urlsafe(12)
        row = client.v1.customers.create(
            {"name": customer.name, "email": customer.email,
             "metadata": {"seed_run": run_id, "seed_key": customer.key, "seed_day": dataset.today.isoformat(),
                          "telegram_bind_token": token}},
            options=_opts(run_id, f"cus:{customer.key}"),
        )
        method = client.v1.payment_methods.attach(SUCCESS_CARD, {"customer": row.id}, options=_opts(run_id, f"pm:{customer.key}"))
        client.v1.customers.update(row.id, {"invoice_settings": {"default_payment_method": method.id}})
        created[customer.key] = CreatedCustomer(customer.key, row.id, customer.name,
                                                row["metadata"]["telegram_bind_token"])
        say(f"  customer {customer.name} ({row.id})")
    return created


def create_payments(client: stripe.StripeClient, payments: list[SeedPayment], customer_ids: dict[str, str],
                    run_id: str, say: Say) -> tuple[int, int]:
    """Create payment intents; returns (succeeded, declined). Declines raise CardError by design."""
    ok = declined = 0
    for index, payment in enumerate(payments, 1):
        metadata = {"seed_run": run_id, "seed_key": payment.key,
                    "seed_scope": "history" if payment.occurred_at else "today"}
        if payment.occurred_at:
            metadata["demo_created_at"] = payment.occurred_at.isoformat()
        params = {
            "amount": payment.amount_cents, "currency": "usd", "customer": customer_ids[payment.customer_key],
            "payment_method": DECLINE_CARD if payment.decline else SUCCESS_CARD, "confirm": True,
            "off_session": True, "payment_method_types": ["card"], "description": payment.description,
            "metadata": metadata,
        }
        try:
            client.v1.payment_intents.create(params, options=_opts(run_id, f"pi:{payment.key}"))  # type: ignore[arg-type]
            ok += 1
        except stripe.CardError:
            if not payment.decline:
                raise
            declined += 1
        if index % 10 == 0 or index == len(payments):
            say(f"  payments {index}/{len(payments)}")
    return ok, declined


def create_invoices(client: stripe.StripeClient, dataset: Dataset, customer_ids: dict[str, str],
                    run_id: str, say: Say) -> int:
    """Create, itemise, finalise; mark historical ones paid out of band."""
    for invoice in dataset.invoices:
        metadata = {"seed_run": run_id, "seed_key": invoice.key}
        if invoice.paid:
            paid_on = dataset.today + timedelta(days=invoice.due_in_days)
            metadata["demo_created_at"] = f"{paid_on.isoformat()}T10:00:00+00:00"
        row = client.v1.invoices.create(
            {"customer": customer_ids[invoice.customer_key], "collection_method": "send_invoice",
             "days_until_due": invoice.due_in_days if invoice.due_in_days > 0 else 30,
             "description": invoice.description, "metadata": metadata},
            options=_opts(run_id, f"in:{invoice.key}"),
        )
        client.v1.invoice_items.create(
            {"customer": customer_ids[invoice.customer_key], "invoice": row.id, "amount": invoice.amount_cents,
             "currency": "usd", "description": invoice.description},
            options=_opts(run_id, f"ii:{invoice.key}"),
        )
        client.v1.invoices.finalize_invoice(row.id, options=_opts(run_id, f"fin:{invoice.key}"))
        if invoice.paid:
            client.v1.invoices.pay(row.id, {"paid_out_of_band": True}, options=_opts(run_id, f"pay:{invoice.key}"))
        say(f"  invoice {invoice.description} for {invoice.customer_key} ({row.id})")
    return len(dataset.invoices)
```

`seed/inventory.py`:

```python
"""Detect what a previous seed left behind, and remove what Stripe allows."""

from dataclasses import dataclass, field

import stripe

from seed.report import Say


@dataclass(frozen=True)
class SeededCustomer:
    """A customer created by a previous run."""

    id: str
    name: str
    bind_token: str
    seed_day: str


@dataclass
class Inventory:
    """Seeded objects still in the account."""

    customers: list[SeededCustomer] = field(default_factory=list)
    open_invoice_ids: list[str] = field(default_factory=list)

    @property
    def seed_days(self) -> set[str]:
        """Days on which customers were seeded (normally one)."""
        return {c.seed_day for c in self.customers}


def find_seeded(client: stripe.StripeClient) -> Inventory:
    """Scan customers and open invoices for `metadata.seed_run`."""
    inventory = Inventory()
    for customer in client.v1.customers.list({"limit": 100}).auto_paging_iter():
        meta = customer.get("metadata") or {}
        if meta.get("seed_run"):
            inventory.customers.append(SeededCustomer(customer.id, customer.get("name") or "", meta.get("telegram_bind_token", ""), meta.get("seed_day", "")))
    for invoice in client.v1.invoices.list({"limit": 100, "status": "open"}).auto_paging_iter():
        if (invoice.get("metadata") or {}).get("seed_run"):
            inventory.open_invoice_ids.append(invoice.id)
    return inventory


def clean(client: stripe.StripeClient, inventory: Inventory, say: Say) -> None:
    """Void seeded open invoices and delete seeded customers. Charges cannot be deleted; say so."""
    for invoice_id in inventory.open_invoice_ids:
        client.v1.invoices.void_invoice(invoice_id)
        say(f"  voided {invoice_id}")
    for customer in inventory.customers:
        client.v1.customers.delete(customer.id)
        say(f"  deleted {customer.name} ({customer.id})")
    say("  note: Stripe does not allow deleting charges or payment intents; seeded payments remain "
        "in the account (tagged metadata.seed_run) and still count towards history.")
```

`seed/report.py`:

```python
"""What the reviewer reads when the seed finishes: figures to verify, tokens to bind."""

from collections.abc import Iterable
from typing import Protocol

from app.domain.money import format_usd
from app.domain.policy import TELEGRAM_PAYMENT_CEILING_CENTS
from seed.dataset import Dataset


class Say(Protocol):
    """An output sink for progress and report lines (print, or a test recorder)."""

    def __call__(self, line: str) -> None:
        """Emit one line."""
        ...


def print_report(dataset: Dataset, customers: Iterable[tuple[str, str]], say: Say) -> None:
    """Print today's expected figures and the per-customer Telegram tokens.

    Args:
        dataset: The dataset that was written.
        customers: (name, bind_token) pairs.
        say: Output sink.
    """
    today_ok = [p for p in dataset.today_payments if not p.decline]
    say("")
    say("Seeded. Figures the daily summary should report today:")
    say(f"  {len(today_ok)} successful payments totalling {format_usd(sum(p.amount_cents for p in today_ok))}")
    say(f"  {len([p for p in dataset.today_payments if p.decline])} declines (insufficient funds)")
    for invoice in dataset.invoices:
        if not invoice.paid:
            flag = "  ← at/above the bot's ceiling, escalates" if invoice.amount_cents >= TELEGRAM_PAYMENT_CEILING_CENTS else ""
            say(f"  open invoice: {invoice.customer_key} {format_usd(invoice.amount_cents)} — {invoice.description}{flag}")
    say("")
    say("Telegram binding tokens (send `/start <token>` to your bot, or open https://t.me/<bot>?start=<token>):")
    for name, token in customers:
        say(f"  {name:<28} {token}")
    say("")
    say("Tip: Acme Corp has both a payable invoice and one that escalates — bind Acme to see the whole loop.")
```

- [ ] **Step 5: Implement the CLI and Makefile target**

`seed/__main__.py`:

```python
"""`python -m seed [--force] [--clean] [--today-only]`.

Default: seed a fresh account, or, if seeded data exists, print the tokens and
exit without doubling revenue. `--force` cleans then seeds. `--clean` only
removes. `--today-only` adds a fresh day of activity for existing customers.
"""

import argparse
import secrets
import sys
from datetime import datetime

from app.domain.periods import local_timezone
from app.settings import ConfigError, load_settings
from app.stripe_.gateway import StripeGatewayError
from app.stripe_.owner_client import StripeOwnerGateway, translate_stripe_errors
from seed.dataset import build_dataset
from seed.inventory import clean, find_seeded
from seed.report import print_report
from seed.writer import create_customers, create_invoices, create_payments


def say(line: str) -> None:
    """Print immediately so progress is visible while Stripe calls run."""
    print(line, flush=True)


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(prog="seed", description=__doc__)
    parser.add_argument("--force", action="store_true", help="remove seeded data, then seed again")
    parser.add_argument("--clean", action="store_true", help="remove seeded data and exit")
    parser.add_argument("--today-only", action="store_true", help="add today's activity for existing seeded customers")
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        settings.require_stripe()
    except ConfigError as exc:
        say(f"error: {exc}")
        return 2
    client = StripeOwnerGateway(settings.stripe_secret_key).client
    today = datetime.now(local_timezone()).date()
    dataset = build_dataset(today)
    try:
        with translate_stripe_errors():
            inventory = find_seeded(client)
            if args.clean:
                clean(client, inventory, say)
                return 0
            if args.today_only:
                if not inventory.customers:
                    say("error: nothing seeded yet — run `make seed` first")
                    return 1
                run_id = f"today-{today.isoformat()}"
                by_name = {c.name: c.id for c in inventory.customers}
                ids = {c.key: by_name[c.name] for c in dataset.customers}
                say(f"Adding today's activity ({run_id})")
                ok, declined = create_payments(client, dataset.today_payments, ids, run_id, say)
                say(f"  {ok} payments, {declined} declines")
                return 0
            if inventory.customers and not args.force:
                say(f"Already seeded on {', '.join(sorted(inventory.seed_days))}. Nothing changed.")
                say("  --force re-seeds (charges from the old run remain), --today-only adds a fresh day.")
                print_report(dataset, [(c.name, c.bind_token) for c in inventory.customers], say)
                return 0
            if inventory.customers:
                say("Removing the previous seed…")
                clean(client, inventory, say)
            run_id = f"seed-{today.isoformat()}-{secrets.token_hex(3)}"
            say(f"Seeding {run_id} against API version {StripeOwnerGateway(settings.stripe_secret_key).api_version}")
            created = create_customers(client, dataset, run_id, say)
            ids = {key: c.id for key, c in created.items()}
            ok, declined = create_payments(client, dataset.payments, ids, run_id, say)
            say(f"  {ok} payments created, {declined} declined as intended")
            create_invoices(client, dataset, ids, run_id, say)
            print_report(dataset, [(c.name, c.bind_token) for c in created.values()], say)
            return 0
    except StripeGatewayError as exc:
        say(f"error: {exc}")
        if exc.hint:
            say(f"  hint: {exc.hint}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

Add to the `Makefile` (after `install`), and to `.PHONY`:

```make
seed:
	uv run python -m seed $(ARGS)
```

- [ ] **Step 6: Run tests, lint, then seed a real sandbox**

Run: `uv run pytest tests/test_seed_dataset.py -q && uv run ruff check .`
Expected: 3 passed; ruff clean.

Then against a fresh sandbox: `make seed` (2–4 minutes; ~130 Stripe writes). Expected: progress lines, then the report with figures and ten tokens. Run `make seed` again: "Already seeded … Nothing changed." and the same tokens. Verify in the Stripe dashboard that two payments show `insufficient_funds`. Record the printed figures — the README task uses them.

- [ ] **Step 7: Commit**

```bash
git add seed tests/test_seed_dataset.py Makefile
git commit -m "feat(seed): deterministic, idempotent sandbox seeding with detection, --force, --clean, --today-only"
```

### Task 15: Web app — scaffold, design tokens, API client, layout shell

**Files:**
- Create (via scaffold, then edit): `web/` from `npm create vite@latest web -- --template react-ts`; replace `web/index.html`, `web/vite.config.ts`, `web/src/main.tsx`, `web/src/App.tsx`, `web/src/vite-env.d.ts`; delete `web/src/App.css`, `web/src/index.css`, `web/src/assets/`
- Create: `web/src/styles.css`, `web/src/api/types.ts`, `web/src/api/client.ts`, `web/src/lib/money.ts`

**Interfaces:**
- Consumes: the API from Task 12 (proxied at `/api`), `OWNER_API_TOKEN` from the repo-root `.env` via Vite's `envDir: '..'` and `envPrefix` (one variable, one place).
- Produces: `AgentEvent`, `Confirmation`, `DailyFacts`, `Escalation`, `HistoryResponse` types; `apiFetch<T>(path, init?) -> Promise<T>` (throws `ApiError` carrying `code`/`hint`); `streamTurn(path, body, onEvent) -> Promise<void>`; `formatUsd(cents) -> string`; the page shell with header, two-column grid, and the CSS custom properties below.
- No frontend tests (per spec). Quality gate: `npm run build` (runs `tsc -b` then Vite) must pass.

**Design direction** (decided here so the three web tasks agree; the frontend-design skill's "avoid the three default looks" rule applies — this is neither cream-and-serif, nor black-with-acid-accent, nor hairline broadsheet):

- **Subject:** a small business owner's money desk. The page's job: read the day's summary, issue a command, and *watch it be carried out legibly*.
- **Signature element:** the **ledger trail** — the agent's steps rendered as ledger lines with a monospace gutter stamp (`PLAN`, `ACT`, `OBS`, `ASK`, `ERR`) and every amount set in tabular monospace. The trail is the product's honesty made visible.
- **Palette:** paper `#F6F7F9`, card `#FFFFFF`, ink `#141821`, ink-2 `#4B5160`, ink-3 `#8A8F98`, rule `#E1E4EA`, **ultramarine `#2B3FD6`** as the single interactive accent (soft `#E7EAFB`), money-in green `#1E7D4F` (soft `#E4F3EA`) and money-out red `#B7372E` (soft `#F8E6E4`) used only for amounts and status — semantic, never decorative; amber `#B9770E` for "waiting".
- **Type:** display *Bricolage Grotesque* (700, tight) for the wordmark and card titles; body *Instrument Sans*; data *JetBrains Mono* with `font-variant-numeric: tabular-nums` for every amount, id, and gutter stamp. Loaded from Google Fonts with system fallbacks.
- **Motion:** one gesture — new trail lines fade/slide in over 160 ms; the confirmation card's border pulses once. `prefers-reduced-motion` disables both.
- **Copy:** sentence case, plain verbs, names carried through the flow ("Approve refund" → "Refund approved"). Empty state invites: "Ask me to refund, invoice, or summarise."

- [ ] **Step 1: Scaffold and prune**

```bash
npm create vite@latest web -- --template react-ts
cd web && npm install && cd ..
rm web/src/App.css web/src/index.css && rm -rf web/src/assets web/public/vite.svg
```

- [ ] **Step 2: Configure Vite, HTML, and env typing**

`web/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The repo-root .env is the single place OWNER_API_TOKEN lives; Vite reads it
// from envDir and exposes only the prefixes listed here to the browser bundle.
export default defineConfig({
  plugins: [react()],
  envDir: "..",
  envPrefix: ["VITE_", "OWNER_API_TOKEN"],
  server: {
    port: 5173,
    proxy: { "/api": { target: "http://localhost:8000", changeOrigin: false } },
  },
});
```

`web/index.html`:

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Ledger — payments assistant</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Bricolage+Grotesque:opsz,wght@12..96,500;12..96,700&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
      rel="stylesheet"
    />
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`web/src/vite-env.d.ts`:

```ts
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly OWNER_API_TOKEN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
```

`web/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 3: Design tokens and base styles**

`web/src/styles.css`:

```css
:root {
  --paper: #f6f7f9; --card: #ffffff; --ink: #141821; --ink-2: #4b5160; --ink-3: #8a8f98; --rule: #e1e4ea;
  --accent: #2b3fd6; --accent-ink: #1f2fa6; --accent-soft: #e7eafb;
  --in: #1e7d4f; --in-soft: #e4f3ea; --out: #b7372e; --out-soft: #f8e6e4; --wait: #b9770e; --wait-soft: #f8eedc;
  --font-display: "Bricolage Grotesque", "Avenir Next", system-ui, sans-serif;
  --font-body: "Instrument Sans", "Helvetica Neue", Arial, sans-serif;
  --font-mono: "JetBrains Mono", ui-monospace, "SF Mono", Menlo, monospace;
  --radius: 10px; --shadow: 0 1px 2px rgba(20, 24, 33, 0.06), 0 8px 24px -16px rgba(20, 24, 33, 0.25);
}
* { box-sizing: border-box; }
html, body { margin: 0; background: var(--paper); color: var(--ink); font: 15px/1.5 var(--font-body); }
button, input, textarea { font: inherit; }
a { color: var(--accent-ink); }
.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.amount { font-family: var(--font-mono); font-variant-numeric: tabular-nums; font-weight: 500; }
.amount.in { color: var(--in); } .amount.out { color: var(--out); }

.shell { max-width: 1180px; margin: 0 auto; padding: 24px 20px 120px; }
.masthead { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 20px; }
.wordmark { font-family: var(--font-display); font-weight: 700; font-size: 28px; letter-spacing: -0.02em; margin: 0; }
.wordmark small { font-family: var(--font-body); font-weight: 500; color: var(--ink-3); font-size: 14px; margin-left: 10px; letter-spacing: 0; }
.dateline { color: var(--ink-3); font-family: var(--font-mono); font-size: 13px; }

.grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 24px; align-items: start; }
@media (max-width: 900px) { .grid { grid-template-columns: minmax(0, 1fr); } .rail { order: -1; } }

.card { background: var(--card); border: 1px solid var(--rule); border-radius: var(--radius); box-shadow: var(--shadow); padding: 18px 20px; }
.card h2 { font-family: var(--font-display); font-weight: 700; font-size: 17px; letter-spacing: -0.01em; margin: 0 0 10px; }
.eyebrow { font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-3); }
.pill { display: inline-block; padding: 2px 8px; border-radius: 999px; font-family: var(--font-mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.06em; }
.pill.open { background: var(--wait-soft); color: var(--wait); } .pill.paid { background: var(--in-soft); color: var(--in); }
.pill.void, .pill.failed { background: var(--out-soft); color: var(--out); } .pill.neutral { background: var(--accent-soft); color: var(--accent-ink); }

.btn { border: 1px solid var(--rule); background: var(--card); color: var(--ink); border-radius: 8px; padding: 8px 14px; cursor: pointer; }
.btn:hover { border-color: var(--ink-3); } .btn:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.btn.primary { background: var(--accent); border-color: var(--accent); color: white; } .btn.primary:hover { background: var(--accent-ink); }
.btn:disabled { opacity: 0.55; cursor: default; }

.thread { display: flex; flex-direction: column; gap: 14px; }
.turn.user { align-self: flex-end; max-width: 78%; background: var(--accent-soft); color: var(--accent-ink); padding: 10px 14px; border-radius: 14px 14px 4px 14px; }
.turn.assistant { display: flex; flex-direction: column; gap: 10px; }
.bubble { background: var(--card); border: 1px solid var(--rule); border-radius: 14px 14px 14px 4px; padding: 12px 16px; max-width: 78%; }

.trail { border-left: 2px solid var(--rule); margin-left: 6px; padding-left: 0; list-style: none; margin-top: 0; margin-bottom: 0; }
.trail li { display: grid; grid-template-columns: 52px minmax(0, 1fr); gap: 10px; padding: 3px 0 3px 12px; animation: rise 160ms ease-out both; }
.trail .stamp { font-family: var(--font-mono); font-size: 11px; letter-spacing: 0.08em; color: var(--ink-3); padding-top: 3px; }
.trail .stamp.act { color: var(--accent-ink); } .trail .stamp.ask { color: var(--wait); } .trail .stamp.err { color: var(--out); }
.trail .line { color: var(--ink-2); font-size: 14px; min-width: 0; }
.trail details summary { cursor: pointer; color: var(--ink-3); } .trail pre { margin: 6px 0 0; font-size: 12px; overflow-x: auto; background: var(--paper); padding: 8px; border-radius: 6px; }
@keyframes rise { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: none; } }

.confirm { border: 1px solid var(--wait); background: var(--wait-soft); border-radius: var(--radius); padding: 14px 16px; animation: pulse 900ms ease-out 1; }
.confirm .actions { display: flex; gap: 8px; margin-top: 10px; }
@keyframes pulse { 0% { box-shadow: 0 0 0 0 rgba(185, 119, 14, 0.35); } 100% { box-shadow: 0 0 0 12px rgba(185, 119, 14, 0); } }

.result { border-radius: var(--radius); border: 1px solid var(--rule); background: var(--card); padding: 14px 16px; }
.result .big { font-size: 28px; line-height: 1.1; margin: 6px 0; }
.kv { display: grid; grid-template-columns: max-content 1fr; gap: 4px 14px; font-size: 14px; } .kv dt { color: var(--ink-3); } .kv dd { margin: 0; }

.composer { position: sticky; bottom: 16px; display: flex; gap: 8px; background: var(--card); border: 1px solid var(--rule); border-radius: 14px; padding: 8px; box-shadow: var(--shadow); }
.composer input { flex: 1; border: 0; padding: 10px 12px; background: transparent; outline: none; }
.composer input::placeholder { color: var(--ink-3); }

.rail { display: flex; flex-direction: column; gap: 16px; }
.stat { display: flex; justify-content: space-between; align-items: baseline; padding: 6px 0; border-bottom: 1px solid var(--rule); } .stat:last-child { border-bottom: 0; }
.stat .label { color: var(--ink-2); font-size: 14px; }
.esc { padding: 10px 0; border-bottom: 1px solid var(--rule); } .esc:last-child { border-bottom: 0; }
.esc .meta { color: var(--ink-3); font-size: 13px; }
.empty { color: var(--ink-3); font-size: 14px; }
.error { color: var(--out); font-size: 14px; }

@media (prefers-reduced-motion: reduce) { .trail li, .confirm { animation: none; } }
```

- [ ] **Step 4: Types, client, money**

`web/src/api/types.ts`:

```ts
export type EventType = "planning" | "action" | "observation" | "confirmation" | "answer" | "clarify" | "error";

export interface AgentEvent {
  type: EventType;
  data: Record<string, unknown>;
}

export interface Confirmation {
  action_id: string;
  action: string;
  summary: string;
  parameters: Record<string, unknown>;
}

export interface PeriodTotals {
  label: string;
  succeeded_count: number;
  succeeded_total_cents: number;
  refunded_total_cents: number;
  declined_count: number;
  declined_reasons: Record<string, number>;
}

export interface OpenInvoiceFact {
  customer_name: string | null;
  number: string | null;
  amount_remaining_cents: number;
  due_date: string | null;
  overdue: boolean;
}

export interface DailyFacts {
  today: PeriodTotals;
  yesterday: PeriodTotals;
  open_invoices: OpenInvoiceFact[];
  open_invoice_total_cents: number;
  largest_payment: { customer_name: string | null; amount_cents: number; description: string | null } | null;
}

export interface SummaryResponse {
  facts: DailyFacts;
  text: string | null;
}

export interface Escalation {
  id: string;
  customer_name: string;
  invoice_id: string | null;
  amount_cents: number;
  reason: string;
  created_at: string;
}

export interface HistoryResponse {
  conversation_id: string;
  messages: { role: "user" | "assistant"; content: string; created_at: string }[];
  pending: Confirmation | null;
}

export interface ExecutedResult {
  action: string;
  data: Record<string, unknown>;
}
```

`web/src/api/client.ts`:

```ts
import type { AgentEvent } from "./types";

const TOKEN = import.meta.env.OWNER_API_TOKEN ?? "";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string, public hint: string) {
    super(message);
  }
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  return { Authorization: `Bearer ${TOKEN}`, "Content-Type": "application/json", ...extra };
}

async function raise(response: Response): Promise<never> {
  let code = "http_error", message = response.statusText, hint = "";
  try {
    const body = await response.json();
    code = body.error?.code ?? code; message = body.error?.message ?? message; hint = body.error?.hint ?? "";
  } catch { /* non-JSON error body */ }
  throw new ApiError(response.status, code, message, hint);
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(path, { ...init, headers: headers((init.headers as Record<string, string>) ?? {}) });
  if (!response.ok) await raise(response);
  return (await response.json()) as T;
}

// POST + SSE. EventSource only speaks GET, so parse the stream by hand:
// frames are separated by a blank line; each has `event:` and `data:` lines.
export async function streamTurn(
  path: string,
  body: unknown,
  onEvent: (event: AgentEvent) => void,
  extraHeaders: Record<string, string> = {},
): Promise<void> {
  const response = await fetch(path, { method: "POST", headers: headers(extraHeaders), body: JSON.stringify(body) });
  if (!response.ok || !response.body) await raise(response);
  const reader = response.body!.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let boundary: number;
    while ((boundary = buffer.indexOf("\n\n")) !== -1) {
      const frame = buffer.slice(0, boundary);
      buffer = buffer.slice(boundary + 2);
      let type = "message", data = "";
      for (const line of frame.split("\n")) {
        if (line.startsWith("event:")) type = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) onEvent({ type: type as AgentEvent["type"], data: JSON.parse(data) });
    }
  }
}
```

`web/src/lib/money.ts`:

```ts
// The browser-side twin of app/domain/money.py. Cents in, dollars out, nothing else.
export function formatUsd(cents: number): string {
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}$${Math.floor(abs / 100).toLocaleString("en-US")}.${String(abs % 100).padStart(2, "0")}`;
}
```

- [ ] **Step 5: The shell**

`web/src/App.tsx` (placeholder content is replaced in Tasks 16–17; this version must build):

```tsx
export default function App() {
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  return (
    <div className="shell">
      <header className="masthead">
        <h1 className="wordmark">Ledger <small>payments assistant</small></h1>
        <span className="dateline">{today}</span>
      </header>
      <main className="grid">
        <section className="thread" aria-label="Conversation">
          <p className="empty">Ask me to refund, invoice, or summarise.</p>
        </section>
        <aside className="rail" aria-label="Today and escalations" />
      </main>
    </div>
  );
}
```

- [ ] **Step 6: Build**

Run: `cd web && npm run build && cd ..`
Expected: `tsc -b` clean, Vite writes `web/dist/`. Then `make install` (root) succeeds end to end.

- [ ] **Step 7: Commit**

```bash
git add web Makefile
git commit -m "feat(web): Vite React scaffold with design tokens, API client, and SSE parser"
```

### Task 16: Web app — conversation state, composer, ledger trail, confirmation and result cards

**Files:**
- Create: `web/src/state/useConversation.ts`, `web/src/components/Composer.tsx`, `web/src/components/Trail.tsx`, `web/src/components/ConfirmationCard.tsx`, `web/src/components/ResultCard.tsx`
- Modify: `web/src/App.tsx`

**Interfaces:**
- Consumes: `streamTurn`, `apiFetch`, types (Task 15).
- Produces: `useConversation()` returning `{ turns, busy, error, send(text), approve(actionId), cancel(actionId), onMutation: (cb) => void }`; `Turn` type `{ id, role, text?, events, confirmation?, decided?: "approved" | "cancelled", result?, error? }`; components `Composer({ onSend, disabled })`, `Trail({ events })`, `ConfirmationCard({ confirmation, decided, onApprove, onCancel, busy })`, `ResultCard({ result })`.

- [ ] **Step 1: Conversation state**

`web/src/state/useConversation.ts`:

```ts
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, apiFetch, streamTurn } from "../api/client";
import type { AgentEvent, Confirmation, ExecutedResult, HistoryResponse } from "../api/types";

export interface Turn {
  id: string;
  role: "user" | "assistant";
  text?: string;
  events: AgentEvent[];
  confirmation?: Confirmation;
  decided?: "approved" | "cancelled";
  result?: ExecutedResult;
  error?: string;
}

const KEY = "ledger.conversation";

function conversationId(): string {
  try {
    const existing = localStorage.getItem(KEY);
    if (existing) return existing;
    const fresh = crypto.randomUUID();
    localStorage.setItem(KEY, fresh);
    return fresh;
  } catch {
    return crypto.randomUUID();
  }
}

function describe(error: unknown): string {
  if (error instanceof ApiError) return error.hint ? `${error.message} ${error.hint}` : error.message;
  return error instanceof Error ? error.message : String(error);
}

export function useConversation() {
  const id = useRef(conversationId());
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mutationListeners = useRef<(() => void)[]>([]);

  const onMutation = useCallback((cb: () => void) => { mutationListeners.current.push(cb); }, []);
  const notifyMutation = () => mutationListeners.current.forEach((cb) => cb());

  const patch = (turnId: string, fn: (t: Turn) => Turn) =>
    setTurns((prev) => prev.map((t) => (t.id === turnId ? fn(t) : t)));

  useEffect(() => {
    apiFetch<HistoryResponse>(`/api/conversations/${id.current}`)
      .then((history) => {
        const restored: Turn[] = history.messages.map((m, i) => ({ id: `h${i}`, role: m.role, text: m.content, events: [] }));
        if (history.pending) restored.push({ id: history.pending.action_id, role: "assistant", events: [], confirmation: history.pending });
        setTurns(restored);
      })
      .catch((e) => setError(describe(e)));
  }, []);

  // Route one SSE event into the assistant turn being built.
  const absorb = (turnId: string, event: AgentEvent) =>
    patch(turnId, (t) => {
      const next: Turn = { ...t, events: [...t.events, event] };
      if (event.type === "answer") { next.text = String(event.data.text); if (event.data.result) next.result = event.data.result as ExecutedResult; }
      if (event.type === "clarify") next.text = String(event.data.question);
      if (event.type === "confirmation") next.confirmation = event.data as unknown as Confirmation;
      if (event.type === "error" && !event.data.recoverable) next.error = String(event.data.message);
      return next;
    });

  const send = useCallback(async (text: string) => {
    const userId = crypto.randomUUID(), assistantId = crypto.randomUUID();
    setTurns((prev) => [...prev, { id: userId, role: "user", text, events: [] }, { id: assistantId, role: "assistant", events: [] }]);
    setBusy(true); setError(null);
    try {
      await streamTurn(`/api/conversations/${id.current}/messages`, { text }, (e) => absorb(assistantId, e));
    } catch (e) {
      patch(assistantId, (t) => ({ ...t, error: describe(e) }));
    } finally {
      setBusy(false);
    }
  }, []);

  const approve = useCallback(async (actionId: string) => {
    const resultId = crypto.randomUUID();
    patch(actionId, (t) => ({ ...t, decided: "approved" }));
    setTurns((prev) => [...prev, { id: resultId, role: "assistant", events: [] }]);
    setBusy(true);
    try {
      await streamTurn(`/api/conversations/${id.current}/confirm`, { action_id: actionId },
        (e) => absorb(resultId, e), { "Idempotency-Key": actionId });
      notifyMutation();
    } catch (e) {
      patch(resultId, (t) => ({ ...t, error: describe(e) }));
    } finally {
      setBusy(false);
    }
  }, []);

  const cancel = useCallback(async (actionId: string) => {
    try {
      await apiFetch(`/api/conversations/${id.current}/cancel`, { method: "POST", body: JSON.stringify({ action_id: actionId }) });
      patch(actionId, (t) => ({ ...t, decided: "cancelled" }));
    } catch (e) {
      setError(describe(e));
    }
  }, []);

  return { turns, busy, error, send, approve, cancel, onMutation };
}
```

Note: confirmation turns are keyed by `action_id` so `approve`/`cancel` can patch them; when a confirmation event arrives, re-key that turn: in `absorb`, when `event.type === "confirmation"`, also `setTurns(prev => prev.map(t => t.id === turnId ? { ...t, id: String(event.data.action_id) } : t))` after the patch. Implement that as a second `setTurns` inside the `confirmation` branch.

- [ ] **Step 2: Components**

`web/src/components/Composer.tsx`:

```tsx
import { useState, type FormEvent } from "react";

export function Composer({ onSend, disabled }: { onSend: (text: string) => void; disabled: boolean }) {
  const [text, setText] = useState("");
  const submit = (e: FormEvent) => {
    e.preventDefault();
    const trimmed = text.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setText("");
  };
  return (
    <form className="composer" onSubmit={submit}>
      <input
        aria-label="Command"
        placeholder="Refund Maya's last payment"
        value={text}
        onChange={(e) => setText(e.target.value)}
        disabled={disabled}
        autoFocus
      />
      <button className="btn primary" type="submit" disabled={disabled || !text.trim()}>
        {disabled ? "Working…" : "Send"}
      </button>
    </form>
  );
}
```

`web/src/components/Trail.tsx`:

```tsx
import type { JSX } from "react";
import type { AgentEvent } from "../api/types";

const STAMP: Record<AgentEvent["type"], { label: string; cls: string }> = {
  planning: { label: "PLAN", cls: "" }, action: { label: "ACT", cls: "act" }, observation: { label: "OBS", cls: "" },
  confirmation: { label: "ASK", cls: "ask" }, answer: { label: "SAY", cls: "" }, clarify: { label: "ASK", cls: "ask" },
  error: { label: "ERR", cls: "err" },
};

function line(event: AgentEvent): JSX.Element {
  const d = event.data;
  switch (event.type) {
    case "planning": return <span>{String(d.reasoning)}</span>;
    case "action": return <span><span className="mono">{String(d.name)}</span> {JSON.stringify(d.args)}</span>;
    case "observation": return (
      <details><summary>{String(d.name)} returned</summary><pre className="mono">{JSON.stringify(d.result, null, 2)}</pre></details>
    );
    case "confirmation": return <span>Waiting for your approval</span>;
    case "error": return <span>{String(d.message)}{d.hint ? ` — ${String(d.hint)}` : ""}</span>;
    default: return <span />;
  }
}

export function Trail({ events }: { events: AgentEvent[] }) {
  const shown = events.filter((e) => e.type !== "answer" && e.type !== "clarify");
  if (!shown.length) return null;
  return (
    <ul className="trail" aria-label="Agent activity">
      {shown.map((e, i) => (
        <li key={i}>
          <span className={`stamp ${STAMP[e.type].cls}`}>{STAMP[e.type].label}</span>
          <div className="line">{line(e)}</div>
        </li>
      ))}
    </ul>
  );
}
```

`web/src/components/ConfirmationCard.tsx`:

```tsx
import type { Confirmation } from "../api/types";

const VERB: Record<string, string> = {
  refund_payment: "Approve refund", create_invoice: "Create invoice", create_payment_link: "Create link",
  approve_escalation: "Approve and notify",
};

export function ConfirmationCard({ confirmation, decided, busy, onApprove, onCancel }: {
  confirmation: Confirmation; decided?: "approved" | "cancelled"; busy: boolean;
  onApprove: () => void; onCancel: () => void;
}) {
  return (
    <div className="confirm" role="group" aria-label="Confirmation">
      <div className="eyebrow">Needs your approval</div>
      <div>{confirmation.summary}</div>
      {decided ? (
        <div className="eyebrow" style={{ marginTop: 8 }}>{decided === "approved" ? "Approved" : "Cancelled"}</div>
      ) : (
        <div className="actions">
          <button className="btn primary" onClick={onApprove} disabled={busy}>{VERB[confirmation.action] ?? "Approve"}</button>
          <button className="btn" onClick={onCancel} disabled={busy}>Cancel</button>
        </div>
      )}
    </div>
  );
}
```

`web/src/components/ResultCard.tsx`:

```tsx
import type { ExecutedResult } from "../api/types";
import { formatUsd } from "../lib/money";

export function ResultCard({ result }: { result: ExecutedResult }) {
  const d = result.data as Record<string, any>;
  switch (result.action) {
    case "refund_payment":
      return (
        <div className="result">
          <div className="eyebrow">Refund issued</div>
          <div className="big amount out">−{formatUsd(Number(d.amount_cents))}</div>
          <dl className="kv"><dt>To</dt><dd>{d.customer_name ?? "customer"}</dd><dt>Refund</dt><dd className="mono">{d.refund_id}</dd><dt>Status</dt><dd><span className="pill paid">{d.status}</span></dd></dl>
        </div>
      );
    case "create_invoice":
      return (
        <div className="result">
          <div className="eyebrow">Invoice created</div>
          <div className="big amount">{formatUsd(Number(d.total_cents))}</div>
          <dl className="kv"><dt>Customer</dt><dd>{d.customer_name}</dd><dt>Number</dt><dd className="mono">{d.number}</dd><dt>Due</dt><dd className="mono">{d.due_date}</dd><dt>Status</dt><dd><span className={`pill ${d.status}`}>{d.status}</span></dd>
          {d.hosted_url && <><dt>Link</dt><dd><a href={d.hosted_url} target="_blank" rel="noreferrer">Hosted invoice</a></dd></>}</dl>
        </div>
      );
    case "create_payment_link":
      return (
        <div className="result">
          <div className="eyebrow">Payment link</div>
          <div className="big amount">{formatUsd(Number(d.amount_cents))}</div>
          <dl className="kv"><dt>For</dt><dd>{d.description}</dd><dt>URL</dt><dd><a className="mono" href={d.url} target="_blank" rel="noreferrer">{d.url}</a></dd></dl>
        </div>
      );
    case "approve_escalation":
      return (
        <div className="result">
          <div className="eyebrow">Escalation approved</div>
          <dl className="kv"><dt>Customer</dt><dd>{d.customer_name}</dd><dt>Amount</dt><dd className="amount">{formatUsd(Number(d.amount_cents))}</dd><dt>Telegram</dt><dd><span className={`pill ${d.notified ? "paid" : "failed"}`}>{d.notified ? "notified" : "not delivered"}</span></dd></dl>
        </div>
      );
    default:
      return <pre className="result mono">{JSON.stringify(d, null, 2)}</pre>;
  }
}
```

- [ ] **Step 3: Wire the thread into `App.tsx`**

Replace `web/src/App.tsx`:

```tsx
import { useConversation } from "./state/useConversation";
import { Composer } from "./components/Composer";
import { Trail } from "./components/Trail";
import { ConfirmationCard } from "./components/ConfirmationCard";
import { ResultCard } from "./components/ResultCard";

export default function App() {
  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
  const { turns, busy, error, send, approve, cancel } = useConversation();
  return (
    <div className="shell">
      <header className="masthead">
        <h1 className="wordmark">Ledger <small>payments assistant</small></h1>
        <span className="dateline">{today}</span>
      </header>
      <main className="grid">
        <section aria-label="Conversation">
          <div className="thread">
            {turns.length === 0 && <p className="empty">Ask me to refund, invoice, or summarise.</p>}
            {turns.map((t) =>
              t.role === "user" ? (
                <div key={t.id} className="turn user">{t.text}</div>
              ) : (
                <div key={t.id} className="turn assistant">
                  <Trail events={t.events} />
                  {t.confirmation && (
                    <ConfirmationCard confirmation={t.confirmation} decided={t.decided} busy={busy}
                      onApprove={() => approve(t.confirmation!.action_id)} onCancel={() => cancel(t.confirmation!.action_id)} />
                  )}
                  {t.result && <ResultCard result={t.result} />}
                  {t.text && <div className="bubble">{t.text}</div>}
                  {t.error && <div className="error">{t.error}</div>}
                </div>
              ),
            )}
            {error && <div className="error">{error}</div>}
          </div>
          <div style={{ height: 16 }} />
          <Composer onSend={send} disabled={busy} />
        </section>
        <aside className="rail" aria-label="Today and escalations" />
      </main>
    </div>
  );
}
```

- [ ] **Step 4: Build and try it against the running API**

Run: `cd web && npm run build && cd ..` — expected clean. Then with the API running (`uv run uvicorn app.main:app --port 8000`) and `cd web && npm run dev`: open http://localhost:5173, send "who is maya", watch `PLAN → ACT → OBS → SAY` appear; send "refund Maya's last payment", see the confirmation card, click **Approve refund**, see the receipt card. Reload: the transcript is restored.

- [ ] **Step 5: Commit**

```bash
git add web/src
git commit -m "feat(web): conversation thread with live ledger trail, confirmation and result cards"
```

### Task 17: Web app — summary on load, today rail, escalations panel

**Files:**
- Create: `web/src/components/SummaryCard.tsx`, `web/src/components/TodayRail.tsx`, `web/src/components/EscalationsPanel.tsx`
- Modify: `web/src/App.tsx`

**Interfaces:**
- Consumes: `apiFetch`, `SummaryResponse`, `DailyFacts`, `Escalation`, `useConversation().onMutation`.
- Produces: `SummaryCard({ summary, loading, error })`, `TodayRail({ facts })`, `EscalationsPanel({ escalations, onApprove, busyId })`.

- [ ] **Step 1: Components**

`web/src/components/SummaryCard.tsx`:

```tsx
import type { SummaryResponse } from "../api/types";

export function SummaryCard({ summary, loading, error }: { summary: SummaryResponse | null; loading: boolean; error: string | null }) {
  return (
    <div className="card" aria-live="polite">
      <div className="eyebrow">Today, in a sentence</div>
      <h2>Good {new Date().getHours() < 12 ? "morning" : "afternoon"}.</h2>
      {loading && <p className="empty">Reading today's activity…</p>}
      {error && <p className="error">{error}</p>}
      {summary?.text && <p style={{ fontSize: 17, margin: 0 }}>{summary.text}</p>}
    </div>
  );
}
```

`web/src/components/TodayRail.tsx`:

```tsx
import type { DailyFacts } from "../api/types";
import { formatUsd } from "../lib/money";

export function TodayRail({ facts }: { facts: DailyFacts | null }) {
  if (!facts) return <div className="card"><div className="eyebrow">Today</div><p className="empty">Loading…</p></div>;
  const declined = Object.entries(facts.today.declined_reasons).map(([r, n]) => `${n} ${r.replace(/_/g, " ")}`).join(", ");
  return (
    <div className="card">
      <div className="eyebrow">Today · {facts.today.label}</div>
      <div className="stat"><span className="label">Taken</span><span className="amount in">{formatUsd(facts.today.succeeded_total_cents)}</span></div>
      <div className="stat"><span className="label">Payments</span><span className="mono">{facts.today.succeeded_count}</span></div>
      <div className="stat"><span className="label">Refunded</span><span className="amount out">{formatUsd(facts.today.refunded_total_cents)}</span></div>
      <div className="stat"><span className="label">Declined</span><span className="mono" title={declined}>{facts.today.declined_count}</span></div>
      <div className="stat"><span className="label">Yesterday</span><span className="amount">{formatUsd(facts.yesterday.succeeded_total_cents)}</span></div>
      <div className="stat"><span className="label">Unpaid invoices</span><span className="amount">{formatUsd(facts.open_invoice_total_cents)}</span></div>
    </div>
  );
}
```

`web/src/components/EscalationsPanel.tsx`:

```tsx
import type { Escalation } from "../api/types";
import { formatUsd } from "../lib/money";

export function EscalationsPanel({ escalations, onApprove, busyId }: {
  escalations: Escalation[]; onApprove: (id: string) => void; busyId: string | null;
}) {
  return (
    <div className="card">
      <div className="eyebrow">Escalations</div>
      <h2>Waiting on you</h2>
      {escalations.length === 0 && <p className="empty">Nothing waiting. Customers above the bot's limit will appear here.</p>}
      {escalations.map((e) => (
        <div className="esc" key={e.id}>
          <div><strong>{e.customer_name}</strong> {e.amount_cents > 0 && <span className="amount">{formatUsd(e.amount_cents)}</span>}</div>
          <div className="meta">{e.reason} · {new Date(e.created_at + "Z").toLocaleString()}</div>
          <button className="btn primary" style={{ marginTop: 8 }} onClick={() => onApprove(e.id)} disabled={busyId === e.id}>
            {busyId === e.id ? "Approving…" : "Approve and notify"}
          </button>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Load, refresh after mutations, wire the rail**

In `web/src/App.tsx` add state and effects (keep everything from Task 16 and add):

```tsx
import { useCallback, useEffect, useState } from "react";
import { ApiError, apiFetch } from "./api/client";
import type { DailyFacts, Escalation, SummaryResponse } from "./api/types";
import { SummaryCard } from "./components/SummaryCard";
import { TodayRail } from "./components/TodayRail";
import { EscalationsPanel } from "./components/EscalationsPanel";
```

Inside `App()`, after `useConversation()`:

```tsx
  const { turns, busy, error, send, approve, cancel, onMutation } = useConversation();
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [facts, setFacts] = useState<DailyFacts | null>(null);
  const [summaryError, setSummaryError] = useState<string | null>(null);
  const [escalations, setEscalations] = useState<Escalation[]>([]);
  const [approving, setApproving] = useState<string | null>(null);

  const refreshFacts = useCallback(() => {
    apiFetch<SummaryResponse>("/api/summary/today?narrate=false").then((s) => setFacts(s.facts)).catch(() => undefined);
    apiFetch<Escalation[]>("/api/escalations").then(setEscalations).catch(() => undefined);
  }, []);

  useEffect(() => {
    apiFetch<SummaryResponse>("/api/summary/today")
      .then((s) => { setSummary(s); setFacts(s.facts); })
      .catch((e) => setSummaryError(e instanceof ApiError && e.hint ? `${e.message} ${e.hint}` : String(e)));
    apiFetch<Escalation[]>("/api/escalations").then(setEscalations).catch(() => undefined);
    onMutation(refreshFacts);
    const timer = setInterval(refreshFacts, 30_000);
    return () => clearInterval(timer);
  }, [onMutation, refreshFacts]);

  const approveEscalation = async (id: string) => {
    setApproving(id);
    try { await apiFetch(`/api/escalations/${id}/approve`, { method: "POST" }); refreshFacts(); }
    finally { setApproving(null); }
  };
```

Render: put `<SummaryCard summary={summary} loading={!summary && !summaryError} error={summaryError} />` as the first child inside the conversation `<section>` (above `.thread`), and fill the aside:

```tsx
        <aside className="rail" aria-label="Today and escalations">
          <TodayRail facts={facts} />
          <EscalationsPanel escalations={escalations} onApprove={approveEscalation} busyId={approving} />
        </aside>
```

- [ ] **Step 3: Build and walk the whole owner flow**

Run: `cd web && npm run build && cd ..` — expected clean.
With API + web dev server running against a seeded sandbox: the summary paragraph renders on load; the rail shows today's total; "How much did we take last week compared to the week before?" answers with dates; "Create a $250 invoice for Acme Corp due next Friday" → confirmation → **Create invoice** → invoice card with an open pill; the rail's "Unpaid invoices" figure rises after the refresh. Resize to 800 px wide: the rail moves above the thread; nothing scrolls horizontally.

- [ ] **Step 4: Commit**

```bash
git add web/src
git commit -m "feat(web): daily summary on load, live today rail, escalations panel"
```

### Task 18: `make dev`, the end-to-end walkthrough, README, write-up, and docs

**Files:**
- Create: `scripts/dev.sh`, `write-up.md`
- Modify: `Makefile` (add `dev`), `README.md` (replace the brief copy with the deliverable README), `CLAUDE.md` (status + commands), `documentation/index.md` (no change needed — the plan is already linked)

**Interfaces:**
- Consumes: everything.
- Produces: the reviewer-facing deliverables. `make dev` runs API + bot + web together.

- [ ] **Step 1: `scripts/dev.sh` and the `dev` target**

`scripts/dev.sh` (then `chmod +x scripts/dev.sh`):

```bash
#!/usr/bin/env bash
#
# Run the API, the Telegram bot, and the web dev server together.
# One Ctrl-C stops all three. The bot is skipped politely if no token is set.
set -euo pipefail
cd "$(dirname "$0")/.."

trap 'kill 0' EXIT INT TERM

uv run uvicorn app.main:app --port 8000 --reload &
uv run python -m app.telegram.bot &
( cd web && npm run dev ) &
wait
```

Add to the `Makefile` (and to `.PHONY`):

```make
dev:
	./scripts/dev.sh
```

- [ ] **Step 2: Full-system walkthrough against a seeded sandbox**

With `.env` complete (Stripe test key, one LLM key, bot token from agent-vault `replicant-assignment-telegram-bot-token`, `OWNER_API_TOKEN=dev-owner-token`) and the sandbox seeded, run `make dev` and verify each line; fix before proceeding:

1. Web app on http://localhost:5173 renders the narrated summary; the rail's figures match the seed report.
2. "How much did we take last week compared to the week before?" → answer states the date ranges it compared.
3. "Refund Maya's last payment" → trail shows find_customer/query_payments, confirmation card names Maya and the amount → Approve → receipt card; `GET /api/audit` shows the mutation with the prompt.
4. Telegram: `/start <acme token>` binds; "what do I owe?" → amount-free reply with View/Pay buttons.
5. Pay the smaller Acme invoice ($1,200): Pay → confirm message with the amount → Confirm → receipt button; the web rail's "Taken" figure rises on next refresh.
6. Ask the bot to pay the $2,400 licence invoice → escalation message, no payment; the web Escalations panel shows Acme → Approve and notify → the Telegram chat receives the Stripe link; paying it on the hosted page (card 4242 4242 4242 4242) completes the loop.
7. "what does Maya Chen owe?" to the bot → the bot declines to discuss other customers.
8. `/logout` disconnects; a further message asks to connect.
9. Kill the LLM key in `.env`, restart, send a message → a clear `llm_error` with a hint, not a stack trace. Restore the key.

- [ ] **Step 3: Write `README.md`** (replacing the brief copy — the brief lives in `documentation/assignment-brief.md`)

Contents, in this order (write it as finished prose, not this outline):

- **Title + one-paragraph pitch:** an AI payments assistant over Stripe — owner chat web app, customer Telegram bot, one seed command; the agent is a propose→execute→narrate loop where every guardrail is Python, not prompt text.
- **Architecture overview** (~half a page): the diagram from the design spec (ASCII), then five bullets: LLM proposes one validated JSON action per step and deterministic Python executes it; two registries share one executor and the bot's registry has no action taking a `customer_id`; mutations pause as stored confirmations and approval executes the stored action; the $2,000 ceiling and binding expiry live in `app/domain/policy.py`; Stripe is the source of truth, SQLite holds conversations/confirmations/bindings/escalations/audit.
- **API design choices** (the brief asks for this explicitly): resource-shaped state + conversational intent; SSE typed events (`planning/action/observation/confirmation/answer`) because the loop's dispatch is ours to stream; confirmation as a resource with `Idempotency-Key` passthrough; `{error: {code, message, hint}}` envelope; single `OWNER_API_TOKEN` bearer auth. Include the route table from the design spec plus `POST /api/conversations/{id}/cancel` and `GET /api/summary/today?narrate=false`.
- **Setup** (step-by-step, numbered): prerequisites (uv, Node 20+, a Stripe test account, one LLM key, a Telegram bot from @BotFather); `cp .env.example .env` and fill each variable (say where each comes from); `make install`; `make seed` (what it creates, that it prints the binding tokens and today's expected figures, that re-running is safe, `--force` / `--clean` / `--today-only` semantics, and that seeded history carries `metadata.demo_created_at` read in exactly one mapping function); `make dev` (which ports); how to bind Telegram (`/start <token>` or `https://t.me/<your-bot>?start=<token>`).
- **Demo script** (so the reviewer's first fifteen minutes are scripted): the walkthrough from Step 2, items 1–6, phrased as things to type.
- **Testing:** `make test` (no network, no LLM — fakes at the gateway and backend protocols), what the load-bearing tests prove (ceiling before any Stripe call, scoped client isolation, stored-action confirmation, `occurred_at` concession, executor validation), and `uv run pytest -m live_llm` for the one live smoke test.
- **Notes:** today's seed figures vary with the calendar (amounts are drawn deterministically but the history layout depends on weekdays), so the seed report is the source of the exact numbers; the fixed fixtures are 18 payments + 2 `insufficient_funds` declines today, Acme's open $1,200 invoice, and the $2,400 invoice that escalates.

- [ ] **Step 4: Write `write-up.md`**

Sections, written as finished prose (the reasoning is in the design spec — condense, don't invent):

- **Assumptions:** single owner, single currency (USD), demo-scale data (list-and-filter over Stripe pagination is fine at ~150 objects); the reviewer runs seed and app on the same machine and, ideally, the same day (`--today-only` covers the next morning); Telegram identity is an identifier, not an authenticator — binding tokens are minted by the seed because seeded customers have unreceivable email addresses.
- **Challenges:** Stripe assigns `created` and offers no import (CSV import doesn't exist for charges; test clocks cap at three customers per clock, expire in about seven days, and are built for subscription lifecycles) → the `metadata.demo_created_at` concession, confined to one mapping function; making declines real (`pm_card_chargeDeclinedInsufficientFunds`, a genuine `insufficient_funds` outcome) rather than faked records; keeping two processes on one SQLite file honest (WAL + short transactions + claim-once conditional UPDATE).
- **Limitations / with more time:** native tool calling (deliberately not used — legibility, portability, testability; at ~10 actions the reliability gap doesn't bite, at 50 it would); webhooks instead of on-demand queries (needs a tunnel); email verification for binding; session auth, multi-owner, rate limiting; frontend tests; Stripe pagination beyond demo scale.
- **Bonus — the escalation loop:** why it was chosen (it is Replicant's own product pattern in miniature: automation handles tier one, escalates cleanly to a human, resumes), and that it doubles as the security answer for high-stakes actions — out-of-band owner approval rather than another code sent to a possibly compromised device.

- [ ] **Step 5: Update `CLAUDE.md`**

- Change the status line to: implementation complete; the design of record is unchanged.
- In **Commands**, replace the placeholder sentence with the real four commands now that they work (`make install`, `make seed` with its flags, `make dev`, `make test`, `make lint`), keeping `./scripts/check-docs.sh`.

- [ ] **Step 6: Docs check, full gates, final commit**

Run: `./scripts/check-docs.sh && uv run pytest -q && uv run ruff check . && (cd web && npm run build)`
Expected: all clean.

```bash
git add scripts/dev.sh Makefile README.md write-up.md CLAUDE.md
git commit -m "docs: deliverable README and write-up; make dev runs all three processes"
```

---

## Execution notes

- **Order matters:** tasks are dependency-ordered; do not start a task before the previous one's tests pass and its commit exists.
- **Ambient rules:** `.claude/rules/code-style.md` applies to every `.py`/`.ts`/`.tsx` file here; the Global Constraints section restates the enforceable core. When in doubt, the vault's `code-conventions.md` wins.
- **The five load-bearing claims** (from the design spec §10) and where this plan proves them:
  1. Bot rejects ≥ $2,000 before any Stripe call → `tests/test_customer_actions.py`
  2. Scoped client cannot reach another customer's data → `tests/test_scoped_gateway.py` (+ registry test in `tests/test_customer_actions.py`)
  3. Confirmed action executes the stored action, not a re-plan → `tests/test_confirm.py` (+ API-level in `tests/test_api.py`)
  4. `occurred_at` prefers `demo_created_at`, falls back to `created` → `tests/test_mapping.py`
  5. Executor rejects malformed or unknown actions → `tests/test_executor.py`
- **Live-service steps** (seed run, `make dev` walkthrough, Telegram poll) need real keys in `.env`; the Telegram token is in agent-vault under `replicant-assignment-telegram-bot-token`. Everything else runs offline.
