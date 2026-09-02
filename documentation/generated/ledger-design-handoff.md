---
title: Ledger design handoff
status: active
updated: 2026-09-02
---

# Handoff: Ledger owner app redesign ("1b — Bold")

## Overview
Restyle the owner-facing web app (`web/`, React + Vite) of the AI payments assistant from the current cool-grey/indigo look to the warm-paper editorial design chosen in review, and add four data visualizations: a 3-week daily trend, today's payments by hour, top customers, and an inline two-week comparison chart inside the assistant's answer. Behaviour (agent loop, SSE trail, confirmation → receipt, escalations) is unchanged.

## About the design files
Everything in this bundle is a **design reference written in HTML**, not production code to paste in. Recreate it inside the existing `web/src` React app using its patterns (function components, `apiFetch`, `useConversation`, `formatUsd`). The `ledger-design-system/` folder is the source of truth for values; its `components/core/*.jsx` are reference implementations you may port to TSX nearly verbatim.

## Fidelity
**High-fidelity.** Colors, type, spacing, radii and copy are final. Recreate pixel-perfectly.

## Files
- `ledger-design-system/ui_kits/ledger/index.html` — the target screen, all states, light + dark toggle. Open it in a browser.
- `ledger-design-system/tokens/*.css` — colors (light + `[data-theme="dark"]`), typography, spacing/radii.
- `ledger-design-system/components/components.css` — every `.ldg-*` class; can replace `web/src/styles.css` wholesale.
- `ledger-design-system/components/core/*.jsx` + `.d.ts` + `.prompt.md` — reference React components.
- `ledger-design-system/readme.md` — design guide (voice, foundations, codebase mapping).
- `ledger-design-system/SKILL.md` — drop the folder into `.claude/skills/ledger-design/` to use it as a Claude Code skill.
- `mockups/Ledger - Redesign Options.dc.html` — the review artifact (option 1a and 1b side by side); `mockups/Ledger - Current.dc.html` — recreation of today's build. Both need `mockups/support.js` alongside.

## Screens / Views

### Owner home (`App.tsx`) — single page, 1280 design width, `max-width:1200px` content, 40px gutters
Top to bottom:

1. **Masthead band** — full-bleed `--band #15130e`, `14px 40px` padding, flex space-between. Left: "Ledger" in Instrument Serif 26px `-0.01em` + "PAYMENTS ASSISTANT" mono 11px uppercase `.08em` `--band-ink-3`. Right: mono 12px `--band-ink-3`: `● Stripe test mode · synced 12s ago` (6px green dot) and the long date ("Wednesday, September 2"). Replaces today's `.masthead`.
2. **Hero** — grid `minmax(0,1fr) 380px`, gap 48, `align-items:end`, hairline bottom, `padding-bottom:28px`.
   - Left: eyebrow "Today, in a sentence"; `<h1>` serif 44/1.05 `-0.015em` "Good morning." + `<em style="color:var(--ink-3)">` a one-clause aside the LLM writes ("A strong Wednesday."); lede 19/1.45 `--ink-2` max 60ch, `<strong>` 600 in `--ink`. Content = `summary.text` (Markdown) from `GET /api/summary/today`.
   - Right (text-align right): eyebrow "Taken today"; figure mono 500 56px/1 `-0.03em` `--in`, cents at 28px `--ink-3`; pill row (gap 8): `+80.5% vs yesterday` (green, `--in-soft` bg, green border), `18 payments` (hairline), `2 declined` (coral border/text). From `facts.today` / `facts.yesterday`.
