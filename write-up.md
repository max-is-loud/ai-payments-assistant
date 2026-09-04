# Write-up

## Scope and approach

I spent about six hours on the project over several sessions, slightly more than
the suggested three-to-five-hour range. The extra time went mainly into
testing, hardening, documentation, interface polish, and the optional escalation
workflow. After reviewing the first version, I added targeted regression tests
and fixed the issues they exposed. Those changes are described below.

I kept one main rule throughout: the language model could handle understanding
and communication, but not financial execution. The model can propose one named
action with structured parameters or produce a final response. Python validates
and executes the action, then returns a typed result for the model to explain.
Financial actions are stored and require explicit confirmation before they run.
The customer bot follows the same pattern with a smaller, customer-scoped set of
actions.

I used Claude Code throughout the project for planning, implementation support,
test generation, and review. The application logic, action boundaries, tests, and product decisions are all explicit in the repository and can be reviewed on their own.

## Assumptions

- **One owner and one Stripe account.** This is a proof of concept for a single
  business. It does not include organizations, multiple owners, or role-based
  permissions.
- **One settlement currency.** The app reads the Stripe account's default
  currency and uses it for seeded data, invoices, payment links, summaries, and
  charts. Zero-decimal currencies are rejected because the domain model stores
  money in cents.
- **Demo-scale data.** The seeded sandbox contains roughly 150 Stripe objects.
  Fetching and filtering complete Stripe lists in Python is reasonable at that
  scale, but it would not be my production design.
- **A fresh Stripe test account.** The reviewer runs the seed command against
  their own empty sandbox. Seeded records include `metadata.demo_created_at` so
  the app can show historical activity even though Stripe controls the real
  `created` timestamp.
- **Telegram is a demo identity boundary.** Each seed token can be used only
  once. Reconnecting the same customer after logout, expiry, or owner revocation
  requires a newly seeded token. In production, I would use verified delivery,
  token rotation, and a stronger binding lifecycle.

## Key challenges and decisions

### Keeping financial actions deterministic

Natural-language requests are useful at the interface, but they are not a safe
execution format. The model never calls Stripe directly. It proposes an action,
and ordinary Python handles customer lookup, date ranges, amount conversion,
Stripe calls, and errors.

That boundary matters most for refunds and invoices. Before a mutation runs, the
resolved operation is stored and shown as a concrete confirmation such as
“Refund CA$45.00 to Maya Chen.” Approval executes that stored operation instead
of asking the model to plan it again. The action layer can also be tested with
fake Stripe and LLM implementations, without network access or nondeterministic
model output.

The dashboard follows the same rule. Python calculates its totals and chart
series, while the narrator receives formatted facts rather than raw cents. I
added a `compare_periods` action after testing showed that asking the model to
infer two date ranges and total raw payment rows was unnecessarily fragile.

### Creating useful historical test data

Stripe does not let an application assign historical `created` timestamps to
PaymentIntents and Charges. Test clocks were not a good fit here, so the seed
command stores a demo timestamp in metadata. One mapping function uses it when
present and otherwise falls back to Stripe's real timestamp. The workaround is
therefore isolated and easy to remove outside the demo.

Making the seed command safe to resume was trickier than it first looked. A
same-day interrupted run with seed-tagged customers keeps the same run ID,
customer IDs, and binding tokens, then creates only what is missing. Retried
requests use the original parameters and idempotency keys. Completeness is
checked against the final state expected for each invoice—paid or open—rather
than by counting invoice objects. This prevents a draft left by a crash from
being mistaken for a completed invoice.

I tested that behaviour with a stateful Stripe fake that enforces idempotency.
The tests interrupt the seed before every customer and invoice write, plus a
sample of payment writes. I have not exercised this resume path against a live
Stripe sandbox.

The seed also creates real failed PaymentIntents using Stripe's
insufficient-funds test payment method instead of inventing failed records
locally. It reads the account's default currency before writing anything, so it
does not assume that every reviewer sandbox is based in the United States.

### Separating owner and customer capabilities

Privacy is enforced by the application structure, not only by a prompt. The
owner and customer interfaces share an executor but use different action
registries. Customer actions cannot accept an arbitrary `customer_id`; the
server resolves the bound customer before the model is involved. This keeps a
customer prompt from becoming access to another customer's invoices or the
business's overall finances.

The Telegram payment action enforces the threshold in Python. When an open
invoice has $2,000 or more remaining, it creates an escalation instead of
completing the payment. Because Stripe's hosted invoice page can also take
payment, the bot withholds that URL from its observations, buttons, and
callbacks until the owner approves the request.

The bot responds only in private chats. In a group or channel, every command,
message, and button receives one fixed response without looking anything up.
Every callback requires an active binding, and Cancel also requires the same
Telegram account that created the proposal.

