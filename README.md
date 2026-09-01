# AI payments assistant

An AI assistant over a Stripe account, in three parts: a FastAPI backend with
a React chat UI for the business owner, a Telegram bot for their customers,
and a seed command that populates a fresh Stripe sandbox with a believable
history. Every turn is a propose → execute → narrate loop: the LLM proposes
one action as validated JSON, deterministic Python executes it, and the LLM
narrates the typed result. The guardrails that matter — the $2,000 Telegram
payment ceiling and per-customer data scoping — are Python invariants
enforced by the executor, never instructions in a prompt.

This assessment's original brief is preserved verbatim at
[`documentation/assignment-brief.md`](documentation/assignment-brief.md);
this file replaces the copy of it that used to live here. The design of
record, including the reasoning behind every choice below, is
[`documentation/specs/2026-09-01-ai-payments-assistant-design.md`](documentation/specs/2026-09-01-ai-payments-assistant-design.md).

## Architecture

```
                    ┌──────────────┐
   owner ──────────>│  React SPA   │──── SSE ────┐
                    └──────────────┘             │
                                                 ▼
   customer ───────>┌──────────────┐      ┌─────────────┐      ┌────────┐
                    │ Telegram bot │─────>│   FastAPI   │─────>│ Stripe │
                    └──────────────┘      │   backend   │      └────────┘
                                          └─────────────┘
                                             │       │
                                        ┌────▼──┐ ┌──▼──────┐
                                        │SQLite │ │   LLM   │
                                        └───────┘ └─────────┘
```

- The LLM proposes exactly one validated JSON action per step; deterministic
  Python executes it and returns a typed observation. This is an agent
  loop — capped at five iterations — with the dispatch in our hands rather
  than a provider SDK's, which is what makes every step streamable and
  testable without a model in the loop.
- Two action registries — owner and customer — share one executor. The
  bot's registry contains no action that takes a `customer_id` parameter, so
  a prompt injection asking it to read another customer's invoices finds no
  action to call and no parameter to fill.
- A proposed mutation is resolved fully, then stored and returned for
  approval with concrete details ("Refund $45.00 to Maya Chen"). Approval
  executes **the stored action**, never a freshly re-planned one — the model
  cannot substitute a different action between proposal and execution.
- The $2,000 payment ceiling and the 14-day binding expiry are each defined
  once, in `app/domain/policy.py`, and imported everywhere they apply.
- Stripe is the source of truth for money. SQLite holds only what Stripe
  cannot: conversations, pending confirmations, Telegram bindings,
  escalations, and the audit log.

## API design choices

The API is resource-shaped for state and conversational for intent: a turn
is a POST that streams Server-Sent Events, but the state it produces —
conversations, confirmations, escalations, the audit trail — lives behind
real resources any client can inspect on its own.

- **Typed SSE events**, not a spinner: `planning`, `action`, `observation`,
  `confirmation`, `answer`, `clarify`, and `error`. Because the agent's
  dispatch is ours, every step it takes is an event worth showing.
- **Confirmation as a resource, not a dialog.** A `confirmation` event
  carries a server-stored `action_id`; approving it executes that stored
  action rather than asking the model to plan again.
- **`Idempotency-Key` passthrough** on mutating routes, forwarded to Stripe,
  so a double-clicked approval cannot refund or charge twice.
- **Errors carry a fix.** Every error is `{error: {code, message, hint}}` —
  "set `STRIPE_SECRET_KEY` in `.env`", not "unauthorized" — and SSE error
  frames carry the same three fields.
- **Auth** is a single `OWNER_API_TOKEN` bearer token required on every
  `/api/*` route, shipped with a working local default in `.env.example` so
  it costs the reviewer nothing to run.

| Method | Path | Purpose |
| --- | --- | --- |
| `POST` | `/api/conversations/{id}/messages` | Send a turn; streams SSE |
| `POST` | `/api/conversations/{id}/confirm` | Approve a pending mutation; streams SSE |
| `POST` | `/api/conversations/{id}/cancel` | Dismiss a pending mutation |
| `GET` | `/api/conversations/{id}` | Transcript, plus any still-pending proposal |
| `GET` | `/api/summary/today` | Daily summary, narrated by the LLM |
| `GET` | `/api/summary/today?narrate=false` | The same facts with no LLM call, for the live rail |
| `GET` | `/api/escalations` | Payments waiting on the owner |
| `POST` | `/api/escalations/{id}/approve` | Approve one; notifies the customer |
| `DELETE` | `/api/customers/{id}/telegram-binding` | Owner-side revoke of a customer's bot binding |
| `GET` | `/api/audit` | Every action taken, and the prompt that produced it |

`POST /api/conversations/{id}/cancel` and the `narrate=false` variant of the
summary route are additions beyond the design spec's original eight: cancel
lets a reviewer dismiss a proposal instead of leaving it pending, and
`narrate=false` gives the web app's live activity rail exact figures on a
30-second poll without spending an LLM call on every refresh.

## Setup

