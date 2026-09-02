---
title: AI payments assistant — design
status: approved
updated: 2026-09-02
---

# AI payments assistant — design

Design for the Replicant.ai take-home: an AI assistant over a Stripe account,
with a web app for the business owner and a Telegram bot for their customers.
Requirements of record are in [Assignment brief](../assignment-brief.md).
Code rules are in [Code conventions](../code-conventions.md).

## 1. Goal and constraints

Three deliverables, one product:

1. **Owner web app** — chat interface that summarises the day's payment
   activity and carries out natural-language commands against Stripe.
2. **Customer Telegram bot** — lets an external customer see and pay only
   their own invoices, handing anything at or above **$2,000** to the owner.
3. **Seed script** — one command that populates a *fresh* Stripe sandbox.

The binding constraint on everything below: **the reviewer runs this against
their own empty Stripe test account.** Nothing may depend on data created by
hand in a dashboard. The seed script is a graded deliverable, not a
convenience.

Budget is three to five hours of engineering. The design optimises for a
reviewer's first fifteen minutes: it must install, seed, run, and demonstrate
its claims without a tunnel, a fourth vendor account, or a support ticket.

## 2. Architecture

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

Stripe is the source of truth for money. SQLite holds only what Stripe cannot:
conversations, pending confirmations, Telegram bindings, escalations, and the
audit log.

### Module layout

```
app/
  domain/     models and the Stripe-to-domain mapping
  agent/      loop, action schema, prompts, registries
  llm/        backend protocol and two providers
  actions/    owner actions, customer actions
  stripe_/    gateway protocol, owner client, customer-scoped client
  db/         SQLAlchemy 2.0 typed models
  telegram/   bot and handlers
seed/         seed script
web/          Vite + React + TypeScript
```

## 3. The agent: propose, execute, narrate

The assistant is **not** a native tool-calling loop. The LLM returns a
validated JSON action; deterministic Python executes it; the LLM then narrates
the typed result.

```
  user text
      │
      ▼
┌─────────────┐   JSON action    ┌──────────────┐   typed result   ┌───────────┐
│   PLANNER   │─────────────────>│   EXECUTOR   │─────────────────>│ NARRATOR  │
│    (LLM)    │<─────────────────│  (pure py)   │                  │   (LLM)   │
└─────────────┘   observation    └──────────────┘                  └───────────┘
```

Each turn is validated against one schema:

```json
{
  "reasoning": "why this step",
  "action": "refund_charge",
  "parameters": { "charge_id": "ch_...", "amount_cents": null }
}
```

`answer`, `clarify`, and `confirm` terminate the loop. Anything else returns an
observation and iterates, capped at **five iterations** so a confused model
cannot spin.

This is an agent loop — iterative and able to refine on what it observes — with
the dispatch in our hands rather than the provider's.

### Why not native tool calling

Considered and rejected, for reasons worth stating because the default is the
opposite choice:

- **Legibility.** Because we own the dispatch, every step is an event we can
  stream to the UI. A provider SDK's loop hides this.
- **Portability.** One code path regardless of provider.
- **Testability.** The executor is exercised with plain JSON, no LLM and no
  network.

It is not a *safety* argument. Native tool calling also leaves execution in our
code, and would permit identical guardrails. The honest trade is that models
are post-trained on native tool formats and are therefore somewhat more
reliable at selecting actions from large tool sets. At roughly ten actions the
difference does not bite; at fifty it would. Recorded in `write-up.md` as a
"with more time" item.

### Two registries, one executor

Scoping is structural, not prompted:

| Owner (web) | Customer (bot) |
| --- | --- |
| `summarize_day`, `query_payments` | `my_balance`, `my_invoices` |
| `find_customer`, `list_invoices` | `pay_invoice` |
| `create_invoice`, `refund_charge` | `escalate_to_owner` |
| `create_payment_link` | |
| `list_escalations`, `approve_escalation` | |

**The bot's registry contains no action taking a `customer_id` parameter.** Its
Stripe client is constructed with the ID from the binding row. A prompt
injection instructing the model to read another customer's invoices finds no
action to call and no parameter to fill — the capability does not exist in that
registry.

### Guardrails as executor invariants

- `pay_invoice` raises above **$2,000** and returns an escalation,
  unconditionally, before any Stripe call.
- Every bot-side Stripe call carries the bound `customer_id`.
- Every mutation is written to the audit log with the prompt that produced it.
- The ceiling is defined in exactly one place, per
  [Code conventions](../code-conventions.md).

### Confirm before mutate

A proposed mutation is resolved fully, then returned for approval with concrete
details ("Refund $45.00 to Maya Chen, charge from Aug 30"). On approval the
server executes **the stored action**, never a freshly planned one. The model
cannot substitute a different action between proposal and execution.

## 4. Identity and the privacy boundary

A customer binds their Telegram account once, via a deep-link token minted by
the seed script:

