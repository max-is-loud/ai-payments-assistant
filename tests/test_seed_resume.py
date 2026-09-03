"""`make seed` after a crash: the real write path, driven through `seed.__main__`.

The fake client keeps what each attempt created and enforces Stripe's
idempotency rules, so these tests show what a reviewer's sandbox would hold:
every object exactly once, the binding tokens printed at the end the same
ones the customers were created with, and no idempotency key ever sent twice
with different parameters.
"""

from datetime import datetime
from typing import Any

import pytest

from app.domain.currency import USD, Currency
from app.domain.periods import local_timezone
from app.settings import Settings
from seed import __main__ as seed_main
from seed.dataset import build_dataset
from tests.fakes.stripe_client_fake import FakeStripeClient, Interrupted

TODAY = datetime.now(local_timezone()).date()
DATASET = build_dataset(TODAY)
# One customer is create + attach + update; one payment is one create; one
# invoice is create + item + finalize, plus pay for the historical paid ones.
CUSTOMER_WRITES = 3 * len(DATASET.customers)
PAYMENT_WRITES = len(DATASET.payments)
INVOICE_WRITES = sum(4 if i.paid else 3 for i in DATASET.invoices)
EXPECTED_STATUS = {i.key: "paid" if i.paid else "open" for i in DATASET.invoices}


