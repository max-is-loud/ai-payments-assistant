# Ledger design system

Ledger is the owner-facing web app of an AI payments assistant built for the Replicant.ai take-home (source: the attached local codebase `assignment1/`, React + Vite SPA at `web/src`, FastAPI backend at `app/`). The owner chats with an assistant that reads and moves money in Stripe; every turn is a PLAN → ACT → OBS trail, mutations pause for approval, and a Telegram bot for customers escalates payments ≥ $2,000 back to this app.

This system formalizes redesign option **1b "Bold"** (`../../../documentation/assets/design-mockups/ledger-redesign-options.dc.html`). v1 (`../../../documentation/assets/design-mockups/ledger-current.dc.html`, from `web/src/styles.css`) used Bricolage Grotesque + indigo on cool grey; 1b keeps v1's bones — two-column grid, agent trail, confirmation-then-receipt — and changes the voice.

## Content fundamentals

- **Second person, present tense, one sentence at a time.** "You took $2,412.00 across 18 payments today." The assistant speaks to the owner as a competent bookkeeper would: plain, specific, never chirpy.
- **Figures are exact and formatted once**: `$2,412.00`, always two decimals, always mono, thousands separated. Percentages to one decimal (`+14.6%`). Never round in copy what the chart shows precisely.
- **Dates are human**: "Aug 24 – 30", "due September 12", "Tuesday Aug 25". ISO dates appear only in trail arguments.
- **Eyebrows are sentence-written, uppercase-rendered**: "Today, in a sentence", "Waiting on you", "Needs your approval", "Refund issued".
- **Errors carry a fix, never a stack.** "The assistant could not finish this turn." + Retry. Developer detail lives behind DEBUG in the trail's ERR line.
- Sentence case everywhere. No exclamation marks. No emoji, ever. No icons except one 6px status dot.
- The serif is the human voice; use it only where a person speaks to a person (greeting, escalation headline).

## Visual foundations

- **Color**: warm paper (`#f3f0e8`) with a stepped card (`#fbf9f4`) and near-black ink (`#15130e`). One green for money in (`#0a6b4f`), coral for money out and errors (`#c1432c`), amber for anything waiting on the owner (`#a8690a`). Each has a soft fill. Dark theme swaps the same tokens under `[data-theme="dark"]`. Green doubles as the link/ACT colour — there is no separate brand accent.
- **Type**: Instrument Serif (display, 400 only, italics for asides in `--ink-3`), Instrument Sans (body 15/1.5, lede 19/1.45), JetBrains Mono (every number, id, eyebrow, stamp, axis; `tabular-nums` always). Hero figure 56px/−.03em with dimmed cents.
- **Spacing**: ladder 4→48 (`tokens/spacing.css`). Page max 1200, 40px gutters, 48px grid gap, 340px rail.
- **Surfaces**: no shadows anywhere. Hierarchy is hairlines (`--rule`) and the paper→card step. The masthead is a full-width ink band.
- **Radii**: 2 bars · 4 bubble tail · 12/14 cards · 18 bubbles · 999 pills/buttons/composer.
- **Bubbles**: user = solid ink, right-aligned, tail bottom-right, max 70%. Assistant = card with hairline, tail top-left, max 88%. Confirmation = same shape in amber. Receipt = three-column grid (figure · description · pill).
- **Rail**: borderless sections with an underlined eyebrow; the escalation card is the only bordered element (amber) because it is the only thing that needs the owner.
- **Charts**: bars (muted baseline / green period-of-interest / ink in the rail, 2px min height), a full-width area trend (14% fill, 2px non-scaling stroke, dashed gridlines, dot on today), and ranked 3px tracks. Charts never carry titles — an eyebrow above and an axis below.
- **Motion**: trail rows rise 4px over 160ms; the confirmation bubble pulses once (900ms amber ring). Buttons dim to 85% on hover, drop 1px on press. Nothing else moves. `prefers-reduced-motion` disables both.
- **Focus**: 2px green outline, 2px offset.
- **Iconography**: none. One 6px dot (`.ldg-dot`) means "live/succeeded". No logo mark — the wordmark is the word "Ledger" in the serif.
- **Imagery**: none.

## Index

- `styles.css` — entry; imports everything below.
- `tokens/colors.css`, `tokens/typography.css`, `tokens/spacing.css`, `tokens/fonts.css`
- `components/components.css` — all `.ldg-*` classes (framework-agnostic; adopt directly in place of `web/src/styles.css`).
- `components/core/` — React: Eyebrow, Figure, Pill, Button, MastheadBand, Trail, Bubble (User/Assistant), ConfirmationCard, ReceiptCard, ErrorStrip, Composer, Bars (+Axis), AreaChart, RankedBars, RailSection, EscalationCard. Each has `.d.ts` + `.prompt.md`.
- `guidelines/` — specimen cards (colors, type, spacing, radii, charts, trail, wordmark).
- `ui_kits/ledger/index.html` — the full owner home screen with click-through.
- `SKILL.md` — Claude Code skill wrapper.

## Mapping to the existing codebase

| Existing (`web/src`) | Replace with |
| --- | --- |
| `styles.css` tokens + classes | `tokens/*.css` + `components/components.css` |
| `App.tsx` masthead | `MastheadBand` + new hero/trend sections |
| `SummaryCard.tsx` | hero left column (`.ldg-hero`) |
| `TodayRail.tsx` | hero right column figure + pills; rail `RailSection`s with `Bars`/`RankedBars` |
| `Trail.tsx` | `Trail` (same logic, `.ldg-trail`) |
| `ConfirmationCard.tsx` | `ConfirmationCard` |
| `ResultCard.tsx` | `ReceiptCard` |
| `Composer.tsx` | `Composer` |
| `EscalationsPanel.tsx` | one `EscalationCard` per escalation |

## Caveats

- Fonts are Google-hosted via `@import`; no binaries are bundled. Self-host if the reviewer may be offline.
- Chart data in the kit is mock, shaped to the seed (18 payments today, 2 declines, $1,200/$2,400 Acme invoices). The API needs one new read (per-day totals for 22 days, per-hour totals for today, per-customer totals) — see the handoff README.
- Intentional additions beyond the source inventory: Figure, Bars/Axis, AreaChart, RankedBars, RailSection, MastheadBand, ErrorStrip — all new to the 1b design.
