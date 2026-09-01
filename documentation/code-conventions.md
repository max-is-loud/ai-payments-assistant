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

## Filenames and layout

Lowercase `snake_case` modules, as PEP 8 requires. A file that grows past a
single clear responsibility gets split — smaller focused modules are easier
for both a human reviewer and a semantic index to work with.
