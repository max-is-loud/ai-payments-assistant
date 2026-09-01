# Project conventions

Authoritative copies live in the `documentation/` Obsidian vault. This memory
is the short form for tool use; when the two disagree, the vault wins.

## Documentation vault

- The vault is `documentation/`, **not** `docs/`. Git is the source of truth;
  Obsidian is only a reading and graph UI. No Obsidian REST API or MCP plugin
  is used — edit the markdown directly.
- **Relative markdown links only**, always with the `.md` extension:
  `[Text](../path/to/note.md)`. Obsidian double-square-bracket wikilinks and
  embeds are banned and fail CI.
- Filenames are lowercase kebab-case.
- **Never rename or move a file under `documentation/`.** Propose it and let a
  human do it in Obsidian so backlinks are rewritten. Creating and editing is
  fine.
- Frontmatter: `title`, `status`, `updated` required on new notes. Preserve
  every existing key when editing; never rewrite the YAML block wholesale.
- No Dataview, Templater, or other query blocks — notes must render as static
  markdown in a PR diff.
- Assistant-generated notes go in `documentation/generated/`. Do not edit
  anything under `documentation/adr/` or `documentation/decisions/` without
  asking first.

CI (`.github/workflows/docs.yml`) enforces two checks: a grep guard rejecting
wikilinks, and `lychee --offline` proving relative paths resolve. Run both
locally with `./scripts/check-docs.sh` (needs `brew install lychee` for the
second check).

## Python code

- **Every function carries a Google-style docstring**, public and private
  alike, plus module and class docstrings.
- Docstrings are written **for humans**. Serena and Graphify supply the
  machine-readable context, so docstrings explain intent, non-obvious
  constraints, units, and why errors are raised — not a restatement of the
  signature, and never types (annotations carry those).
- Full type annotations on every parameter and return value.
- Inline comments explain **why**, never **what**.
- `snake_case` module names; the filename names the responsibility
  (`refunds.py`, not `payment_utils.py`).

## Module boundaries — no god files

- A module has **one reason to change**. A second reason means split.
- Tripwire, not a rule: past 300 lines justify the file; past 400 split it.
- Smells: a name needing "and"; `utils`/`helpers`/`common`/`misc`; imports
  spanning unrelated concerns; one file edited for every feature change.
- Each module answers on sight: what it does, how to use it, what it depends
  on.

## DRY, bounded by YAGNI

- **DRY applies to duplicated knowledge, not duplicated characters.** Two
  functions that look alike but change for different reasons are not
  duplication; merging them creates harmful coupling.
- **Extract on the third occurrence.** Two examples usually guess the
  abstraction wrong, and a wrong abstraction costs more than the duplication.
- **Always single-source** business rules, limits, thresholds (e.g. the
  payment ceiling appears exactly once).
- YAGNI forbids: unused parameters, config with one value, an ABC with one
  implementation, empty plugin points, unhandled-case handling.
- Test before abstracting: **name the second caller.** If you cannot, do not
  build it.

## Tooling boundaries

- Serena self-manages `.serena/.gitignore` (`/cache`, `/project.local.yml`).
  Do not blanket-ignore `.serena/` at the repo root. Committed:
  `project.yml`, `memories/`.
- Nothing under `graphify-out/` is committed — all regenerable, large, and
  churns every rebuild. Upstream docs give no guidance; this was decided here.

## Context

This repository is a take-home assessment for Replicant.ai: an AI payments
assistant over Stripe, with a FastAPI backend, a React SPA, and a Telegram
bot for external customers. The reviewer runs it against **their own** Stripe
test account, so nothing may depend on hand-created dashboard data — a seed
script must populate everything.
