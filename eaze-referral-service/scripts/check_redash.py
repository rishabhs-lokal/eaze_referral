#!/usr/bin/env python
"""Diagnose the two Redash queries against ONE known phone number, before they're trusted to
decide who gets paid.

Run this the moment the queries exist and the REDASH_* env vars are set. It is read-only — it
never writes to the database, never credits anyone, and never touches the Google Sheet.

    docker compose -f docker-compose.tier-1000.yml run --rm \
        --entrypoint python app scripts/check_redash.py +919876543210

Pass a number that you KNOW is a registered Eaze user — the whole point is to confirm we can
find someone who is definitely there. A number that isn't registered can't distinguish "the
query works and they're genuinely absent" from "the query is broken and finds nobody", and
those two look identical to the pipeline while meaning opposite things.

The most likely real failure is phone formatting: if the warehouse stores 9876543210 and the
service sends +919876543210, every lookup comes back empty, which the pipeline reads as "not a
registered user" — silently letting pre-existing accounts through the eligibility check. So the
same number is tried in three shapes and the results compared.
"""

import asyncio
import sys

from app.config import get_settings
from app.services import redash

# What app/services/verification.py actually reads off each row. Anything missing here breaks
# the pipeline, so they're checked explicitly rather than discovered at runtime.
PHONE_QUERY_REQUIRED = ["user_id", "mobile_no"]
PHONE_QUERY_OPTIONAL = ["registered_at"]
PAYMENT_QUERY_REQUIRED = ["user_id", "successful_payment_count"]
PAYMENT_QUERY_OPTIONAL = ["first_payment_at", "first_payment_amount_paise"]

PASS = "  PASS"
FAIL = "  FAIL"
WARN = "  WARN"


def _columns_report(rows: list[dict], required: list[str], optional: list[str]) -> bool:
    if not rows:
        return False
    present = set(rows[0].keys())
    ok = True
    for col in required:
        if col in present:
            print(f"{PASS} required column '{col}' present")
        else:
            print(f"{FAIL} required column '{col}' MISSING — the pipeline cannot read this")
            ok = False
    for col in optional:
        if col in present:
            print(f"{PASS} optional column '{col}' present")
        else:
            print(f"{WARN} optional column '{col}' absent (reporting detail only, not fatal)")
    extra = present - set(required) - set(optional)
    if extra:
        print(f"  note: extra columns returned, harmless: {sorted(extra)}")
    return ok


async def main(raw_phone: str) -> int:
    settings = get_settings()

    print("=" * 72)
    print("REDASH CONNECTIVITY")
    print("=" * 72)
    if not redash.is_configured(settings):
        print(f"{FAIL} REDASH_BASE_URL / REDASH_API_KEY not set — nothing to test.")
        return 2
    print(f"{PASS} base url: {settings.redash_base_url}")
    if not settings.redash_verify_phone_query_id:
        print(f"{FAIL} REDASH_VERIFY_PHONE_QUERY_ID not set")
        return 2
    if not settings.redash_payments_query_id:
        print(f"{FAIL} REDASH_PAYMENTS_QUERY_ID not set")
        return 2
    print(f"{PASS} phone query id:   {settings.redash_verify_phone_query_id}")
    print(f"{PASS} payment query id: {settings.redash_payments_query_id}")

    digits = "".join(c for c in raw_phone if c.isdigit())[-10:]
    variants = {
        "E.164 (what the service sends)": f"+91{digits}",
        "country code, no plus": f"91{digits}",
        "bare 10-digit": digits,
    }

    print()
    print("=" * 72)
    print(f"QUERY 1 — phone lookup, same number in {len(variants)} formats")
    print("=" * 72)

    results: dict[str, list[dict]] = {}
    for label, value in variants.items():
        print(f"\n-- {label}: {value}")
        try:
            rows = await redash.run_query(
                settings, settings.redash_verify_phone_query_id, {"mobile_numbers": value}
            )
        except redash.RedashError as exc:
            print(f"{FAIL} query errored: {exc}")
            results[label] = []
            continue
        results[label] = rows
        print(f"  returned {len(rows)} row(s)")
        if rows:
            print(f"  first row: {rows[0]}")

    matched = [label for label, rows in results.items() if rows]
    print()
    if not matched:
        print(f"{FAIL} NO format matched. Either this number isn't actually registered, or the")
        print("       query's phone normalisation doesn't work. Do not go live on this —")
        print("       the pipeline would read every number as 'not registered' and let")
        print("       pre-existing accounts through the eligibility check.")
        return 1

    print(f"{PASS} matched on: {', '.join(matched)}")
    if "E.164 (what the service sends)" not in matched:
        print(f"{FAIL} the E.164 form is what the service actually sends, and it did NOT match.")
        print("       Fix the query to normalise (strip +91 / 91 and compare last 10 digits)")
        print("       before enabling this, or every lookup silently finds nobody.")
        return 1

    rows = results["E.164 (what the service sends)"]
    print()
    print("-- columns on the E.164 result:")
    if not _columns_report(rows, PHONE_QUERY_REQUIRED, PHONE_QUERY_OPTIONAL):
        return 1

    user_id = rows[0].get("user_id")
    if user_id is None:
        print(f"{FAIL} user_id is null — the pipeline treats a row without it as no match")
        return 1

    print()
    print("=" * 72)
    print(f"QUERY 2 — payments for user_id {user_id}")
    print("=" * 72)
    try:
        pay_rows = await redash.run_query(
            settings, settings.redash_payments_query_id, {"user_ids": str(user_id)}
        )
    except redash.RedashError as exc:
        print(f"{FAIL} query errored: {exc}")
        return 1

    print(f"  returned {len(pay_rows)} row(s)")
    if not pay_rows:
        print(f"{WARN} no payment row for this user. Fine if they genuinely never paid, but")
        print("       re-run with a user you KNOW has paid before trusting the payout gate —")
        print("       an always-empty payment query means nobody is ever credited.")
        return 0

    print(f"  first row: {pay_rows[0]}")
    print()
    if not _columns_report(pay_rows, PAYMENT_QUERY_REQUIRED, PAYMENT_QUERY_OPTIONAL):
        return 1

    count = pay_rows[0].get("successful_payment_count")
    try:
        count_int = int(count)
    except (TypeError, ValueError):
        print(f"{FAIL} successful_payment_count is {count!r} — must be a number")
        return 1
    if count_int > 0:
        print(f"{PASS} successful_payment_count = {count_int} — this referral would pay out")
    else:
        print(f"{WARN} successful_payment_count = 0 — this user would NOT trigger a payout")

    print()
    print("=" * 72)
    print("Both queries answered in the shape the pipeline expects.")
    print("Confirm the payment count only counts SUCCESSFUL payments — a query that")
    print("also counts failed or refunded ones would pay out referrals that never earned it.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(__doc__)
        print("error: pass exactly one phone number, e.g. +919876543210")
        raise SystemExit(2)
    raise SystemExit(asyncio.run(main(sys.argv[1])))
