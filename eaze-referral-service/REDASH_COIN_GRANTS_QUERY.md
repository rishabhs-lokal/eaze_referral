# Redash query requirement — free-coin grants per user

For the same-day coin guard: before this service credits referral coins, it needs to know
whether that Eaze user has **already been granted free coins today by some other tool** (Dostt,
level-up, a manual batch, anything). All of those write through the same shared free-coins
endpoint, and crediting twice in one day is what we are avoiding.

This document is the contract. It is written for whoever has warehouse access; no knowledge of
the referral service is assumed.

## What the query must answer

> For each of these Eaze user ids, when were they last granted free coins, and how many grants
> have they had recently?

Nothing else. It is read-only and must never be cached (the service already passes
`max_age=0`).

## Parameter

| name | type | shape |
|---|---|---|
| `user_ids` | text | comma-separated Eaze user ids, e.g. `11391052,10151402,9983211` |

Up to **200 ids per call** (`REDASH_BATCH_SIZE`). The service packs them itself and calls the
query repeatedly for larger sets, so the query only has to handle one batch.

Follow whatever `IN (...)` splitting pattern the existing queries use — the two already in
production (`REDASH_VERIFY_PHONE_QUERY_ID`, `REDASH_PAYMENTS_QUERY_ID`) take a comma-separated
text parameter the same way, so copy that mechanism rather than inventing a new one.

## Columns the result MUST contain

| column | type | meaning |
|---|---|---|
| `user_id` | text or int | the Eaze user id, so rows can be matched back to the request |
| `last_granted_at` | timestamp | the most recent free-coin grant for that user |

### Strongly wanted, if the data exists

| column | type | meaning |
|---|---|---|
| `source` | text | which tool/batch the grant came from — the batch name or label the upload carried |
| `grants_last_48h` | int | number of grants in the last 48 hours, for diagnostics |
| `coins_last_granted` | int | size of that most recent grant |

`source` matters more than it looks. This service labels its own uploads
`Eaze Referral Program` (`EAZE_FREE_COINS_BATCH_NAME`). Without a way to tell our own grants
apart from another tool's, a retry after a partial payout would see the coins **we** just
credited and defer a payment that already happened. If the warehouse does not record the batch
label, say so — the service can work around it, but less cleanly.

## Rows to return

- **One row per user id that has ever been granted free coins.**
- A user with no grants is simply **absent** from the results — do not return a row of nulls.
  The existing queries behave this way and the service already treats absence as "no record".
- If a user has multiple grants, return only the most recent (`MAX`), not one row per grant.

## Timestamps — read this part

The warehouse serialises timestamps **naive and in UTC** (`2026-10-12T11:49:25.635`, no
offset). That is established empirically, not assumed: a payment observed 20 minutes after it
happened came back as `11:55:27` while the wall clock read `12:15` UTC.

**Please return `last_granted_at` exactly that way — raw, in UTC, no conversion to IST.**

The service converts to the IST calendar day itself, deliberately, because that boundary is the
part most likely to be wrong and we want it under our own tests rather than inside SQL we cannot
test from the application side. A query that helpfully pre-converts to IST, or that returns
"granted today" as a boolean computed in SQL, would hide exactly the thing we need to verify.

If the column genuinely is not UTC in the warehouse, that is important — tell us rather than
converting, and we will set `REDASH_TIMESTAMP_TIMEZONE` accordingly.

## Which grants count

Free / promotional / bonus coin grants — the kind pushed through the shared free-coins upload
endpoint. **Not** coins a user earned through normal product activity, and not purchased coins,
unless the warehouse cannot distinguish them. If it cannot, say so, because it changes whether
this guard is safe to switch on at all.

## How to verify it before we trust it

Run it against a user id that you **know** was granted free coins today, and confirm a row
comes back with a plausible `last_granted_at`. Then run it against an id you know has never had
a grant and confirm **zero rows**, not a null row.

A query that returns nothing for everyone is indistinguishable from "nobody got coins today",
and the service would read that as "safe to credit" — failing open, silently. Confirming a known
positive is the only way to tell those apart. This is the same failure mode that
`scripts/check_redash.py` exists to catch for the other two queries.

## What we need back

1. The **query id** from Redash.
2. Confirmation of the actual column names, if they differ from the table above.
3. Whether `source` / batch label is available.
4. Whether free grants are distinguishable from earned or purchased coins.