```
Customer                  Bot                      SQLite            Stripe
   │  /start <token>       │                          │                 │
   ├──────────────────────>│  bind(telegram_id, cus)  │                 │
   │                       ├─────────────────────────>│                 │
   │  "what do I owe?"     │  lookup(telegram_id)     │                 │
   ├──────────────────────>├─────────────────────────>│                 │
   │  "you owe $1,200"     │  invoices(customer_id ◄── from binding)    │
   │<──────────────────────┤────────────────────────────────────────────>│
```

| Control | Value |
| --- | --- |
| Binding | `telegram_id` to `stripe_customer_id` |
| Inactivity expiry | 14 days |
| Customer revocation | `/logout` |
| Owner revocation | `DELETE /api/customers/{id}/telegram-binding` |
| Per-session re-verification | Not implemented — see below |

The Telegram ID is read from the update payload, never from message text, so a
user cannot present another's. It is stable across username and phone changes,
and Telegram does not recycle IDs.

**It is an identifier, not an authenticator.** It proves "the same account as
last time", never "this account belongs to Acme Corp". That is established once
by the binding token and trusted thereafter.

### Why not re-verify every session

Re-verification defends against a stale binding — the employee who leaves Acme
but keeps access. Fourteen-day expiry and revocation cover that at far lower
cost.

It does **not** defend the case it appears to: an attacker holding an unlocked
phone. A one-time code sent by email arrives on that same device. A second
factor delivered to a compromised handset is not a second factor. The durable
leak in that scenario is the chat transcript, which no re-authentication policy
can reach — which is why the bot reports "1 unpaid invoice, tap to view"
instead of restating amounts into the thread.

In production the binding step itself should be an email verification rather
than a seeded token. That is not built here because seeded customers carry
generated addresses no reviewer can receive mail at, making the flow
untestable against a fresh sandbox.

## 5. Stripe data and the seed script

### The history problem

The required summary compares periods — "well ahead of yesterday", "last week
compared to the week before". A fresh sandbox has no history, and `created` is
assigned by Stripe.

Two routes were investigated:

| Option | Outcome |
| --- | --- |
| CSV / bulk import | Does not exist. Stripe's data migration is PAN import — card credentials, via a support request, live mode only. Revenue Recognition import creates accounting records, not `Charge` objects the payments API returns |
| **Test clocks** | Real, and *can* create objects at a past `frozen_time` — but limited to three customers per clock, auto-delete after roughly seven days (taking their customers with them), forbid a past start for existing customers, advance asynchronously, and are documented for subscription lifecycles rather than one-off payments |

Test clocks are the sanctioned mechanism and are rejected on fit, not on
principle. Seven-day expiry alone disqualifies data a reviewer may return to.

### Chosen approach

Today's activity is created today with genuine Stripe timestamps. Historical
activity carries `metadata.demo_created_at`. The concession lives at the domain
boundary:

```
Stripe Charge/Invoice  ──►  to_payment()  ──►  Payment(occurred_at=..., ...)
                              │
                              └── occurred_at = metadata.demo_created_at or created
```

Summaries, comparisons, and every agent action see only `occurred_at`. Removing
two words from one function makes it production behaviour.

### What gets seeded

Deterministic via `Faker.seed(42)`, so the reviewer's data matches the README's
stated figures and the summary can be verified rather than merely believed.

- **Acme Corp** and **Maya Chen** pinned by name, because the brief's own
  example commands reference them
- Remaining customers, amounts, and invoice line items generated for realism,
  with weighted amounts and business-hours clustering
- Around 18 successful payments today; a lighter yesterday; two prior weeks
- Two declines on `4000000000009995`, producing genuine `insufficient_funds`
- An open **$1,200** invoice for Acme Corp
- At least one invoice at or above **$2,000**, so the ceiling and the
  escalation bonus are demonstrable
- A deep-link token per customer, printed on completion

Every object is tagged `metadata.seed_run`. Re-running detects existing data
and exits rather than silently doubling revenue; `--force` re-seeds and
`--clean` removes what it can. Charges cannot be deleted in Stripe, and
`--clean` says so rather than pretending otherwise.

## 6. API

```
POST   /api/conversations/{id}/messages     send a turn        → SSE stream
POST   /api/conversations/{id}/confirm      approve a mutation → SSE stream
GET    /api/conversations/{id}              history
GET    /api/summary/today                   daily summary
GET    /api/escalations                     pending approvals
POST   /api/escalations/{id}/approve
DELETE /api/customers/{id}/telegram-binding owner-side revoke
GET    /api/audit                           every action taken, and why
```

Resource-shaped for state, conversational for intent. State lives behind real
resources that can be inspected independently of the chat.

### Streaming

Because we own the dispatch, the agent's work is legible. SSE emits typed
events rather than a spinner:

