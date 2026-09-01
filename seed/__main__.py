"""`python -m seed [--force] [--clean] [--today-only]`.

Default: seed a fresh account, or, if seeded data exists, print the tokens and
exit without doubling revenue. `--force` cleans then seeds. `--clean` only
removes. `--today-only` adds a fresh day of activity for existing customers.
"""

import argparse
import secrets
import sys
from datetime import date, datetime
from typing import Literal

from app.domain.periods import local_timezone
from app.settings import ConfigError, load_settings
from app.stripe_.gateway import StripeGatewayError
from app.stripe_.owner_client import StripeOwnerGateway, translate_stripe_errors
from seed.dataset import Dataset, build_dataset
from seed.inventory import Inventory, clean, find_seeded
from seed.report import print_report
from seed.writer import create_customers, create_invoices, create_payments


def say(line: str) -> None:
    """Print immediately so progress is visible while Stripe calls run."""
    print(line, flush=True)


def classify_existing(
    inventory: Inventory, dataset: Dataset, today: date
) -> tuple[Literal["complete", "resume", "stuck"], str | None]:
    """Decide what a plain (non-`--force`) run should do about existing seeded data.

    Only meaningful when `inventory.customers` is non-empty; an empty
    inventory means "seed from scratch" and the caller never reaches here.

    A crash can leave every customer seeded but not every invoice — customers
    and payments are quick, invoices come last. Counting seed-tagged objects
    against the dataset, rather than trusting a locally-built report, is what
    catches that.

    Args:
        inventory: What `find_seeded` currently sees in the account.
        dataset: The dataset a fresh seed would write; gives the expected
            counts to compare against.
        today: The local calendar day, used to bound how "resume" is judged
            safe (see below).

    Returns:
        `("complete", None)`: every customer and invoice the dataset expects
            is already seed-tagged. Nothing to do.
        `("resume", run_id)`: short of invoices, but every seeded customer
            carries the same `run_id` and today's `seed_day`. Stripe caches
            idempotency keys for about 24h, so replaying that `run_id` is
            safe: objects already created come back as no-ops, missing ones
            get created.
        `("stuck", None)`: short of invoices, and either more than one run id
            is present or the seeding happened on an earlier day. Resuming
            under either run id is not knowably safe (an old run's
            idempotency keys may have already expired), so only `--force`
            (accepting that the orphaned payments stay) can recover.
    """
    complete = len(inventory.customers) >= len(
        dataset.customers
    ) and inventory.seeded_invoice_count >= len(dataset.invoices)
    if complete:
        return "complete", None
    run_ids = inventory.run_ids
    if len(run_ids) == 1 and inventory.seed_days == {today.isoformat()}:
        return "resume", next(iter(run_ids))
    return "stuck", None


def main(argv: list[str] | None = None) -> int:
    """Entry point; returns the process exit code."""
    parser = argparse.ArgumentParser(prog="seed", description=__doc__)
    parser.add_argument("--force", action="store_true", help="remove seeded data, then seed again")
    parser.add_argument("--clean", action="store_true", help="remove seeded data and exit")
    parser.add_argument(
        "--today-only",
        action="store_true",
        help="add today's activity for existing seeded customers",
    )
    args = parser.parse_args(argv)
    try:
        settings = load_settings()
        settings.require_stripe()
    except ConfigError as exc:
        say(f"error: {exc}")
        return 2
    client = StripeOwnerGateway(settings.stripe_secret_key).client
    today = datetime.now(local_timezone()).date()
    dataset = build_dataset(today)
    try:
        with translate_stripe_errors():
            inventory = find_seeded(client)
            if args.clean:
                clean(client, inventory, say)
                return 0
            if args.today_only:
                if not inventory.customers:
                    say("error: nothing seeded yet — run `make seed` first")
                    return 1
                run_id = f"today-{today.isoformat()}"
                by_name = {c.name: c.id for c in inventory.customers}
                ids = {c.key: by_name[c.name] for c in dataset.customers}
                say(f"Adding today's activity ({run_id})")
                ok, declined = create_payments(client, dataset.today_payments, ids, run_id, say)
                say(f"  {ok} payments, {declined} declines")
                return 0
            if inventory.customers and not args.force:
                state, resume_run_id = classify_existing(inventory, dataset, today)
                if state == "complete":
                    say(
                        f"Already seeded on {', '.join(sorted(inventory.seed_days))}. "
                        "Nothing changed."
                    )
                    say(
                        "  --force re-seeds (charges from the old run remain), "
                        "--today-only adds a fresh day."
                    )
                    print_report(
                        dataset, [(c.name, c.bind_token) for c in inventory.customers], say
                    )
                    return 0
                if state == "resume":
                    assert resume_run_id is not None  # guaranteed by classify_existing for "resume"
                    say(
                        f"Previous seed incomplete ({inventory.seeded_invoice_count} of "
                        f"{len(dataset.invoices)} invoices) — resuming run {resume_run_id}"
                    )
                    created = create_customers(client, dataset, resume_run_id, say)
                    ids = {key: c.id for key, c in created.items()}
                    ok, declined = create_payments(
                        client, dataset.payments, ids, resume_run_id, say
                    )
                    say(f"  {ok} payments created, {declined} declined as intended")
                    create_invoices(client, dataset, ids, resume_run_id, say)
                    print_report(dataset, [(c.name, c.bind_token) for c in created.values()], say)
                    return 0
                # state == "stuck": say so plainly and stop — never print success-style figures
                # for an account we cannot confirm is complete.
                say(
                    f"Previous seed incomplete ({inventory.seeded_invoice_count} of "
                    f"{len(dataset.invoices)} invoices) and cannot be safely resumed "
                    "(spans more than one run, or was seeded on an earlier day)."
                )
                say("  Existing Telegram binding tokens:")
                for customer in inventory.customers:
                    say(f"    {customer.name:<28} {customer.bind_token}")
                say(
                    "  Run `make seed ARGS=--force` to discard and reseed from scratch "
                    "(payments already created cannot be deleted and will remain)."
                )
                return 1
            if inventory.customers:
                say("Removing the previous seed…")
                clean(client, inventory, say)
            run_id = f"seed-{today.isoformat()}-{secrets.token_hex(3)}"
            api_version = StripeOwnerGateway(settings.stripe_secret_key).api_version
            say(f"Seeding {run_id} against API version {api_version}")
            created = create_customers(client, dataset, run_id, say)
            ids = {key: c.id for key, c in created.items()}
            ok, declined = create_payments(client, dataset.payments, ids, run_id, say)
            say(f"  {ok} payments created, {declined} declined as intended")
            create_invoices(client, dataset, ids, run_id, say)
            print_report(dataset, [(c.name, c.bind_token) for c in created.values()], say)
            return 0
    except StripeGatewayError as exc:
        say(f"error: {exc}")
        if exc.hint:
            say(f"  hint: {exc.hint}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
