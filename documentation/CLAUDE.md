# documentation/ — Obsidian vault

**Follow `.claude/rules/documentation.md` before creating or editing any file
here.** It is the authoritative rule set for this directory.

The short version, so nothing is missed if that rule has not loaded:

- Relative markdown links with the `.md` extension. Never Obsidian wikilinks or
  embeds — CI rejects them.
- Lowercase kebab-case filenames.
- **Never rename or move a file in this vault.** Propose it; a human does it in
  Obsidian so backlinks are rewritten. Creating and editing is fine.
- New notes require `title`, `status`, and `updated` frontmatter. Preserve every
  existing key when editing.
- No Dataview, Templater, or other query blocks.
- Assistant-generated notes go in `generated/`. Ask before editing `adr/` or
  `decisions/`.

Run `./scripts/check-docs.sh` before committing changes here.

Prose explaining *why* these rules exist lives in `conventions.md`. This file
and the rule are the operational subset; when they disagree with the vault
notes, the vault notes win.
