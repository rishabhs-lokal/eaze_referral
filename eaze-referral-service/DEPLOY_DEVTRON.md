# Deploying through Devtron

tier-1000 first. tier-500 is the same image and the same keys with two numbers and one
`DATABASE_URL` changed — see the bottom.

Verified at commit `087763b`. Tag the image with that SHA so "what is deployed" matches "what is
on main" without anyone having to remember a mapping.

Supersedes `DEPLOY_TIER_1000.md`, which assumes the `kubectl` path and predates migration `0006`.

## What has actually been verified

Run on 2026-10-12, against production Redash:

| | |
|---|---|
| Image builds | ✅ at `087763b` |
| Test suite, inside that image | ✅ 19 passed |
| Redash `20610` (phone → account) | ✅ answers, correct columns, matches E.164 / 91-prefixed / bare 10-digit |
| Redash `20649` (payments) | ✅ answers, all required and optional columns present |
| Schema | ✅ alembic `0006` applied to a live database, 12 tables |
| Queue expiry + prioritisation | ✅ against a live database: `checked` 3→1, signed-up row survived expiry, second pass idempotent |

**Not verified, and it is the branch that moves money:** no referral has ever been paid against
production. The probe number had `successful_payment_count = 0`, so the payout path has only
run against mocks. See "Before the first payout".

---

## 1. Build

Devtron's CI builds from the repo's `Dockerfile` at `eaze-referral-service/`. Nothing special is
needed — no build args, no secrets at build time. Tag the image with the commit SHA rather than
`latest`, so a rollback has something to point at.

One image serves both tiers. The coin amount is configuration, not code.

## 2. ConfigMap

Create a ConfigMap in Devtron for the tier-1000 environment with the keys below. They are the
same keys as `k8s/tier-1000/10-configmap.yaml`, which stays in the repo as the reference copy —
if you change a value in Devtron, change it there too, or the file becomes a lie.

| Key | tier-1000 value |
|---|---|
| `SIGNUP_BONUS_COINS` | `1000` ← **differs per tier** |
| `RECHARGE_BONUS_COINS` | `1000` ← **differs per tier** |
| `PUBLIC_BASE_URL` | the tier-1000 host |
| `REDASH_BASE_URL` | `https://analytics.getlokalapp.com` |
| `REDASH_VERIFY_PHONE_QUERY_ID` | `20610` |
| `REDASH_PAYMENTS_QUERY_ID` | `20649` |
| `PHONE_CHECK_TIMEOUT_SECONDS` | `8` |
| `RECONCILE_INTERVAL_SECONDS` | `0` for the first deploy, then `900` — see step 5 |
| `REFERRAL_EXPIRY_DAYS` | `90` — stops polling referrals that never produced a signup |
| `EAZE_FREE_COINS_API_URL` | `https://api.eazeapp.com/payments/free-coins/upload/` |
| `EAZE_FREE_COINS_AUTH_HEADER` | `x-n8n-auth-key` |
| `GOOGLE_SHEETS_WEBHOOK_URL` | the Apps Script Web App URL |
| `PLAY_STORE_URL` | `https://play.google.com/store/apps/details?id=live.emotionalcare.eazeapp` |
| `APP_STORE_URL` | `https://apps.apple.com/in/app/eaze-app-talk-feel-better/id6748073409` |
| `FALLBACK_URL` | `https://eaze.onelink.me/x8qY/eirps9xf` |
| `LOG_LEVEL` | `info` |
| `DATABASE_SSL_MODE` | `require` |
| `DB_TIMEZONE` | `Asia/Kolkata` |
| `DB_POOL_SIZE` | `5` |
| `DB_POOL_MAX_OVERFLOW` | `5` |

`DB_POOL_SIZE` and `DB_POOL_MAX_OVERFLOW` are **per pod**. Total connections against the database
is roughly `replicas * (5 + 5)`. Check that against the database's `max_connections` before
scaling replicas up.

## 3. Secret

A Devtron Secret in the same environment. Four keys:

| Key | Notes |
|---|---|
| `DATABASE_URL` | tier-1000's **own** database. Not shared with tier-500. |
| `REDASH_API_KEY` | A **user** key, not a query key. Query keys are scoped to one query and there is only one slot here, so two queries with different query keys would mean one of them 403s. |
| `EAZE_FREE_COINS_AUTH_KEY` | This one moves real coins. |
| `GOOGLE_SHEETS_WEBHOOK_SECRET` | Matches the Apps Script's `WEBHOOK_SECRET` property. Omit if the Sheet mirror is unused. |

Blank is handled: the config layer turns empty strings into `None`, because Devtron and Compose
both pass `""` rather than leaving a variable unset. A missing optional key will not crash the
pod. A missing **required** one will, loudly, which is the intent.

## 4. Migrations — the one thing Devtron changes

The `kubectl` path ran the migration Job to completion and only then rolled the Deployment. In
Devtron this has to be expressed as a **pre-deployment stage**, running:

```
alembic upgrade head
```

on the same image, with the same ConfigMap and Secret attached.

If migrations instead run as a post-deployment stage, or not at all, new pods start serving
traffic against a schema that has no `referral_verifications` table. Migrations `0004` through `0006`
must land **before** the new code takes traffic. This is the single highest-risk difference
between the two deployment paths.

