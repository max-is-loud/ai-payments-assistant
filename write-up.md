# Write-up

## Scope

This went past the brief's 3–5 hours, and it is worth saying so plainly rather
than making you infer it from the commit count.

I know what the 3–5 hour version looks like, because it is the first third of
this one: the propose-execute loop, the owner action registry, the seed
script, a chat box with an input and a response area, and the Telegram bot
with the $2,000 ceiling enforced in Python. Every requirement in the brief is
met by that version. Nothing after it was necessary.

What the extra time bought was the part a brief cannot ask for directly. The
owner app reads like an instrument rather than a chat box; the charts are
drawn from Python-computed series, so no figure on the page has passed through
a model; a shared cache turns an eight-second cold load into an instant one;
and the escalation loop makes the two deliverables one product instead of two.
The design system and the documentation vault are checked in as tooling rather
than as assignment code — they exist so the visual language and the reasoning
behind it are reproducible rather than merely described.

Where I did hold the line is the assistant itself. The owner registry opened
at nine actions and stands at ten; the single addition, `compare_periods`,
exists to take arithmetic away from the model rather than to give it a new
power. Growth went into how faithfully the interface renders what the
assistant already knew, never into widening what it may do.

The clearest example of that line is a thing the app cannot do. Ask it for
"payments per customer as a bar chart" and it will tell you it cannot draw
one, and offer a table instead. The fix is small and obvious — an aggregating
parameter on `query_payments`, and a chart the interface draws from the result
the way it already draws period comparisons — and I left it unbuilt on
purpose. Every chart on the page today is read from a Python-computed series
under an interface-only `display` key the planner never sees. Opening a
model-facing path to charts means owning a contract: which result shapes are
chartable, what the interface does when the model asks for a chart over data
that will not support one, and how it declines without the model narrating a
picture that is not there. That contract is worth more care than the feature
is worth, and a partial version of it would have undermined the invariant the
rest of the app is built on.

## Assumptions

- **Single owner, single currency.** The design targets one business owner
  and one currency throughout — whichever the Stripe account settles in,
  read from the account rather than assumed. There is no multi-tenant or
  multi-currency handling, and accounts in a currency with no minor unit
  (JPY, KRW) are refused up front.
- **Demo-scale data.** Listing and filtering over Stripe's pagination in
  Python is fine at the roughly 150-object scale a seeded sandbox produces;
  it would not be at production volume.
- **Reviewer runs seed and app on the same machine, ideally the same day.**
  The daily summary's "today" is computed from the local clock, and the
  seed script's own resume logic is keyed to it; `--today-only` covers
  returning the next morning without re-seeding from scratch.
- **Telegram identity is an identifier, not an authenticator.** A Telegram
  `chat_id` proves "the same account as last time," never "this account
  belongs to Acme Corp." That link is established once, by a binding token,
  and trusted thereafter. Binding tokens are minted by the seed script
  rather than delivered by email verification because seeded customers
  carry generated, unreceivable addresses — a production deployment would
  verify by email instead (see Limitations).

## Challenges

- **Stripe assigns `created`, and there is no way to import history.** CSV
  import does not exist for `Charge` or `PaymentIntent` objects — Stripe's
  data-migration tooling is PAN import (live-mode card credentials, via a
  support request) and Revenue Recognition import (accounting records, not
  objects the Payments API returns). Test clocks can create objects at a
  past `frozen_time` and were seriously considered, but they cap at three
  customers per clock, expire in about a week (taking their customers with
  them), and are built for subscription lifecycles rather than one-off
  payments — disqualifying for data a reviewer might come back to. The
  resolution is `metadata.demo_created_at`, written by the seed script and
  read by exactly one function (`app.domain.mapping._occurred_at`); deleting
  its fallback to Stripe's real `created` is all that separates this from
  production behavior.
- **Making the declines real.** Rather than fabricate a "failed" record, the
  seed script pays two payment intents with Stripe's
  `pm_card_chargeDeclinedInsufficientFunds` test payment method, producing a
  genuine `insufficient_funds` decline that the same mapping code every
  other payment goes through has to handle correctly.