def _every_boundary() -> list[Any]:
    """A crash before every customer and invoice write, and a sample of payment writes.

    Customer and invoice writes are multi-step objects, so each step is a
    distinct state to recover from; payments are one write each and all
    alike, so a few positions stand in for the rest.
    """
    points: list[Any] = []
    for k in range(1, CUSTOMER_WRITES + 1):
        points.append(pytest.param(k, id=f"customers-{k}"))
    for k in (1, 2, PAYMENT_WRITES // 2, PAYMENT_WRITES):
        points.append(pytest.param(CUSTOMER_WRITES + k, id=f"payments-{k}"))
    for k in range(1, INVOICE_WRITES + 1):
        points.append(pytest.param(CUSTOMER_WRITES + PAYMENT_WRITES + k, id=f"invoices-{k}"))
    return points


class _FakeOwnerGateway:
    """The three things `seed.__main__` asks of `StripeOwnerGateway`."""

    api_version = "2026-test"

    def __init__(self, client: FakeStripeClient) -> None:
        """Front the shared fake client."""
        self.client = client

    def default_currency(self) -> Currency:
        """A dollar account."""
        return USD


@pytest.fixture
def sandbox(monkeypatch: pytest.MonkeyPatch) -> FakeStripeClient:
    """An empty fake account wired into the CLI's settings and gateway."""
    client = FakeStripeClient()
    monkeypatch.setattr(
        seed_main, "load_settings",
        lambda: Settings(_env_file=None, stripe_secret_key="sk_test_fake"),
    )
    monkeypatch.setattr(seed_main, "StripeOwnerGateway", lambda _key: _FakeOwnerGateway(client))
    return client


def _run(monkeypatch: pytest.MonkeyPatch, argv: list[str] | None = None) -> tuple[int, list[str]]:
    """Run the CLI and capture its exit code and output lines."""
    lines: list[str] = []
    monkeypatch.setattr(seed_main, "say", lines.append)
    return seed_main.main(argv or []), lines


def _tokens(client: FakeStripeClient) -> dict[str, str]:
    """Seed key to binding token for every live seeded customer."""
    return {
        c["metadata"]["seed_key"]: c["metadata"]["telegram_bind_token"]
        for c in client.customers_store.values() if not c["deleted"]
    }


def _reported_tokens(lines: list[str]) -> dict[str, str]:
    """Name to token, as the report prints them after the tokens heading."""
    names = {c.name for c in DATASET.customers}
    found: dict[str, str] = {}
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and " ".join(parts[:-1]).strip() in names:
            found[" ".join(parts[:-1]).strip()] = parts[-1]
    return found


def _assert_seeded_exactly_once(client: FakeStripeClient, run_id: str) -> None:
    """Every dataset object exists exactly once under `run_id`.

    Objects of an earlier run may remain: Stripe cannot delete payment intents,
    and `--force` voids invoices rather than removing them. They are tagged
    with their own run and are not this run's.
    """
    live = [c for c in client.customers_store.values() if not c["deleted"]]
    assert sorted(c["metadata"]["seed_key"] for c in live) == sorted(
        c.key for c in DATASET.customers
    )
    assert {c["metadata"]["seed_run"] for c in live} == {run_id}
    payments = [p for p in client.payment_intents.values() if p["metadata"]["seed_run"] == run_id]
    assert sorted(p["metadata"]["seed_key"] for p in payments) == sorted(
        p.key for p in DATASET.payments
    )
    invoices = [i for i in client.invoices_store.values() if i["metadata"]["seed_run"] == run_id]
    assert sorted(i["metadata"]["seed_key"] for i in invoices) == sorted(
        i.key for i in DATASET.invoices
    )
    # Each invoice reached the state the dataset expects: paid history, open otherwise.
    assert {i["metadata"]["seed_key"]: i["status"] for i in invoices} == EXPECTED_STATUS
    invoice_ids = {i["id"] for i in invoices}
    assert len([ii for ii in client.invoice_items.values() if ii["invoice"] in invoice_ids]) == len(
        DATASET.invoices
    )
    # Every live customer has its card on file, whichever attempt attached it.
    assert {customer for _method, customer in client.attached} >= {c["id"] for c in live}


def _run_id(client: FakeStripeClient) -> str:
    """The run id the live customers carry."""
    return next(iter({
        c["metadata"]["seed_run"] for c in client.customers_store.values() if not c["deleted"]
    }))


def test_a_fresh_sandbox_is_seeded_once_and_a_rerun_changes_nothing(
    sandbox: FakeStripeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The supported starting point; a second plain run reprints the same tokens."""
    code, lines = _run(monkeypatch)
    assert code == 0
    _assert_seeded_exactly_once(sandbox, _run_id(sandbox))
    tokens = _tokens(sandbox)
    assert _reported_tokens(lines) == {c.name: tokens[c.key] for c in DATASET.customers}
    writes = sandbox.writes
    code, lines = _run(monkeypatch)
    assert code == 0 and any("Nothing changed" in line for line in lines)
    assert sandbox.writes == writes and _tokens(sandbox) == tokens
    assert _reported_tokens(lines) == {c.name: tokens[c.key] for c in DATASET.customers}


@pytest.mark.parametrize("crash_after", _every_boundary())
def test_an_interrupted_seed_resumes_with_the_same_objects_and_tokens(
    sandbox: FakeStripeClient, monkeypatch: pytest.MonkeyPatch, crash_after: int
) -> None:
    """After a crash before any write, the next plain run finishes it: no duplicates, no new tokens.

    Customers that already exist keep their id and their token, so the report
    at the end names the tokens the customers were created with; only the
    customers the crash prevented are created, with fresh ones. A crash that
    leaves an invoice in draft, or a historical invoice open, is a resume
    too: completeness is judged on each invoice's expected state, not on how
    many invoice objects exist.
    """
    sandbox.crash_after(crash_after)
    with pytest.raises(Interrupted):
        _run(monkeypatch)
    surviving = _tokens(sandbox)
    if not surviving:
        # The crash landed before the first customer: nothing to resume, a fresh seed.
        code, lines = _run(monkeypatch)
        assert code == 0, lines
        _assert_seeded_exactly_once(sandbox, _run_id(sandbox))
        return
    code, lines = _run(monkeypatch)
    assert code == 0, lines
    assert any("resuming" in line for line in lines), lines
    _assert_seeded_exactly_once(sandbox, _run_id(sandbox))
    tokens = _tokens(sandbox)
    assert {key: tokens[key] for key in surviving} == surviving
    assert _reported_tokens(lines) == {c.name: tokens[c.key] for c in DATASET.customers}


def test_repeated_interruptions_still_converge(
    sandbox: FakeStripeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A resume that itself crashes is resumed again; the account still ends up exact."""
    sandbox.crash_after(CUSTOMER_WRITES + 10)
    with pytest.raises(Interrupted):
        _run(monkeypatch)
    tokens_after_first = _tokens(sandbox)
    sandbox.crash_after(CUSTOMER_WRITES + PAYMENT_WRITES + 2)
    with pytest.raises(Interrupted):
        _run(monkeypatch)
    assert _tokens(sandbox) == tokens_after_first
    code, lines = _run(monkeypatch)
    assert code == 0, lines
    _assert_seeded_exactly_once(sandbox, _run_id(sandbox))
    assert _tokens(sandbox) == tokens_after_first
    assert _reported_tokens(lines) == {
        c.name: tokens_after_first[c.key] for c in DATASET.customers
    }


def test_resume_never_reuses_a_key_with_different_parameters(
    sandbox: FakeStripeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every replayed key carries byte-for-byte the parameters it was first sent with.

    The fake raises Stripe's own error for a key reused with other
    parameters, so a resume that minted new tokens for existing customers
    would fail here rather than silently sending Stripe something new.
    """
    sandbox.crash_after(CUSTOMER_WRITES + 3)
    with pytest.raises(Interrupted):
        _run(monkeypatch)
    live_before = len(_tokens(sandbox))
    code, lines = _run(monkeypatch)
    assert code == 0, lines
    assert not any("idempotent" in line.lower() for line in lines)
    # Existing customers were kept, so their create keys were never sent again; the
    # card attachments were replayed under their keys with the same parameters.
    assert not any(":cus:" in key for key in sandbox.replays)
    assert sum(1 for key in sandbox.replays if ":pm:" in key) == live_before


def test_completion_is_judged_on_the_active_run_not_on_older_invoices(
    sandbox: FakeStripeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Voided invoices from a run `--force` removed must not make a crashed run look complete.

    `--force` deletes customers and voids open invoices, but voided invoices
    stay in the account with their seed tags. A later run that crashes
    before its own invoices used to be counted complete against them.
    """
    code, _lines = _run(monkeypatch)
    assert code == 0
    sandbox.crash_after(CUSTOMER_WRITES + PAYMENT_WRITES + 1)  # after --force's clean-up
    with pytest.raises(Interrupted):
        _run(monkeypatch, ["--force"])
    old_voided = [i for i in sandbox.invoices_store.values() if i["status"] == "void"]
    assert len(old_voided) == len([i for i in DATASET.invoices if not i.paid])
    code, lines = _run(monkeypatch)
    assert code == 0, lines
    assert any("resuming" in line for line in lines), lines
    _assert_seeded_exactly_once(sandbox, _run_id(sandbox))


def test_a_crash_before_the_first_customer_starts_over_cleanly(
    sandbox: FakeStripeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing seeded means the next run is a fresh seed, not a resume."""
    sandbox.crash_after(1)
    with pytest.raises(Interrupted):
        _run(monkeypatch)
    code, lines = _run(monkeypatch)
    assert code == 0, lines
    assert not any("resuming" in line for line in lines)
    _assert_seeded_exactly_once(sandbox, _run_id(sandbox))


def test_stuck_state_is_reported_without_success_figures(
    sandbox: FakeStripeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A partial seed from another day cannot be resumed: exit 1, tokens listed, no figures."""
    sandbox.crash_after(CUSTOMER_WRITES + 3)
    with pytest.raises(Interrupted):
        _run(monkeypatch)
    for customer in sandbox.customers_store.values():
        customer["metadata"]["seed_day"] = "2000-01-01"
    code, lines = _run(monkeypatch)
    assert code == 1
    assert any("cannot be safely resumed" in line for line in lines)
    assert not any("Figures the daily summary" in line for line in lines)


def test_the_crash_points_above_fall_inside_the_stage_they_name() -> None:
    """The write counts the parametrised crash points rely on match the dataset."""
    assert CUSTOMER_WRITES == 30 and len(DATASET.invoices) == 5
    assert 40 < PAYMENT_WRITES and 5 < INVOICE_WRITES


def test_a_draft_left_by_a_crash_before_finalisation_is_not_counted_as_complete(
    sandbox: FakeStripeClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The exact reproduction: the last invoice created but not finalised, then a plain rerun.

    Counting invoice objects called this complete and exited 0 with the
    invoice still in draft. The rerun must resume and finish it.
    """
    before_last = sum(4 if i.paid else 3 for i in DATASET.invoices[:-1])
    sandbox.crash_after(CUSTOMER_WRITES + PAYMENT_WRITES + before_last + 3)  # before finalize
    with pytest.raises(Interrupted):
        _run(monkeypatch)
    drafts = [i for i in sandbox.invoices_store.values() if i["status"] == "draft"]
    assert [i["metadata"]["seed_key"] for i in drafts] == [DATASET.invoices[-1].key]
    code, lines = _run(monkeypatch)
    assert code == 0, lines
    assert any("resuming" in line for line in lines), lines
    assert not any("Nothing changed" in line for line in lines)
    _assert_seeded_exactly_once(sandbox, _run_id(sandbox))
