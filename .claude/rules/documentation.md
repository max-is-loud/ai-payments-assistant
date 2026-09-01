---
paths:
  - "documentation/**/*.md"
---

# Documentation vault rules

`documentation/` is an Obsidian vault. Git is the source of truth; Obsidian is
only a reading and graph UI. Edit the markdown directly — never install or call
an Obsidian REST API or MCP plugin.

`documentation/CLAUDE.md` is a Claude Code instruction file, not a vault note.
It is exempt from the frontmatter and link rules below and stays out of the
vault's link graph.

## Links

- Use relative markdown links with the `.md` extension: `[Text](../path/to/note.md)`.
- Never use Obsidian wikilink or embed syntax. CI rejects it, and a link
  checker does not recognise it as a link, so a broken one would pass silently.

## Files

- Filenames are lowercase kebab-case, no spaces.
- **Never rename or move a file in this vault.** Propose the change and let a
  human do it in Obsidian so backlinks are rewritten. Creating and editing is fine.

## Frontmatter

- Every new note requires `title`, `status`, and `updated`.
- When editing an existing note, preserve every key already present. Never
  rewrite the YAML block wholesale.

## Content

- No Dataview, Templater, or other plugin query blocks. Notes must render as
  static markdown in a pull request diff.
- Put assistant-generated notes in `documentation/generated/`.
- Do not edit anything under `documentation/adr/` or `documentation/decisions/`
  without asking first.

## Before finishing

Run `./scripts/check-docs.sh`. It runs the two checks CI runs: the wikilink
guard, and `lychee --offline` proving every relative path resolves.