```
event: planning     {"reasoning": "need to find which Maya"}
event: action       {"name": "find_customer", "args": {"query": "Maya"}}
event: observation  {"matched": 1, "customer": "Maya Chen"}
event: confirmation {"action_id": "act_7f3", "summary": "Refund $45.00 ..."}
```

### Design choices

- **Confirmation is a resource, not a dialog.** A `confirmation_required`
  response carries a server-stored `action_id`; approval executes that stored
  action.
- **`Idempotency-Key` passthrough** on mutating routes, forwarded to Stripe. A
  double-clicked approval must not refund twice.
- **Errors carry a fix.** `{error: {code, message, hint}}` — "set
  `STRIPE_SECRET_KEY` in `.env`" rather than "unauthorized". A fourth field,
  `detail`, carries developer text (a provider's raw response body, an
  exception name) and is sent only when the API runs with `DEBUG=1`; it is
  always written to the API log, so the default hides nothing from whoever
  runs the process.
- **Auth** is a single `OWNER_API_TOKEN` required on `/api/*`, shipped with a
  working default in `.env.example`. Enforced, with zero reviewer friction.

## 7. Web app

Vite, React, TypeScript. Beyond the required input and response area:

- Daily summary rendered on load, so the app speaks first
- Live activity trail driven by the SSE events above
- Inline confirmation cards with resolved details and Approve or Cancel
- Typed result cards — a refund renders a receipt, invoices render with status
  pills
- Escalations panel for the bonus loop

Model text is rendered as GitHub-flavored Markdown, and the web system message
says so, so a list of payments arrives as a list. Telegram cannot render
Markdown — only a three-tag HTML dialect, and it rejects the whole message on
any parse error — so the bot's system message asks for that dialect instead.
Each channel's system message is built by its own function carrying its own
formatting rules; there is no builder that could pair the wrong two. Neither
side trusts the prompt: `react-markdown` escapes raw HTML and empties unsafe
links, and the bot's send path sanitizes to balanced allowed tags or
downgrades to plain text.

## 8. Bonus: the escalation loop

The brief requires payments at or above $2,000 to be handed to the owner. Most
solutions will make that a dead end. Here it is a loop:

```
customer hits ceiling ──► bot files escalation ──► owner's web app
                                                        │
customer receives link ◄── bot notifies ◄── owner approves
```

Chosen because it is Replicant's own product pattern in miniature — automation
handles tier one, escalates cleanly to a human, then resumes — and because it
turns two separate deliverables into one product. It also doubles as the
security answer for high-stakes actions: out-of-band owner approval, rather
than another code sent to a possibly compromised device.

## 9. LLM providers

Two backends behind one `complete()` interface, selected by environment
variable: Anthropic and OpenAI. This is architecture, not a headline feature —
its purpose is that the reviewer can run the project with whichever key they
already hold.

## 10. Testing

Tests go where claims are load-bearing.

| Test | Why it exists |
| --- | --- |
| Bot rejects at or above $2,000 before any Stripe call | The stated requirement |
| Scoped client cannot reach another customer's data | Part 2's whole point |
| Confirmed action executes the stored action, not a re-plan | The safety claim |
| `occurred_at` prefers `demo_created_at`, falls back to `created` | Pins the one concession |
| Executor rejects malformed or unknown actions | The LLM boundary |
| Telegram send path never produces a message Telegram rejects | A dropped reply is a silent failure |
| Neither channel's system message carries the other's formatting rules | No accidental crossovers |
| Web renders Markdown lists and tables, never raw HTML or `javascript:` links | The web formatting boundary |

All run without an LLM and without network. The executor depends on a narrow
`StripeGateway` protocol; tests supply a fake. Planner tests are one smoke case
behind a marker, skipped without a key — nondeterministic assertions on model
output are theatre.

## 11. Configuration and running

`pydantic-settings` with `.env` from `.env.example`, validated at startup so a
missing key produces a message naming what is absent and where to get it.

```
make install    dependencies, both sides
make seed       populate the reviewer's Stripe sandbox
make dev        API, frontend, and bot together
make test
```

**Telegram uses long polling, not webhooks.** Webhooks require a public URL,
therefore a tunnel, therefore another account — a wall between the reviewer and
Part 2. Production would use webhooks.

The Stripe API version is pinned explicitly rather than drifting with the
account default.

## 12. Deliberately not built

Recorded in `write-up.md` with reasoning, because knowing what was skipped
reads as judgment where silence reads as oversight.

- **Stripe webhooks** — queried on demand; real-time needs a tunnel
- **Test clocks** — investigated, rejected on the limits in section 5
- **Native tool calling** — deliberate, per section 3
- **Email verification for bot binding** — preferred in production, untestable
  against a fresh sandbox with generated addresses
- **Session auth, multi-owner, rate limiting** — single-owner proof of concept
- **Frontend tests beyond the Markdown boundary** — the backend claims are the
  ones worth proving
