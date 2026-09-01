# AI payments assistant

Take-home assessment for Replicant.ai. An AI assistant over a Stripe account,
in three parts: a FastAPI backend with a React SPA for the business owner, a
Telegram bot for their external customers, and a seed script that populates a
fresh Stripe sandbox.

**Status:** design approved, implementation not started. The design of record is
`documentation/specs/2026-09-01-ai-payments-assistant-design.md`. Requirements
are `documentation/assignment-brief.md`. Read both before changing architecture.

## Conventions live in rules — follow them explicitly

Two path-scoped rule files carry the project's conventions. **Read the relevant
rule and follow it before writing or editing a file it covers.** They load
automatically when a matching file is read, but not always when creating a new
one, so load them yourself when starting fresh work:

- `.claude/rules/code-style.md` — applies to `**/*.py`, `**/*.ts`, `**/*.tsx`.
  Google-style docstrings on every Python function, full type annotations, no
  god files, DRY bounded by YAGNI.
- `.claude/rules/documentation.md` — applies to `documentation/**/*.md`.
  Relative markdown links only, frontmatter requirements, and a hard rule
  against renaming or moving vault files.

`documentation/` is also covered by its own `documentation/CLAUDE.md`.

## Documentation

`documentation/` is an Obsidian vault that doubles as the project's
documentation. Git is the source of truth; Obsidian is only a reading and graph
UI on top of plain markdown. Never install or depend on an Obsidian REST API or
MCP plugin — edit the files directly.

Start at `documentation/index.md`. It links the design spec, the assignment
brief, the code conventions and their reasoning, and the tooling notes.

## Constraints that are easy to get wrong

- **The reviewer runs this against their own empty Stripe test account.**
  Nothing may depend on data created by hand in a dashboard. The seed script is
  a graded deliverable.
- **Stripe assigns `created`; it cannot be set.** Historical seed data carries
  `metadata.demo_created_at`, resolved in exactly one domain-mapping function.
  Nothing downstream reads that field.
- **The $2,000 Telegram ceiling and per-customer scoping are Python
  invariants, never prompt instructions.** The bot's action registry contains no
  action that accepts a `customer_id`.
- **Secrets never enter the repository.** `.env` and `telegram_bot.md` are
  gitignored. The Telegram bot token is in agent-vault under
  `replicant-assignment-telegram-bot-token`.

## Tooling

- **Serena** is the semantic code index. Prefer its symbolic tools over
  reading whole files. `.serena/project.yml` and `.serena/memories/` are
  committed; `cache/` and `project.local.yml` are not.
- **Graphify** builds the knowledge graph. Nothing under `graphify-out/` is
  committed — all of it is regenerable and large.

## Commands

```bash
./scripts/check-docs.sh    # wikilink guard + link resolution; run before committing docs
```

Application commands (`make install`, `make seed`, `make dev`, `make test`)
arrive with the implementation. Do not document a command here before it works.

## Git

Commit regularly with meaningful messages — the brief asks to see how the work
came together. Never commit `.env`, API keys, or the Telegram bot token.