The authoritative monetary figures in the invoice workflow bypass the model.
Amounts travel under an interface-only `display` key that is removed from the
planner's observation. The renderer writes the amounts onto the invoice buttons
and calculates the total line itself. Action parameter models also reject
unknown keys, so a misspelled `amount` cannot silently turn into a full refund.

The web app and Telegram bot have separate output rules. The browser renders a
restricted Markdown format, while Telegram output is sanitized to the smaller
HTML subset it accepts. Without that boundary, one malformed model response
could prevent an entire customer message from being delivered.

### Integration reliability

A few problems only showed up during live walkthroughs. Stripe SDK objects had
to be converted to plain dictionaries at the gateway boundary. The browser's
SSE parser initially disagreed with the server's line endings. Provider errors
also contained useful developer details that were not appropriate to show an
owner. I fixed each issue at the boundary where it originated rather than adding
special cases to the interface.

The API and Telegram bot run as separate processes over the same SQLite file.
WAL mode and a claim-once status transition prevent two confirmations from
executing the same action. Execution uses three short stages: claim the action
and store a server-generated idempotency key, call Stripe without holding a
database write transaction, then record the result and audit entry together.
The narrator runs afterward.

This keeps a slow provider from blocking the other process's database writes. It
also means a dropped stream cannot return a completed action to `pending`. If a
process dies between the Stripe call and the local record, startup recovery uses
the same idempotency key. Recovery is limited to twenty hours because Stripe
retains keys for at least twenty-four. Older executions are moved to
`needs_review`, with the key recorded for manual comparison against Stripe's
request log. There is no automatic reconciliation.

The amount on a confirmation is also pinned. A full refund stores the refundable
balance shown to the owner, and an invoice payment stores the amount the
customer confirmed. If that amount changes before execution, the action fails
as stale instead of silently using the new value.

For dashboard reads, a short-lived shared cache prevents the page from listing
the same Stripe data several times during one load. Stripe remains the source of
truth. A failed refresh is reported in the masthead with a retry, while the last
successful sync time remains visible.

## Testing and validation

The automated suites cover the executor, customer scoping, confirmation
integrity, the payment ceiling, Stripe mapping, seed payloads, SSE parsing,
formatting boundaries, chart calculations, and the main React interaction
states. The later hardening pass added focused coverage for concurrent
confirmations, interrupted execution, stale recovery, private-chat enforcement,
customer-scoped cancellation, hosted-link withholding, strict parameters,
resumable seeding, one-time binding tokens, and the approval card's loading and
failure states.

Backend and frontend tests use fakes by default, so they run without Stripe or an
LLM. They are not live-model evaluations. There is a separate opt-in LLM smoke
test. I also used fresh Stripe sandboxes and a manual reviewer-style walkthrough
to find integration problems that the fakes missed. The later hardening changes
have been verified against the automated fakes, but I have not repeated the full
live walkthrough since making them.

## Limitations and next steps

- **Authentication is suitable only for a local proof of concept.**
  `OWNER_API_TOKEN` is compiled into the browser bundle as a localhost
  convenience; production would use server-managed owner sessions. Customer
  binding tokens are one-time, but there is no owner-side flow for issuing a new
  one. A production Telegram identity flow would use verified delivery,
  rotation, and stronger lifecycle management.
- **Notification delivery is best-effort.** The Telegram payment link is sent
  once after approval is committed. A delivery failure appears on the escalation
  card but is not retried. Production would need a durable outbox. A manual
  resend action would be a reasonable intermediate step, but I left it out to
  keep the proof of concept focused.
- **Reads list the full Stripe account.** The short-lived cache makes that
  acceptable for demo data. Production would use Stripe webhooks or an indexed
  local read model.
- **Ambiguous Stripe outcomes are recorded, not reconciled.** If Stripe may have
  applied an operation but no response arrives, the action is marked failed and
  retains its idempotency key in local state. An execution interrupted beyond
  the twenty-hour recovery window moves to `needs_review` and writes the key to
  the audit log and transcript. Neither path is reconciled automatically, and
  there is no dedicated owner screen for resolving it.
- **Automated tests rely on fakes.** They verify the executor, lifecycle, and
  interface boundaries, but they do not measure real prompt behaviour. With more
  time, I would add repeatable evaluations for the required commands, ambiguous
  customer names, date interpretation, prompt injection, and refusals across the
  supported models, followed by a full browser test.

## Bonus: owner escalation workflow

I chose the escalation workflow because it turns the payment ceiling into a
useful product flow instead of a dead end. When a customer asks the bot to pay an
invoice at or above $2,000, the server records an escalation and shows it in the
owner's web app. For an invoice with a Stripe-hosted payment page, approval
attempts to send that link to the customer. Otherwise, the bot attempts to send
an owner-follow-up message.

This is the pattern I would want in a production assistant: automate the routine
case, bring a person into higher-risk decisions with the relevant context, then
continue the workflow. It also makes the owner app and customer bot feel like one
product rather than two unrelated deliverables.
