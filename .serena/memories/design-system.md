# Web app design system

The owner web app (`web/`) is styled by the Ledger design system, redesign
option 1b "Bold", produced in Claude Design and handed over on 2026-09-02.

- **Source of truth:** `.claude/skills/ledger-design/` (tokens, `.ldg-*`
  component classes, reference `components/core/*.jsx`, guidelines, a
  full-page UI kit at `ui_kits/ledger/index.html`). Invoke with
  `/ledger-design`. `web/src/styles/tokens/*` and `web/src/styles/components.css`
  mirror it; `layout.css` and `prose.css` are the production-only additions.
- **Handoff spec:** `documentation/generated/ledger-design-handoff.md`.
  Review canvases: `documentation/assets/design-mockups/*.dc.html`.
- **Rules that matter:** warm paper + near-black ink; green = money in,
  coral = money out, amber = waiting on the owner; serif (Instrument Serif)
  only for the human voice (greeting, escalation headline); JetBrains Mono for
  every number with `tabular-nums`; no shadows, no icons, no emoji; sentence
  case; figures always two decimals except averages.
- **Charts never read model text.** Trend, hourly, and top customers come from
  `GET /api/summary/series` (`app/domain/series.py`, no LLM). The inline
  two-period comparison chart is derived in `web/src/lib/comparison.ts` from
  two ranged `query_payments` observations in the turn, which carry
  zero-filled `daily_totals`.
- **Confirmation card** leads with `ProposalDetails` (amount, counterparty,
  meta) from the confirmation event; falls back to the summary sentence when
  a restored pending proposal has none (details are not persisted).
- **Frontend tests** (`vitest`, `web/src/**/*.test.*`) cover the pure
  functions in `web/src/lib/` and the behaviour-carrying components; layout is
  checked by eye against the UI kit. `src/test-setup.ts` registers Testing
  Library cleanup.