- **Two processes sharing one SQLite file honestly.** The API and the
  Telegram bot are separate processes against the same database. WAL mode,
  short-lived transactions, and a claim-once conditional `UPDATE` on
  confirmations (`pending → executed` in one statement, checked by row
  count) keep a double-approval from ever executing twice.
- **stripe-python 15's `StripeObject` stopped being a dict subclass.** Every
  domain-mapping function is written against `Mapping[str, Any]` and calls
  `.get()` on optional fields; in this SDK version `StripeObject` supports
  `__getitem__` and `__contains__` but not `.get()`. This surfaced live,
  against the real API, not in a unit test — the fakes construct plain
  dicts and never exercised the SDK's actual object type. The fix is a
  single `.to_dict()` boundary in `StripeOwnerGateway` (`_plain()`), so
  every object crosses into domain code as a plain dict before any mapping
  function sees it.
- **The sandbox's default currency was not USD.** A fresh reviewer account
  can default to a currency other than USD; `invoice_items.create` requested
  `"currency": "usd"` explicitly while `invoices.create` did not, and Stripe
  rejected the mismatch the first time an invoice was created against an
  account whose default was CAD. The fix at the time was to pass
  `"currency": "usd"` explicitly on every create call. That held until a
  genuinely Canadian sandbox showed it was the wrong fix — see the two
  entries near the end of this section.
- **A re-approvable-confirmation bug, caught in review.** The original
  `execute_pending` marked a failed confirmation as `failed` but did not
  commit that write before re-raising in two of its three failure paths; if
  the surrounding transaction then rolled back on the exception, it could
  undo the `pending → executed` claim along with it, leaving a supposedly
  failed action stuck as `pending` and re-approvable. The fix commits the
  claim and every terminal status change immediately, before any exception
  can propagate past it, and a regression test asserts an unregistered or
  invalid stored action ends up `failed` and never executable again.
- **Formatting crossed channels.** A first walkthrough asked for "a list of
  all payments made today" and got a wall of text: the model had written a
  correct Markdown bulleted list, but the web bubble rendered it as a bare
  string, so the browser collapsed every newline into a space. The deeper
  problem was that no prompt stated an output format for conversational
  answers, so each model chose its own — and the two channels can display
  different things. The web app can render GitHub-flavored Markdown;
  Telegram renders only a three-tag HTML dialect (`<b>`, `<i>`, `<code>`),
  has no lists or tables at all, and rejects the *whole message* on any
  parse error, so a stray `<u>` or an unescaped `&` would mean the customer
  receives nothing. The solution is one system message per channel, each
  carrying its own formatting contract — Markdown lists and tables and no
  retyped ids for the owner, three tags and no Markdown for the customer —
  built by two separate functions so there is no call that could pair the
  wrong two, with a test that neither prompt contains the other's rules.
  Neither side trusts the prompt: `react-markdown` renders the web text
  (raw HTML is escaped to visible text, `javascript:` links are emptied),
  and every Telegram send passes through a sanitizer that keeps balanced
  allowed tags, escapes reserved characters, strips unknown tags, and
  downgrades to plain text on any nesting Telegram forbids — the prompt
  asks for the format; the boundary guarantees a deliverable message.
- **Three wasted round-trips, found by watching the trail.** The same
  walkthrough's event trail showed the planner recovering from its own
  mistakes, each costing a model call: it sent `null` for every parameter
  it left unset, which failed validation on a defaulted integer (the
  executor now treats `null` as omitted); it presented twenty of
  twenty-one payments as "all of them" because the observation truncated
  silently (it now reports `matched_count` and `listed_count`); and one
  reply carried a second JSON object after the first, which a
  first-`{`-to-last-`}` slice could not parse (the parser now decodes the
  first complete object and ignores what follows). None of these were
  visible before the trail made every step an event.
- **An SSE framing mismatch, also caught only in final review.** The server
  streamed sse-starlette's default `\r\n`-separated frames while the
  frontend's hand-rolled parser split on `\n\n`; both curl and httpx's
  `iter_lines()` normalize line endings, so every manual check and every
  existing test looked fine while a real browser would have received zero
  events — a reminder that streaming contracts need a raw-byte test, not
  just a line-normalized one.
