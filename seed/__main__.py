"""`python -m seed [--force] [--clean] [--today-only]`.

Default: seed a fresh account, or, if seeded data exists, print the tokens and
exit without doubling revenue. `--force` cleans then seeds. `--clean` only
removes. `--today-only` adds a fresh day of activity for existing customers.
"""

import argparse
import secrets
import sys
from datetime import datetime

from app.domain.periods import local_timezone
from app.settings import ConfigError, load_settings
from app.stripe_.gateway import StripeGatewayError
from app.stripe_.owner_client import StripeOwnerGateway, translate_stripe_errors
from seed.dataset import build_dataset
from seed.inventory import clean, find_seeded
from seed.report import print_report
from seed.writer import create_customers, create_invoices, create_payments


def say(line: str) -> None:
    """Print immediately so progress is visible while Stripe calls run."""
    print(line, flush=True)


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
                say(f"Already seeded on {', '.join(sorted(inventory.seed_days))}. Nothing changed.")
                say(
                    "  --force re-seeds (charges from the old run remain), "
                    "--today-only adds a fresh day."
                )
                print_report(dataset, [(c.name, c.bind_token) for c in inventory.customers], say)
                return 0
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