1. **Prerequisites:** [`uv`](https://docs.astral.sh/uv/) for Python, Node
   20+ for the web app, a free [Stripe](https://stripe.com) account (test
   mode only — no card required), one LLM API key
   ([Anthropic](https://console.anthropic.com) or
   [OpenAI](https://platform.openai.com)), and a Telegram bot token from
   [@BotFather](https://t.me/BotFather) (send `/newbot`, follow the prompts).

2. **Configure.** `cp .env.example .env`, then fill in:
   - `STRIPE_SECRET_KEY` — Stripe Dashboard → Developers → API keys, the
     **test mode** secret key (`sk_test_...`); the app refuses a live key.
   - `LLM_PROVIDER` — `anthropic` or `openai`; `ANTHROPIC_API_KEY` or
     `OPENAI_API_KEY` to match. Each defaults to a specific model
     (`claude-opus-5` for Anthropic, `gpt-5.4-mini` for OpenAI) unless
     `LLM_MODEL` overrides it.
   - `TELEGRAM_BOT_TOKEN` — from @BotFather above.
   - `OWNER_API_TOKEN` — the bearer token the web app authenticates with;
     the `.env.example` default (`dev-owner-token`) works out of the box for
     local use.
   - `DATABASE_URL` — defaults to a local SQLite file; leave it as-is.

3. **Install.** `make install` — `uv sync` for the backend, `npm install`
   for the web app.

4. **Seed the sandbox.** `make seed`. This creates ten customers and around
   130–140 payment intents spread across today, yesterday, and the two
   weeks before (including two genuine `insufficient_funds` declines — a
   live run produced 136 total: 134 succeeded, 2 declined), plus a handful
   of invoices — among them an open **$1,200** invoice for Acme Corp and one
   at or above the **$2,000** Telegram ceiling, so the escalation path is
   demonstrable immediately. It prints a one-time
   Telegram binding token per customer and the run's expected figures on
   completion — use the tokens and numbers it prints, not any written down
   here, since Stripe assigns object creation order and the exact figures
   shift with the calendar. Re-running `make seed` on an account that
   already has this run's data is a no-op that reprints the same tokens and
   figures rather than doubling revenue; if a previous run crashed partway
   through, the next plain run detects the incomplete state and resumes it
   from the persisted `seed_run` id rather than starting over. `--force`
   wipes what it can and reseeds from scratch (Stripe cannot delete
   `PaymentIntent`s or `Charge`s, so any old ones remain); `--clean` only
   removes and says as much about what it cannot; `--today-only` adds one
   more day of activity to existing seeded customers, useful if you come
   back the next morning. Seeded history carries `metadata.demo_created_at`
   because Stripe assigns `created` and cannot be told otherwise; exactly
   one function (`app.domain.mapping`) reads that field, and every create
   call explicitly requests `"currency": "usd"` because a fresh sandbox's
   account-level default currency is not guaranteed to be USD.

5. **Run everything.** `make dev` starts the API on `:8000`, the web app on
   `:5173`, and the Telegram bot (long polling, no tunnel needed) together;
   one `Ctrl-C` stops all three. Open `http://localhost:5173`.

6. **Bind Telegram.** In the bot's chat, send `/start <token>` with a token
   `make seed` printed for the customer you want to act as, or open
   `https://t.me/<your-bot-username>?start=<token>` to do the same as a
   deep link. `/logout` disconnects; the owner can also revoke a binding
   from the API.

## Demo script

With the sandbox seeded and `make dev` running, this is roughly the
reviewer's first fifteen minutes:

1. Open `http://localhost:5173` and read the narrated summary the app
   opens with; the live rail's figures should match what `make seed`
   reported.
2. Ask the web assistant: *"How much did we take last week compared to the
   week before?"* — the answer states the actual date ranges it compared,
   not just the totals.
3. Ask: *"Refund Maya's last payment."* Watch the trail show
   `find_customer` then `query_payments`, then a confirmation card naming
   Maya and the exact amount. Click **Approve** and a receipt card appears;
   `GET /api/audit` shows the mutation alongside the prompt that produced it.
4. In Telegram, send `/start <Acme's token>` to bind, then ask *"what do I
   owe?"* — the reply states a count and a due date, never a dollar figure
   in the chat, with **View** and **Pay** buttons per invoice.
5. Tap **Pay** on the smaller Acme invoice ($1,200). Confirm the message
   that states the amount, then **Confirm** — a receipt button appears, and
   the web app's "Taken" figure rises on its next refresh.
6. Ask the bot to pay the $2,400 licence invoice instead. It declines to
   pay and explains it has escalated to the owner — no payment happens. The
   web app's Escalations panel now shows Acme; click **Approve and notify**
   and the Telegram chat receives a Stripe-hosted payment link. Paying it
   on that page with test card `4242 4242 4242 4242` completes the loop.

## Testing

`make test` runs the full suite with no network calls and no LLM: the
executor depends on a narrow `StripeGateway` protocol and an `LLMBackend`
protocol, and tests supply fakes for both. The load-bearing claims each have
a test behind them:

- The bot rejects a payment at or above $2,000 before any Stripe call is
  made, not after.
- A customer-scoped Stripe client cannot reach another customer's data.
- Approving a stored confirmation executes the parameters the user saw, not
  a freshly re-planned action.
- `occurred_at` prefers `metadata.demo_created_at` and falls back to
  Stripe's `created` — the one place the seed concession is read.
- The executor rejects malformed or unregistered actions before they reach
  any handler.

`uv run pytest -m live_llm` runs the one test that calls a real model; it is
deselected by default (`addopts = -m 'not live_llm'` in `pyproject.toml`) and
needs a working LLM key, since asserting on live model output would
otherwise be theatre.

## Notes

The exact figures in a given seeded sandbox vary with the calendar: amounts
are drawn deterministically (`Faker.seed(42)`), but which day of the week
gets how much history depends on when you run `make seed`. Treat the seed
report it prints as the source of truth for a given run, not any number
written above. What is fixed regardless of the day: 18 successful payments
and 2 genuine `insufficient_funds` declines happen today, Acme Corp carries
an open $1,200 invoice, and one invoice sits at or above the $2,000 ceiling
so the escalation path always has something to demonstrate.
