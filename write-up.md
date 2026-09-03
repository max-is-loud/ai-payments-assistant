# Write-up

## Scope and approach

The solution has three parts: a FastAPI backend, a React single-page application
for the business owner, and a Telegram bot for customers. A seed command creates
the Stripe test data required to exercise all three. I also implemented one
optional feature: an escalation workflow that connects the customer bot back to
the owner when a payment reaches the $2,000 limit.

I spent approximately six hours on the project over several sessions. That is
slightly above the suggested three-to-five-hour range; the additional time went
mainly into validation, hardening, documentation, interface polish, and the
optional escalation workflow. A later hardening pass, driven by regression
tests written before each fix, closed the defects a review of the first version
found; they are described where they apply below.

The main architectural decision was to keep the language model responsible for
understanding and communication, but not for financial execution. Each owner
request enters a capped action loop. At every step, the model either proposes one
named action with structured parameters or produces a terminal response. Python
validates and executes proposed actions, then returns typed results for the model
to explain. Mutating actions are stored and shown to the owner for confirmation
before execution. The customer bot uses the same pattern with a smaller,
customer-scoped action registry.

I used Claude Code throughout the project for planning, implementation support,
test generation, and review. I treated it as a development tool rather than a
runtime dependency: the application code, action boundaries, tests, and product
decisions remain explicit in the repository and can be reviewed independently of
the tool that helped produce them.

## Assumptions

- **One owner and one Stripe account.** This is a single-business proof of
  concept. It does not include organizations, multiple owners, or role-based
  permissions.
- **One settlement currency.** The app reads the Stripe account's default
  currency and uses it consistently for seeded data, new invoices, payment
  links, summaries, and charts. Zero-decimal currencies are rejected because the
  current domain model represents money in cents.
- **Demo-scale data.** The seeded sandbox contains roughly 150 Stripe objects.
  Fetching and filtering complete Stripe lists in Python is acceptable at that
  scale, but it is not the design I would use for a production account.
- **A fresh, empty Stripe test account.** The reviewer runs the seed command
  against their own sandbox. Seeded records include `metadata.demo_created_at`
  so the app can present historical activity even though Stripe controls each
  object's real `created` timestamp.
- **Telegram is a demo identity boundary.** A token printed by the seed command
  binds a Telegram user to one Stripe customer, once: the token is spent on use,
  and `/logout`, inactivity expiry, or the owner's revocation cannot be undone by
  replaying it. Only the seed mints tokens, so re-binding after that means
  reseeding with `--force`. A production version would use verified delivery
  (email or SMS), rotation, and stronger lifecycle management for that binding.

## Key challenges and decisions

### Keeping financial actions deterministic

Natural-language requests are useful at the interface, but they are not a safe
execution format. The model therefore cannot call Stripe directly. It proposes
an action from a registry, and the executor handles customer lookup, date ranges,
amount conversion, Stripe calls, and error handling in ordinary Python.

This boundary is especially important for refunds and invoices. Before a
mutation runs, the resolved operation is stored and presented as a concrete
confirmation such as “Refund CA$45.00 to Maya Chen.” Approval executes that
stored operation rather than asking the model to plan it again. The same action
system can be tested with fake Stripe and LLM implementations, without network
access or nondeterministic model output.

The dashboard follows the same principle. Charts and structured totals are
computed in Python; the narrator receives formatted facts rather than raw cents.
I added a dedicated `compare_periods` action after testing showed that asking a
model to infer two date ranges and total raw payment rows was needlessly fragile.

### Creating useful historical test data

Stripe does not allow an application to assign historical `created` timestamps
to PaymentIntents and Charges. Test clocks were not a good fit for this use case,
so the seed command writes a demo timestamp in metadata. One mapping function
uses that value when present and otherwise falls back to Stripe's real timestamp.
This keeps the concession isolated and makes it easy to remove outside the demo.

A run interrupted partway is resumed under the same run id: the customers it
already created keep their ids and binding tokens, only the missing objects are
created, and each request repeats exactly the parameters Stripe first saw under
that idempotency key, which is what Stripe requires for a key to be honoured.
Invoices an earlier run left behind (`--force` voids them but cannot delete
them) are counted under their own run, and completeness is judged per invoice
against the state a finished seed leaves it in (paid or open) rather than by
counting invoice objects: a crash between an invoice's creation and its
finalisation left a draft that an object count had called complete. This path
is tested through a stateful fake of the Stripe client that enforces the
idempotency rules, interrupted before every customer and invoice write and a
sample of payment writes; it has not been exercised against a live sandbox.

The seed also creates real failed PaymentIntents with Stripe's insufficient-funds
test payment method instead of inventing failed records locally. It reads the
account's default currency before creating data, which avoids assuming that a
fresh reviewer sandbox is based in the United States.

### Separating owner and customer capabilities

The owner and customer interfaces share an executor but not an action registry.
Customer actions do not accept an arbitrary `customer_id`; the server resolves
the bound customer before the model is involved. This prevents a prompt from
turning into access to another customer's invoices or account-level revenue.
The direct Telegram payment action also checks the $2,000 threshold in Python
and creates an escalation instead of completing the payment. Stripe's hosted
invoice page can take payment too, so for an invoice at or above the threshold
the bot withholds that link everywhere (observations, buttons, callbacks) until
the owner's approval is committed, at which point the approval path sends it.
The bot answers only in private chats; in a group or channel every command,
message, and button gets one fixed sentence and nothing is looked up, because
replies go to the chat and a group has other members. Every button acts as the
bound customer, Cancel included: a callback names an action id, and the row is
dismissed only for the actor whose proposal it is. The figures a customer reads
never pass through the model: amounts travel under an interface-only `display`
key the loop strips from the planner's observation, and the renderer writes
them onto each invoice's button and into one total line of its own, so "what do
I owe?" is answered in full while the model can neither restate nor misstate a
figure. Every action's parameter model forbids unknown keys, so a misspelt
`amount` cannot silently become a full refund; the planner is told which key
was wrong and tries again.

