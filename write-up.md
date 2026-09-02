# Write-up

## Assumptions

- **Single owner, single currency.** The design targets one business owner
  and USD throughout; there is no multi-tenant or multi-currency handling.
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
  account whose default was CAD. Every create call across the gateway now
  passes `"currency": "usd"` explicitly rather than trusting the account
  default.
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
- **Frontend tests cover two boundaries.** The web suite pins the Markdown
  renderer — lists and tables render, raw HTML and `javascript:` links do
  not — and error presentation: the trail's error and failed-action lines,
  developer detail appearing only when the server sends it, and the
  client's wording for a transport failure. Nothing else. The backend
  carries the claims worth proving (the ceiling, scoping, confirmation
  integrity, the `occurred_at` concession, executor validation); the rest
  of the frontend was judged lower-value to cover given the time budget.
- **Stripe pagination beyond demo scale.** Listing and filtering happen in
  Python over `auto_paging_iter()`, fine at ~150 objects, not at production
  volume — that would need server-side filtering or a cache.

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