3. **Trend** — `padding:24px 0 28px`, hairline bottom. Header row: eyebrow "Taken per day · Aug 12 – today" left; right mono 12px stats "3-week total **$18,690.00** · Weekday avg **$886** · Best day **Today**(green)". Chart: 170px tall; 4 gridlines (3 dashed + bottom solid, `--rule`); y-max label mono 11px `--ink-3` top-left; SVG `viewBox 0 0 1000 170` `preserveAspectRatio="none"`, area fill `--in` at 14% opacity, line `--in` 2px `vector-effect:non-scaling-stroke`; 10px green dot with 2px `--paper` border at the last point, `right:-5px`. Axis below (mono 11px `--ink-3`): first date, two mid dates, "Today" in green.
4. **Main grid** — `minmax(0,1fr) 340px`, gap 48, `padding-top:28px`.
   - **Thread** (gap 22 between turns; 12 inside a turn):
     - User bubble: `--user` bg / `--user-ink` text, `10px 16px`, radius `18 18 4 18`, max 70%, right-aligned.
     - Trail: unchanged from `Trail.tsx` (2px left rule, 52px stamp column, stamps mono 11px `.08em`; ACT green, ASK amber, ERR coral, others `--ink-3`; line 14px `--ink-2`).
     - Assistant bubble: `--card` bg, hairline, radius `4 18 18 18`, `18px 20px`, max 88%. `p` 16px; `p.small` 14px `--ink-2`.
     - **Inline comparison chart** (when the answer compares two periods): two columns gap 24; each: eyebrow (period; green for the later one), figure mono 26px 500 `-0.02em` (`$4,610` + ` · 38` in `--ink-3` 14px), 7 bars 56px tall gap 4 radius 2 (`--bar` muted for earlier period, `--in` for later; shared max so heights are comparable); axis "M T W T F S S" mono 10px.
     - Confirmation: assistant-bubble shape, `--wait` border + `--wait-soft` bg, one 900ms amber pulse. Eyebrow "Needs your approval" in `--wait`; row: figure 30px coral `−$45.00` + "to **Maya Chen**" 16px; meta 14px `--ink-2` "Consulting · pi_… · paid today at 09:14"; actions gap 8 margin-top 14: primary "Approve refund" + secondary "Cancel". After decision: replace actions with eyebrow "Approved"/"Cancelled".
     - Receipt (`ResultCard`): assistant bubble; grid `auto 1fr auto` gap `4px 24px` align center; head spans all: green eyebrow with 6px dot "Refund issued"; figure 30px coral; description 14px `--ink-2` "to Maya Chen · `re_…`"; pill solid green "SUCCEEDED". Same grid for invoice/link/escalation results (figure → description → status pill).
     - Error: `border-left:3px solid --out`, `--out-soft` bg, radius `0 12 12 0`, `12px 16px`, text 14px `--out`, flex with "Retry" danger button (coral outline, 6/14 padding, 13px). One sentence only; developer detail stays in the trail ERR line behind `DEBUG`.
     - Composer: `--card`, 1px `--ink` border, radius 999, `padding 6px 6px 6px 20px`; input 15px transparent; ink Send button. Not sticky (page is short).
   - **Rail** (gap 28, borderless sections): eyebrow with `padding-bottom:8px` hairline, `margin-bottom:10px`.
     - "Today by hour": 11 bars (8am–6pm) 56px tall gap 5 in `--ink`; axis `8am · 1pm · 6pm`; note 14px `--ink-2` ("Busiest at 3pm: $486.00 across 3 payments. Nothing before 9.").
     - "Top customers · 3 weeks": ranked rows grid `20px 1fr auto` gap 10: rank `01` mono 11px `--ink-3`; name 14px + 3px track (`--rule` bg, `--ink` fill, width = share of #1); value mono 14px 500 tabular.
     - "Unpaid · $3,780.00": rows 14px space-between, description in `--ink-3`, amount mono. From `facts.open_invoices`.
     - **Escalation card** (one per pending escalation): `--card`, 1px `--wait` border, radius 14, `16px 18px`. Header: eyebrow "Waiting on you" in `--wait` + time mono 11px right. Headline serif 24/1.15: "Acme Corp wants to pay `$2,400.00`" (figure mono 22px 500). Body 14px `--ink-2`. Full-width primary lg button "Approve and notify" → disabled "Approving…" → secondary "Notified on Telegram".

## Interactions & behavior
- Approve/Cancel → existing `approve(action_id)` / `cancel(action_id)`; on `answer`, receipt bubble appears below the (now decided) confirmation, then the text bubble.
- Trail rows: `ldg-rise` 160ms ease-out (opacity 0→1, translateY 4→0). Confirmation: `ldg-pulse` once. Buttons: hover opacity .85; active translateY(1px); focus-visible 2px `--accent` outline offset 2. `prefers-reduced-motion` disables animations.
- Dark mode: toggle `data-theme="dark"` on `<html>`; persist in `localStorage`; default to `prefers-color-scheme`. Optional small secondary button in the band (see kit).
- Responsive ≤960px: hero and main collapse to one column; hero right column left-aligns.
- Loading: hero lede shows `.ldg-empty` "Reading today's activity…"; charts render with all-2px bars until facts arrive.

## State management
Unchanged: `useConversation` (turns, busy, error, send/approve/cancel), `summary`, `facts`, `escalations`, `approving`, 30s `refreshFacts` poll.
New: `theme` ('light'|'dark'); `series` from the new endpoint below.

## Data / API additions (backend)
Add a no-LLM read, e.g. `GET /api/summary/series`, computed in `app/domain/summary.py` from `gateway.list_payments()` (same 21-day + today window the seed produces):
- `daily: [{date, succeeded_total_cents, succeeded_count}]` — 22 entries, oldest first (area chart, comparison bars, weekday avg / best day).
- `hourly_today: [{hour, succeeded_total_cents, succeeded_count}]` — hours 8–18.
- `top_customers: [{customer_name, succeeded_total_cents}]` — top 5 over the window.
The comparison chart inside an answer uses `query_payments` observations already in the turn's events (`start_date`/`end_date` + totals); if two `query_payments` observations with date ranges are present in a turn, render the chart above the text bubble. For per-day bars there, either extend `query_payments` to return `daily_totals` or call `/api/summary/series` and slice.

## Design tokens
Light (`:root`): `--paper #f3f0e8`, `--card #fbf9f4`, `--band #15130e`, `--rule #dcd6c7`, `--bar #cfc8b6`, `--ink #15130e`, `--ink-2 #524c40`, `--ink-3 #8b8576`, `--band-ink #f3f0e8`, `--band-ink-3 #9d978a`, `--in/--accent #0a6b4f`, `--in-soft #d9ebe1`, `--accent-soft #e1efe7`, `--out #c1432c`, `--out-soft #f4e0da`, `--wait #a8690a`, `--wait-soft #f3e7cf`, `--user #15130e`, `--user-ink #f3f0e8`.
Dark (`[data-theme="dark"]`): `--paper #0e0e0c`, `--card/--band #171613`, `--rule #2b2922`, `--bar #2e2c25`, `--ink #f1ede3`, `--ink-2 #c7c1b3`, `--ink-3/--band-ink-3 #857f70`, `--in/--accent #4fd39a`, `--accent-ink #7be3b4`, `--in-soft #153024`, `--accent-soft #12291f`, `--out #ff8a70`, `--out-soft #3a1f19`, `--wait #e6a94a`, `--wait-soft #332711`, `--user #f1ede3`, `--user-ink #0e0e0c`.
Type: Instrument Serif 400 (44 hero, 26 wordmark, 24 headline); Instrument Sans 400/500/600 (19 lede, 16 answer, 15 body, 14 small, 13 meta); JetBrains Mono 400/500 (56/30/26/14 figures, 11 labels uppercase `.08em`, 10 axis, 12 code) with `font-variant-numeric: tabular-nums`. Google Fonts: `family=Instrument+Serif:ital@0;1&family=Instrument+Sans:wght@400;500;600&family=JetBrains+Mono:wght@400;500` — replace the Bricolage link in `web/index.html`.
Spacing: 4 6 8 10 12 14 16 18 20 24 28 36 40 48. Radii: 2 / 4 / 12–14 / 18 / 999. Shadows: none.

## Assets
None. No logo (wordmark is plain type), no icons (one 6px CSS dot), no images. Fonts from Google Fonts.