The two channels have separate output rules as well. The web app renders a
restricted Markdown format, while Telegram output is sanitized to the smaller
HTML subset that Telegram accepts. These are small details, but they matter when
a malformed model response could otherwise make an entire customer message fail.

### Integration reliability

Several issues only appeared during live walkthroughs. Stripe SDK objects needed
to be normalized to plain dictionaries at the gateway boundary. The browser's
SSE parser initially disagreed with the server's line endings. Provider errors
were technically useful but inappropriate for an owner-facing message. These
were addressed at their respective boundaries rather than with special cases in
the interface.

The API and Telegram bot run as separate processes over the same SQLite file.
WAL mode and a claim-once status transition protect confirmations from being
executed twice. Execution is three short transactions: the claim stores a
server-minted idempotency key and commits, the Stripe call runs with no write
transaction open, and the result and audit entry commit together; the narrator
runs after that. A slow provider therefore never holds the writer lock the other
process needs, a dropped stream cannot roll a finished execution back to
pending, and a process that dies between the Stripe call and the record finishes
the execution at its next start under the same key, which Stripe answers with
the original result rather than a second operation. That replay is only safe
while Stripe still holds the key, which it does for at least 24 hours, so
recovery is bounded to twenty hours from the claim; an older row is parked as
`needs_review` with its key in the audit log and the transcript, for a person
to settle against Stripe's request log. Nothing reconciles against Stripe
automatically. The amount a confirmation
names is the amount stored: a full refund is pinned to the refundable balance at
proposal time and an invoice payment to the amount owed, and either fails as
stale if the balance moved in between. For dashboard reads, a short-lived shared
cache avoids repeating the same full Stripe listing several times during one
page load while keeping Stripe as the source of truth; a refresh that fails is
reported in the masthead with a retry and leaves the previous figures, and their
age, as they were.

## Testing and validation

The automated suites cover the action executor, customer scoping, confirmation
integrity, the payment ceiling, Stripe mapping, seed payloads, SSE parsing,
formatting boundaries, chart calculations, and the main React interaction
states. The hardening pass added tests for the confirmation lifecycle under
concurrency (a blocked Stripe call, concurrent approvals, a rollback after
execution, recovery after a crash), private-chat enforcement, the hosted-link
rule, strict parameters, seed resume through a stateful fake Stripe client,
one-time binding tokens, and the approval card's in-flight and failed states.
Backend and frontend tests run without Stripe or an LLM by default and use
fakes; they are not live-model evaluations. There is a separate opt-in live LLM
smoke test. I also used fresh Stripe sandboxes and a manual reviewer-style
walkthrough to catch integration problems that fakes could not expose; the
changes from the hardening pass have been verified against fakes and the
existing manual walkthrough has not yet been repeated against a live sandbox.

## Limitations and next steps

- **Authentication is appropriate only for a local proof of concept.**
  `OWNER_API_TOKEN` is compiled into the browser bundle, so it is a localhost
  demonstration convenience, not production authentication; production would
  use server-managed owner sessions. Customer binding tokens are now one-time,
  but there is no owner-side way to issue a new one, so a customer who logs out
  can only be re-bound by reseeding. A production Telegram identity flow would
  use verified delivery (email or SMS), rotation, and stronger lifecycle
  management.
- **Notification delivery is best-effort.** The Telegram message with the
  payment link is sent once, after the approval is committed; a delivery failure
  is shown on the escalation card ("Approved · Telegram not reached") but not
  retried. Production would need a durable outbox with retries. A manual
  "resend" on an approved escalation would be a safe interim step and was left
  out to avoid growing the API surface in this pass.
- **Reads list the whole Stripe account.** A short-lived cache makes that
  acceptable at demo scale. Production would use Stripe webhooks or an indexed
  local read model rather than repeatedly listing the account.
- **Ambiguous Stripe outcomes are recorded, not reconciled.** If Stripe applied
  an operation but the response never arrived, the action is recorded as failed
  with its idempotency key in the audit log; an execution interrupted more than
  twenty hours ago is parked as `needs_review` with the same information. Both
  are enough to check against Stripe's request log by hand; nothing reconciles
  them automatically, and there is no owner-side screen for them beyond the
  audit log and the transcript.
- **The automated tests use fakes.** They pin the executor, the lifecycle, and
  the interfaces, but they are not live-model evaluations. I would add
  repeatable prompt evaluations for the required commands, ambiguous customer
  names, date interpretation, prompt-injection attempts, and refusal behaviour
  across supported models, plus a full browser test.

## Bonus: owner escalation workflow

I chose the escalation workflow because it turns the payment ceiling into a
useful product flow rather than a dead end. When a customer asks the bot to pay
an invoice at or above $2,000, the server records an escalation and surfaces it
in the owner's web app. For an invoice-backed escalation with a Stripe-hosted
invoice URL, owner approval notifies the customer with that link; otherwise the
bot sends an owner-follow-up message.

This mirrors the pattern I would want in a production assistant: automate the
routine case, hand higher-risk decisions to a person with the relevant context,
and resume the workflow after that decision. It also connects the owner app and
customer bot into one coherent system rather than treating them as unrelated
deliverables.
