---
title: Code conventions
status: active
updated: 2026-09-01
---

# Code conventions

Rules the source in this repository follows. Documentation-vault rules live
separately in [Conventions](conventions.md); back to
[Documentation home](index.md).

## Division of labour

Three layers carry project context, and each has one audience:

| Layer | Audience | Purpose |
| --- | --- | --- |
| Docstrings | Humans | Explain intent and reasoning while reading the file |
| Serena | Machine | Symbol-level semantic index and shared memories |
| Graphify | Machine | Relational knowledge graph across files and docs |

Because Serena and Graphify supply the machine-readable semantic and
relational context, docstrings are freed from that job. They are written
**purely for a human reading the code**, and are judged on whether they help
that person understand the file.

## Google-style docstrings

**Every Python function carries a Google-style docstring** — public, private,
helper, and test alike. Modules and classes carry them too.

```python
def calculate_refund_amount(charge: stripe.Charge, requested_cents: int | None) -> int:
    """Decide how many cents to refund against a charge.

    Stripe permits partial refunds, so a caller may request less than the
    original amount. A caller may also pass None to mean "refund whatever is
    still refundable", which is the common case for a natural-language
    command like "refund Maya's last payment".

    Args:
        charge: The Stripe charge being refunded. Must already be captured;
            an uncaptured charge should be cancelled rather than refunded.
        requested_cents: Amount to refund, or None to refund the full
            remaining balance.

    Returns:
        The number of cents to pass to Stripe, always within the amount still
        refundable on the charge.

    Raises:
        ValueError: If requested_cents exceeds the refundable balance. This is
            a caller error rather than a Stripe error, so it is caught before
            any network call is made.
    """
```

### What earns its place

Write the things the signature cannot say:

- **Why the function exists**, and which real scenario calls it.
- **Non-obvious constraints** — ordering requirements, assumed state,
  units (cents rather than dollars), and idempotency.
- **Why an error is raised**, not merely that it is.
- **Decisions taken and rejected**, where a reader would otherwise wonder.

### What to leave out

- Restating the signature in prose. `Args: charge: The charge.` is noise.
- Types in the docstring. Annotations carry types; repeating them means two
  places to update and one of them will drift.
- Change history. Git holds that.

## Type annotations

Full annotations on every parameter and return value. They are the contract;
the docstring is the explanation of the contract.

## Comments

Inline comments explain **why**, never **what**. Code that needs a comment to
say what it does should be rewritten or given a clearer name instead.

## Module boundaries — no god files

A module has **one reason to change**. When a second reason appears, that is
the signal to split, and it usually arrives before any line limit does.

As a rough tripwire rather than a rule: past **300 lines**, justify the file's
existence; past **400**, split it. The number is a prompt to look, not a
threshold to game — three cohesive 350-line modules are fine, and one
120-line file doing three unrelated jobs is not.

Signals a file is becoming a god file:

- Its name needs "and" to be accurate.
- It is called `utils`, `helpers`, `common`, or `misc`. These names describe
  where code was put, not what it does, and they attract more of the same.
- Its imports span unrelated concerns — HTTP handling next to SQL next to
  currency formatting.
- A change to one feature keeps forcing edits to it.

Each module should answer three questions on sight: what it does, how you use
it, and what it depends on. If a reader must open the file to learn what it is
for, the boundary is wrong.

This matters for more than tidiness. Focused modules are easier for a human to
review, and easier for a semantic index to resolve — see [Tooling](tooling.md).

## DRY, bounded by YAGNI

These two pull in opposite directions, and treating either as absolute
produces bad code. The rule that resolves them:

> **DRY applies to duplicated knowledge, not duplicated characters.**

One fact — how a refund amount is calculated, what the payment ceiling is,
how a Stripe object maps to our domain — lives in exactly one place. Two
functions that merely *look* alike but exist for different reasons are not
duplication, and merging them creates a coupling that breaks the first time
one of the reasons changes.

**Extract on the third occurrence.** Write it the first time. Notice it the
second. Extract on the third, when the shape is known. Abstracting from two
examples usually guesses wrong, and a wrong abstraction costs more than the
duplication it replaced.

**Always extract, regardless of count:** business rules, limits and
thresholds, anything a reviewer would expect to find in exactly one place.
The payment ceiling appears once. A second copy is a bug waiting for someone
to update only one of them.

What YAGNI forbids here:

- Parameters no caller passes.
- Configuration for a value that has one setting.
- An abstract base class with a single implementation.
- Plugin points, registries, or hooks with nothing to register.
- Handling cases the product does not have.

The test before adding an abstraction: **name the second caller.** If you
cannot, do not build it.

## Filenames and layout

Lowercase `snake_case` modules, as PEP 8 requires. The filename names the
responsibility — `refunds.py`, not `payment_utils.py`.