## 5. Automating the payouts

The payout loop is the automation. `RECONCILE_INTERVAL_SECONDS` is its only dial:

- `0` — loop disabled. Payouts happen only when someone calls `POST /admin/reconcile`.
- `900` — a pass every 15 minutes, unattended. **This is the steady state.**

With N replicas, N copies of the loop run. A Postgres advisory lock means only one pod does the
work per tick; the rest skip cheaply. Nothing needs configuring for that.

**Day one, in order:**

1. Deploy with `RECONCILE_INTERVAL_SECONDS=0`. Nothing can pay anyone yet.
2. Confirm the pod is actually wired up:
   ```
   curl https://<host>/api/referral/admin/verification-summary
   ```
3. Trigger exactly one pass, watching the logs:
   ```
   curl -X POST https://<host>/api/referral/admin/reconcile
   ```
   `redash_not_configured` here means the Secret did not apply. **This is the failure mode to
   watch for** — the pod looks perfectly healthy and pays nobody.
4. If coins moved, check one real wallet in Eaze. See the 202 caveat below.
5. Change `RECONCILE_INTERVAL_SECONDS` to `900` and redeploy. Automated from here; no further
   manual step, ever.

Step 5 is easy to forget, and forgetting it means payouts silently never happen. Set a reminder.

## Before the first payout

**Nothing has moved a coin end to end against production.** Every payout test so far ran against
a mock.

**The database must not carry test referrals.** A test phone that resolves to a real Eaze account
with a real payment would credit a real wallet. Verify the production database is empty, or that
every row in it is a genuine referral, before step 3 above.

**`202` does not mean credited.** Eaze's coin endpoint returns `202 Bulk upload started` with an
`upload_id` — queued, not done. The service marks the side credited on that 202. If Eaze's async
job later fails, our ledger says paid and nothing retries. This is the weakest link in the chain
and the main reason step 4 exists.

**`registered_at` is load-bearing and currently fails open.** It is what disqualifies accounts
that existed before the referral. The guard reads `if registered_at and ...`, so a NULL or
unparseable value **skips the check and pays**. Either guarantee the column is never NULL in
query `20649`, or change the code to fail closed.

**Confirm `20649` counts only successful payments.** If it also counts failed, pending or
refunded attempts, we pay for referrals that never earned anything. This is a question about the
SQL, not about this service.

## Measured latency

Against production Redash, three runs each, `max_age=0` so nothing is cached:

| Hop | median |
|---|---|
| Redash phone lookup (`20610`) | 4.38s |
| Redash payments (`20649`) | 3.03s |
| Google Sheet, list rows | 2.80s |
| This service's own read endpoints | 6ms |

User-visible: pressing **Add your friend** blocks for ~4.5s on the phone lookup, hard-capped at
`PHONE_CHECK_TIMEOUT_SECONDS=8`. Note that 8 was chosen when the lookup measured ~3.1s; at 4.4s
the margin is roughly half what was originally assumed. Exceeding it is not an error — the number
saves anyway and the check finishes in the background — but the referrer stops seeing the
"already on Eaze" popup, which is their only chance to use a different number.

One reconcile pass costs ~10s regardless of whether it covers 1 referral or 200, because the
queries are batched (`redash_batch_size = 200`). At `900`, that is ~288 Redash executions/day.
Worth clearing with whoever owns Redash.

**The real end-to-end delay is not ours.** "Coins within 15 minutes" assumes `20649` reflects a
recharge immediately. If the underlying table is populated by an hourly ETL, users wait up to an
hour regardless of the loop interval. Find out before promising anyone anything.

## The frontend is a separate artifact

`EXPO_PUBLIC_REWARD_COINS` is inlined at build time, so each tier is its own web build:

```bash
cd eaze-referral-app
cp .env.tier-1000.example .env      # EXPO_PUBLIC_REWARD_COINS=1000
# set EXPO_PUBLIC_API_BASE_URL to the tier-1000 host
npx expo export --platform web      # → dist/
```

Verified: the tier-1000 build inlines `Number("1000")` and contains no 500-coin strings. A build
with the wrong value shows the wrong amount in the headline, the invite message and every popup.
There is no runtime fallback — a missing value fails the build rather than shipping a made-up
number.

## Apps Script

Already deployed, **version 3**, same URL and Deployment ID. `append`, `update` and `list` all
verified live, and the phone column is written as text so the leading `+` survives.

Both tiers point at the same Sheet and rows carry no tier label, so 1000- and 500-coin referrals
are indistinguishable there. Fine while only tier-1000 is live; fix before tier-500 joins it.

---

## Then tier-500

Same image, same commit, same keys. Only these differ:

| Key | tier-500 |
|---|---|
| `SIGNUP_BONUS_COINS` | `500` |
| `RECHARGE_BONUS_COINS` | `500` |
| `DATABASE_URL` | tier-500's own database |
| `PUBLIC_BASE_URL` | tier-500's host |

Afterwards, from a machine with cluster access:

```bash
./scripts/check_tier_parity.sh
```

It compares running images, schema versions and API surface. Tier drift has happened twice in
this project — a change landed, one tier was rebuilt, and the other kept serving older code while
looking perfectly healthy.
