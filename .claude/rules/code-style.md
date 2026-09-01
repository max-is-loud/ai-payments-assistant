---
paths:
  - "**/*.py"
  - "**/*.ts"
  - "**/*.tsx"
---

# Code style rules

Reasoning behind these rules is in `documentation/code-conventions.md`. This
file is the enforceable subset.

## Docstrings

- **Every Python function carries a Google-style docstring** — public, private,
  helper, and test alike. Modules and classes carry them too.
- Docstrings are written for **humans**. Serena and Graphify supply the
  machine-readable context, so docstrings explain intent, non-obvious
  constraints, units (cents rather than dollars), assumed state, and why an
  error is raised.
- Do not restate the signature in prose. Do not put types in the docstring —
  annotations carry those, and repeating them creates two places to drift.

## Types and comments

- Full type annotations on every parameter and return value.
- Inline comments explain **why**, never **what**. Code needing a comment to
  say what it does should be renamed or rewritten instead.

## Module boundaries — no god files

- A module has **one reason to change**. A second reason means split it.
- Past 300 lines, justify the file. Past 400, split it. This is a prompt to
  look, not a threshold to game.
- Never create `utils.py`, `helpers.py`, `common.py`, or `misc.py`. Those names
  describe where code was put, not what it does, and they attract more.
- A filename that needs "and" to be accurate is two modules.
- Name the responsibility: `refunds.py`, not `payment_utils.py`.

## DRY, bounded by YAGNI

- **DRY applies to duplicated knowledge, not duplicated characters.** Two
  functions that look alike but change for different reasons are not
  duplication; merging them creates harmful coupling.
- **Extract on the third occurrence.** Two examples usually guess the
  abstraction wrong, and a wrong abstraction costs more than the duplication.
- **Always single-source** business rules, limits, and thresholds. The $2,000
  payment ceiling appears in exactly one place.
- Do not add: parameters no caller passes, config for a value with one setting,
  an abstract base class with one implementation, or plugin points with nothing
  to register.
- Before adding any abstraction, **name the second caller**. If you cannot, do
  not build it.

## Python specifics

- `snake_case` module names, per PEP 8.
- Secrets come from the environment via `pydantic-settings`. Never hardcode a
  key, and never read one from a file in the repository.