- **Errors that read as stack dumps.** With everything working, a
  walkthrough of the owner web app hit a model call that failed, and what
  the owner saw was `Error code: 400 - {'type': 'error', ...}`: both LLM
  backends had put the SDK's message straight into the envelope's `hint`,
  the one field reserved for "what to do next". The same pass found the
  planner's self-corrections rendered as "Malformed JSON in the model
  reply", a Stripe failure inside a turn shown as a `{"error": ..., "hint":
  ...}` block, and an unanticipated exception either answering a bare
  "Internal Server Error" or, once the SSE stream had opened, ending the
  turn as an empty bubble. The `{code, message, hint}` envelope had been
  designed precisely so that errors carry a fix; the failure was developer
  text leaking into fields written for the owner. The first instinct, a
  filter in the frontend, does not work: the browser cannot tell a
  hand-written hint from an SDK dump, and that raw text is exactly what a
  reviewer wants when something goes wrong on their machine. So the split
  lives on the server. Errors gained a fourth field, `detail`, for
  developer text; the HTTP envelope and SSE error frames carry it only when
  the API runs with `DEBUG=1`, and it always goes to the API log, so the
  default hides nothing from whoever runs the process. One build serves
  both readers, the web app needs no flag of its own, and the trail keeps
  every step visible: a planner retry is one sentence with the parse error
  behind the flag, a failed action is a sentence under the ERR stamp
  instead of a JSON block, and a crash mid-stream is a final error frame
  rather than silence.

- **Charts without the model in the loop.** The redesign added four
  visualizations — a three-week trend, today by hour, top customers, and a
  two-period comparison inside an answer — and the tempting shortcut was to
  have the model emit chart data alongside its prose. That would have put
  numbers the owner reads in the one place the design forbids them: the
  model's output. Instead the charts read a new no-LLM route,
  `GET /api/summary/series`, computed the same way as the daily facts, and
  the comparison chart is derived from the two ranged `query_payments`
  observations already streamed in the turn, which now carry zero-filled
  `daily_totals`. The first live run showed why that data has to stay out of
  the model's reach: with per-day totals in the observation, the planner ran
  a single two-week query, split it in half itself, and reported the cents as
  dollars — the exact arithmetic the loop exists to prevent. Interface-only
  data now travels under a `display` key that the loop strips from what the
  model reads, so the trail and the web app get the whole result and the
  planner sees the observation it always saw. The audit log showed the same
  planner had been inconsistent on this question all along — sometimes two
  7-day queries, sometimes one 14-day query and ninety-one rows summed by
  hand — so it also gained `compare_periods`, an action that returns both
  totals and the change as facts; the chart reads that single observation.
  Two more things surfaced doing it. Today's seeded payments carry
  Stripe's real timestamp — whatever hour the reviewer ran the seed — so an
  "8am to 6pm" chart could silently lose all of them; the series returns all
  24 hours and the axis widens to include any activity outside business
  hours. And the design's confirmation card leads with a figure and a name
  that existed only inside the summary sentence; parsing prose in the
  browser was the wrong place to get them, so proposals now carry structured
  details alongside the sentence, and the card falls back to the sentence
  when a restored proposal has none. The hero also exposed the summary
  narrator: with the Python figure of $2,578.00 sitting beside its prose, the
  model's "$257,800.00" — cents read as dollars — was suddenly impossible to
  miss. Both narrators now receive every amount pre-formatted in the
  account's currency, so the prose can only copy a figure, never convert one.
- **A design handoff as a spec.** The visual redesign was produced in Claude
  Design as a handoff bundle — tokens, component classes, reference React
  components, and a full-page kit — and treated as the spec: the bundle is
  installed as a Claude Code skill so the values travel with the repository,
  and `web/src/styles/` mirrors it rather than forking it. The kit did not
  account for two production realities, Markdown inside the assistant's
  bubbles and a loading state before facts arrive, which are the only
  additions the production stylesheet makes.
- **Eight seconds of "syncing…".** The first smoke test of the redesigned
  page opened on a dash where the figure should be, gridlines where the chart
  should be, and a masthead that said "syncing…" for eight seconds. It looked
  broken. The first step was to measure rather than guess: `make timing`
  (`scripts/time_reads.py`, committed before any fix so the result would be a
  before-and-after) times every read the page makes, alone and fired together
  the way the page fires them. The cause was not the model. Every dashboard
  read lists the whole account from Stripe with charge and customer
  expansions, because seeded history is dated by metadata rather than
  `created` and cannot be filtered server-side — a cost the design accepted
  knowingly and then paid once per read, three times on load and twice per
  poll. Three changes, one commit each. `CachedGateway` wraps the Stripe
  gateway behind the same protocol and answers the three listings from one
  fetch for a 20-second TTL: concurrent misses wait on a single fetch, and the
  process's own writes forget exactly what they change (a refund drops
  payments, paying an invoice drops payments and invoices). The TTL sits
  below the page's 30-second poll so no poll serves numbers older than one
  TTL, which also bounds how late the bot's payments reach the owner's
  screen: at most one poll later than before. The API warms that cache at
  startup, off the request path. And the browser keeps the last good numbers
  in `localStorage`, so a reload paints them at once under an honest
  "synced 3m ago", refuses a snapshot from another day, and swaps in fresh
  data when it lands; the trend says "Loading three weeks of takings…" on a
  genuinely cold start instead of showing bare gridlines.

  | Read on page load | Before | After, cache warm |
  | --- | --- | --- |
  | Facts (hero, pills, unpaid) | 9.2s | 0.00s |
  | Series (trend, hourly, top customers) | 9.6s | 0.00s |
  | Narrated summary (includes the model) | 8.9s | 2.3s |
  | Three poll reads fired together | 8.5s, two listings | one listing shared (7.7s cold, ms warm) |

  What was deliberately not done: a local mirror of Stripe, synced
  incrementally by `created` and, in production, by webhooks, would make even
  the cold path instant. It would also make SQLite a second source of truth
  for money, which this design avoids on purpose, so it stays the named
  production path rather than something built for the submission.

- **A retry loop that taught the planner to keep failing.** A follow-up
  question — "when was this done?" — produced three `planner_retry` lines in a
  row, and the log gave the same reason each time: "No JSON object found in the
  model reply". The extractor tolerates code fences, prose on either side, and
  a trailing second object, so that error means the reply contained no `{` at
  all: the planner had answered in prose instead of proposing a step. The cause
  was the correction itself. On a parse failure the loop fed the reply back
  through `_feedback`, which records it under the assistant role — and a model
  imitates its transcript, where the strongest example is its own last turn. So
  each retry left a stronger case for answering in prose than the one before
  it. Those three attempts plus the `summarize_day` that followed spent four of
  the five steps a turn is allowed, and the fifth had to be terminal, which is
  why the answer was a bare date and the timestamp took a second question. A
  reply that does not parse is now corrected without being recorded: the loop
  states the error, repeats the required shape as a user message, and drops the
  reply. The two retry paths whose replies *did* parse still feed their step
  back, because protocol-shaped JSON is a useful example. The old test could
  not have caught this — a scripted planner recovers on cue whatever the
  transcript says — so the new one asserts against the transcript itself.

- **A Canadian sandbox, and an invoice currency that could not be argued
  with.** Seeding a second test account stopped on "You cannot combine
  currencies on a single invoice. This invoice has invoice items currency usd
  that conflicts with the invoice currency cad." The seed had named
  `"currency": "usd"` on every create since its first commit, so the parameter
  was not the problem. Stripe's rule is that a customer is single-currency: the
  first invoice or invoice item raised against it fixes that currency
  permanently, and where nothing else has decided, the account's own default
  does. The account's `country` was CA, so its default was CAD — the customer
  locked to CAD, and a USD line item on a CAD invoice is the one combination
  Stripe refuses. The 161 USD payment intents written moments earlier had not
  helped, because a payment intent locks nothing.

  What made it worth stopping for was the blast radius rather than the error.
  The brief never says USD; it writes `$` four times and nothing else, and `$`
  is CAD in Canada. Stripe gives a new sandbox the currency of its country, so
  a reviewer outside the US meets this on their first command — and meets it
  *after* the seed has created around 136 payment intents. Payment intents and
  charges cannot be deleted, and `--force` removes only customers and invoices,
  so there is no recovery: the account keeps the wreckage. The sandbox this
  surfaced in still holds one CAD payment intent among 161, two CAD invoices
  among five, and one customer that is CAD for good. The seed now reads the
  account's `default_currency` before creating anything and names it on every
  write, so the objects agree with each other whatever country the reviewer is
  in. Currencies with no minor unit — JPY, KRW and the rest — are refused at
  that same point rather than mishandled, because every amount here is an
  integer number of cents and there is no honest way to express one of those in
  a currency that has none.

- **Then the rest of the app had to follow.** Reading the account fixed the
  seed and left the same hole open in the gateway the chat box uses: the
  invoice item behind "Create a $250 invoice for Acme" and the price behind
  every payment link still said `"usd"`, so the assistant could raise the
  exact error the seed had just stopped raising — or, for a payment link, not
  fail at all and quietly charge the wrong money. The gateway now resolves the
  account's currency once per process and keeps it, and every place money
  becomes text asks the gateway rather than assuming: the confirmation
  summaries, both narrators, and the planner prompt — which matters more than
  it looks, because the planner reads raw `*_cents` integers and renders the
  figure itself, so an untold planner writes "$1,200.00" on a Canadian account
  no matter what the page shows. The web app learns the currency from one
  field on the summary response and holds it in a context, so the charts do
  not carry it as a prop; `Intl.NumberFormat` renders it there and a small
  table mirrors the same symbols in Python, so `CA$1,200.00` reads identically
  in a narrated sentence and beside a bar. Two decisions were deliberate. The
  $2,000 Telegram ceiling is 200,000 cents of *the account's* currency — the
  brief writes "$2,000" and nothing more, and a fixed number of minor units
  keeps it an invariant with no exchange rate in it. And the currency lives on
  the gateway rather than as a new field on the action contexts: it is a fact
  about the account the gateway fronts, and asking for it there meant no
  change to the thirteen tests that build those contexts by hand.

- **The smoke test had to learn what the code learned.** The manual
  walkthrough is a browser page rather than a test file: twelve stages in
  the order a reviewer meets them, eighty-eight checks of one thing to do
  and one thing to expect, each ticked or flagged, the flags copied back as
  a report to work through. It was written against the first sandbox and it
  aged in three ways this session exposed. It pinned dates — "Wednesday,
  September 2", "due Fri Sep 11". It assumed dollars in every expectation.
  And it carried the old account's stray history as part of the baseline.
  The revision starts from an empty sandbox the way the reviewer's run will:
  a new key, the local database moved aside because its Telegram bindings
  and audit rows name customer ids that exist only in the old account, and
  the browser's last-known numbers cleared once, since the page paints them
  before it asks. It has one check for each thing fixed here — a short
  follow-up question that must not spiral into three ERR lines, every
  object in the Stripe dashboard in the account's own currency, `currency`
  on the summary response — and it marks the two admitted limitations, the
  UTC timestamp and the declined chart, as not-a-flag so a run does not
  chase what this document already concedes. Because the reviewer's
  currency is unknown, every figure a reader *sees* sits behind a
  placeholder that a control at the top of the page swaps for the account's
  symbol; what a reader *types* stays "$250", the brief's own wording, which
  the planner reads in whatever currency the account settles in.

## Limitations / with more time

- **Native tool calling was deliberately not used.** The propose-execute
  loop gives up whatever reliability edge a provider's post-trained tool
  format offers, in exchange for legibility (every step is an event we
  control), portability (one code path across providers), and testability
  (the executor runs on plain JSON with no model or network). At roughly
  ten actions per registry that trade does not bite; at fifty it would, and
  native tool calling would be worth revisiting.
- **On-demand queries instead of webhooks.** Stripe webhooks would make the
  summary and the live rail push-driven instead of polled, but they need a
  public URL and therefore a tunnel — a wall between the reviewer and the
  rest of the demo. Production would use them.
- **Email verification for Telegram binding**, instead of a token the seed
  script hands out — the honest production version of the identity
  boundary described above.
- **No session auth, multi-owner support, or rate limiting.** This is a
  single-owner proof of concept behind one bearer token.
- **Frontend tests cover logic, not layout.** The web suite pins the Markdown
  renderer, error presentation, the pure functions behind the charts (local
  day and hour labels, trend stats, comparison detection, the summary aside
  split), and the components that carry behaviour: the confirmation card's
  figure-or-sentence fallback, the receipt grid per action, the error strip,
  the comparison chart's shared scale, and the thread's chart wiring and
  retry. Layout and colour are checked by eye against the UI kit, not by
  snapshot, and the backend still carries the claims worth proving (the
  ceiling, scoping, confirmation integrity, the `occurred_at` concession,
  executor validation).
- **Stripe pagination beyond demo scale.** Listing and filtering happen in
  Python over `auto_paging_iter()`. A 20-second cache shares each listing
  across the reads that arrive together and is warmed at startup, which keeps
  the page instant at ~200 objects; at production volume the cold listing
  itself would be the problem, and the answer is a local mirror synced by
  `created` and webhooks, deliberately not built here because it makes
  SQLite a second source of truth for money.

- **Turn memory is text-only.** A turn's observations live only as long as the
  turn; what persists is the question and the answer. A follow-up about a fact
  already fetched therefore re-fetches it, and may reach for a different action
  than the one that had it — `summarize_day` returns aggregates, so it cannot
  answer "when". Storing each turn's steps beside its text would fix that and
  would also stop prior turns from modelling prose replies, but it changes what
  `GET /api/conversations/{id}` returns, so it is recorded here rather than
  done.
- **One timestamp escapes the local clock.** Every figure the app computes is
  bucketed in the owner's timezone, but a payment row's `occurred_at` reaches
  the planner as raw UTC, so an answer that quotes one states a time in a
  different zone from the charts beside it. Formatting it like every other date
  is a small change that arrived too late to make.


- **Totals trust the account to be single-currency.** Every write names the
  account's currency, so an account seeded by this project cannot hold two.
  But the domain records do not carry a currency and the totals do not check
  one, so an account contaminated before the fix — the sandbox this was found
  in still holds one CAD payment intent among 161 USD — sums the stray cents
  as if they were the account's own. Carrying `currency` on `Payment` and
  `Invoice` and filtering the totals to the account's is the small remaining
  piece; it defends only against data the seed can no longer produce.

## Bonus: the escalation loop

A payment at or above $2,000 does not just fail on the Telegram side — it
files an escalation the owner's web app surfaces in a dedicated panel, and
approving it sends the customer a Stripe-hosted payment link back through
the same chat. It was chosen because it is Replicant's own product pattern
in miniature: automation handles the routine case, escalates cleanly to a
human when it hits a limit, and resumes once that human acts — and because
it turns what could have been two disconnected deliverables (a bot, a web
app) into one loop that closes.

It also doubles as the answer to a question the brief does not ask
directly but a payments assistant cannot dodge: what happens at the
highest-stakes action available. Rather than push another one-time code to
a device that might be the compromised one, the ceiling routes the decision
out-of-band to the owner, who approves from a separate, already-authenticated
channel. That is a stronger security property than an in-band second factor
would have been, not a weaker one.

## Bonus: a designed owner app

The brief's owner interface could have stayed a chat box. The redesign gives
it the shape a bookkeeper would recognise: the app speaks first with a
narrated summary and the day's figure, three weeks of takings sit above the
conversation, and the rail answers the questions an owner asks before they
type — when today got busy, who pays the most, what is still unpaid, what
needs a decision. Comparisons the assistant makes are drawn as well as said.
None of it changes what the assistant can do; it changes how quickly the
owner can read what it did. The design itself was produced in Claude Design
and is checked in as a skill, so the visual language is as reproducible as
the seed data. One flourish is deliberate theatre: the narrated summary
arrives whole, but a cursor blinks in the greeting while the model writes
and the aside and lede then type in, bold figures kept intact mid-reveal, so
the page reads as an assistant speaking rather than a form filling in.
Reduced-motion readers get the text at once.
