# eaze-referral-service

Python/FastAPI backend for the Eaze referral program — supersedes `eaze-referral-backend/` (the
original Node/Express prototype), matching the stack the rest of your Eaze services already use
(FastAPI + uvicorn + Alembic). Pairs with `eaze-referral-app/` (the referral landing screen) and
implements the pipeline documented in `../REFERRAL_PROGRAM_PLAN.md`.

## Stack

- **Runtime**: Python 3.14 (current stable), FastAPI, uvicorn — one process per pod, no
  gunicorn/multi-worker wrapper (Kubernetes replicas provide the scaling).
- **Database client**: SQLAlchemy 2.0 async + asyncpg, built on nothing but a standard
  `postgresql://` connection URL — works against vanilla Postgres, RDS, Cloud SQL, Supabase, Neon,
  or CockroachDB in Postgres mode. See `app/db.py`.
- **Migrations**: Alembic, the standard tool for a SQLAlchemy project — `alembic/env.py` uses
  Alembic's official async template pattern. `app/models.py` is the single source of truth for
  the schema; every change after the initial migration should be authored with
  `alembic revision --autogenerate -m "..."`.

## Run it locally (Docker Compose)

There is no default/un-tiered stack — pick a reward tier (see [Reward tiers](#reward-tiers-1000-vs-500-coins)
below for the full picture):

```bash
docker compose -f docker-compose.tier-1000.yml up --build   # 1000 coins, API on :8091
docker compose -f docker-compose.tier-500.yml up --build    # 500 coins, API on :8092
```

Each runs three services, matching the `db` / `migrate` / `app` pattern: `db` (Postgres 16),
`migrate` (runs `alembic upgrade head` once and exits — `app` won't start until it completes
successfully), and `app` (the API). Both tiers can run at once; they're on distinct ports and
Postgres databases.

```bash
curl http://localhost:8091/healthz
curl http://localhost:8091/api/referral/code/demo-referrer
```

## Run it locally (without Docker)

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker compose -f docker-compose.tier-1000.yml up -d db   # just that tier's database
cp .env.tier-1000.example .env   # or .env.tier-500.example — there is no default .env.example
alembic upgrade head
uvicorn app.main:app --reload
pytest                            # unit tests (phone validation, etc.)
```

## Endpoints

Identical contract to the Node prototype (same camelCase JSON on the wire — `app/schemas.py`
handles the snake_case ↔ camelCase translation), so `eaze-referral-app` didn't need any changes
beyond pointing `EXPO_PUBLIC_API_BASE_URL` at this service.

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Liveness — does not touch the database |
| GET | `/readyz` | Readiness — checks the database is reachable |
| GET | `/api/referral/code/:userId` | Fetch or lazily create a referrer's durable code + share link. Also records a first-seen login (see below). |
| POST | `/api/referral/intents` | Save the phone numbers a referrer enters in the webapp. Also appends to `referral_logs` (see below). |
| POST | `/api/referral/copy-log` | Logs one "Copy message" click for a user — see below |
| POST | `/api/referral/signup-match` | Called at signup — phone-only attribution (see below), credits the new user `SIGNUP_BONUS_COINS` if matched |
| POST | `/api/referral/recharge-webhook` | Credits the referrer `RECHARGE_BONUS_COINS` on the referred user's first successful recharge |
| GET | `/api/referral/admin/funnel` | Status-count visibility into the pipeline |
| GET | `/api/referral/admin/verification-summary` | Confirmed funnel: referred → signed up → paid → referrer actually paid out |
| POST | `/api/referral/admin/reconcile` | Verify pending referrals against real payment data and credit any referrer now confirmed owed — see below |
| GET | `/r/:code` | The link in the copyable share message — logs a click, then redirects to the Play Store or App Store by user agent |

Attribution is **phone-only** — no code/deep-link fallback. A referral relationship exists if and
only if the referred phone number was pre-entered by a referrer via `/api/referral/intents`. See
`REFERRAL_PROGRAM_PLAN.md` for why this was deliberately simplified from an earlier code-based
design.

### Base64 user ids

The banner link carries the real Eaze user id **base64-encoded** in the `user_id` query param
(see `eaze-referral-app/src/state/useReferrerId.ts`). Decoding happens on the backend, not the
frontend — `app/services/identity.py`, called once at every entry point that accepts an
externally-supplied user id (`GET /code/:userId`, `POST /intents`, `POST /copy-log`) via the
`_decode_or_400` helper in `app/routers/referral.py`. Everything downstream — `users.external_ref`,
`login_logs`, `referral_logs`, `message_copy_logs` — stores and queries the **decoded original
id**, never the base64 form. An invalid/undecodable value returns `400`. Centralizing the decode
here (rather than in the frontend) means any future caller gets the same normalization for free.

### Timestamps are IST

Every timestamp column (`login_logs.first_seen_at`, `referral_logs.recorded_at`,
`message_copy_logs.copied_at`, etc.) reads as `Asia/Kolkata` wall-clock time. Postgres
`timestamptz` always stores an absolute UTC instant internally — what changes is the session
timezone every connection this app opens is set to, via asyncpg's `server_settings` in
`app/db.py` (`DB_TIMEZONE`, defaults to `Asia/Kolkata`). This is portable to managed Postgres
(no superuser `ALTER DATABASE` needed). The local Compose `db` container additionally runs with
`-c timezone=Asia/Kolkata` so a raw `psql` session sees IST too.

### Login tracking

Every `GET /api/referral/code/:userId` call — i.e. every time the webapp loads for a given user —
calls `record_first_login()`, which inserts into `login_logs (user_id, first_seen_at)`. This is
idempotent: `ON CONFLICT (user_id) DO NOTHING`, so a user's row is written once, on their first
visit ever, and never touched again on later visits. There's deliberately no per-visit log — just
first-seen timestamps, one row per user_id.

### Referral logs

`referral_logs (user_id, phone_e164, recorded_at)` — an **append-only audit trail** of every
validly-formatted phone number a referrer submitted via `POST /api/referral/intents`, logged on
every submission with no dedup. This is distinct from `referral_intents` (which enforces
one-referrer-per-phone globally and drives the actual reward pipeline) — `referral_logs` exists
purely so nothing a user submitted is ever lost from the record, even numbers that
`referral_intents` rejected as duplicates.

### Message copy logs

`message_copy_logs (user_id, copied_at)` — one row per tap of "Copy message"
(`POST /api/referral/copy-log`, called by the webapp on every click, fire-and-forget). Unlike
`login_logs`, this is **not** idempotent — every call inserts a new row. The "number of times a
user copied the message" is `COUNT(*) GROUP BY user_id`; individual click timestamps are kept
rather than collapsed into a running counter.

### Google Sheet mirror (optional)

Every phone number that's actually **accepted** as a new referral (not every raw submission —
that's what `referral_logs` above is for) can be mirrored, fire-and-forget, into a Google Sheet:
one row per accepted referral, `[timestamp, referrer's decoded user_id, phone number]`. This is
a human-readable supplementary view — `referral_intents` in Postgres remains the actual source
of truth for the reward pipeline; nothing about the reward logic depends on this working.

Off by default (`GOOGLE_SHEETS_WEBHOOK_URL` unset). To turn it on:

1. Create a Google Sheet, then Extensions → Apps Script, and paste in the contents of
   `google-apps-script/referral_sheet_webhook.gs` (full deployment steps are in that file's
   header comment — script property for the shared secret, `setupSheet` run-once, deploy as a
   Web App).
2. Set `GOOGLE_SHEETS_WEBHOOK_URL` (the Web App URL from step 1) and, if you configured one,
   `GOOGLE_SHEETS_WEBHOOK_SECRET` on the backend — see `.env.tier-*.example`.

A failure here (network, misconfigured URL, wrong secret) only ever logs a warning — it can
never fail or slow down the actual `/api/referral/intents` request, since it runs as a FastAPI
`BackgroundTask` after the response is already being sent.

### Payment verification via Redash (optional)

The referrer's coins are only earned when the person they referred **actually pays**. The
recharge webhook is the normal trigger for that, but a webhook is a claim, not evidence — it can
also simply never arrive. This feature adds independent confirmation against Eaze's real
warehouse data before any referrer is paid, and a reconciler that catches payments the webhook
missed.

Everything it learns lands in one table, `referral_verifications` — one row per referred phone
number, opened the moment the referral is accepted and only ever advanced afterwards:

| Column group | Answers |
|---|---|
| `signup_status`, `eaze_user_id`, `signed_up_at` | Did this number actually register on Eaze? |
| `payment_status`, `first_payment_at`, `first_payment_amount_paise`, `successful_payment_count` | Did they actually pay? |
| `signup_coins_status` / `_amount` / `_credited_at` | Did the *friend* get their coins? |
| `referrer_coins_status` / `_amount` / `_credited_at` | Did the *referrer* get theirs? |
| `source`, `last_checked_at`, `check_count`, `last_error` | Which path last advanced this row, and why it might be stuck |

Because a row exists from referral time, the table can answer what `referrals` structurally
cannot: which referred numbers never signed up, and which signed up but never paid.

The operationally important query is "who has earned a reward they haven't received":

```sql
SELECT phone_e164, referrer_external_id, first_payment_at, last_error
FROM referral_verifications
WHERE payment_status = 'PAID' AND referrer_coins_status = 'PENDING';
```

Off by default (`REDASH_BASE_URL` unset) — the pipeline then behaves exactly as it did before,
running on the recharge webhook alone. To turn it on you need **two Redash queries**:

**Query 1 — phone → Eaze user id.** Parameter: `mobile_numbers` (the service sends a
comma-separated list). Must return columns `user_id` and `mobile_no`; `registered_at` optional.

```sql
-- Proves the referred number is a real registered Eaze user.
SELECT u.id AS user_id, u.phone AS mobile_no, u.created_at AS registered_at
FROM users u
WHERE REGEXP_REPLACE(u.phone, r'^(\+?91)', '') IN (
  SELECT REGEXP_REPLACE(TRIM(num), r'^(\+?91)', '')
  FROM UNNEST(SPLIT('{{ mobile_numbers }}', ',')) AS num
)
```

**Query 2 — Eaze user id → payment facts.** Parameter: `user_ids` (comma-separated). Must return
`user_id` and `successful_payment_count`; `first_payment_at` and `first_payment_amount_paise`
optional but recommended (they're stored for reporting).

```sql
-- Proves they actually paid. Only successful payments count.
SELECT p.user_id,
       COUNT(*)              AS successful_payment_count,
       MIN(p.created_at)     AS first_payment_at,
       MIN(p.amount_paise)   AS first_payment_amount_paise
FROM payments p
WHERE p.status = 'SUCCESS'
  AND CAST(p.user_id AS STRING) IN (UNNEST(SPLIT('{{ user_ids }}', ',')))
GROUP BY p.user_id
```

Adjust table/column names to the real warehouse schema — the contract this service depends on is
only the **returned column names** above, not where they come from.

Then set `REDASH_BASE_URL`, `REDASH_API_KEY`, `REDASH_VERIFY_PHONE_QUERY_ID` and
`REDASH_PAYMENTS_QUERY_ID` (see `.env.tier-*.example`) and run a pass:

```bash
curl -X POST http://localhost:8091/api/referral/admin/reconcile
curl     http://localhost:8091/api/referral/admin/verification-summary
```

Schedule `/admin/reconcile` on a timer (a Kubernetes `CronJob` hitting the endpoint, every
15–30 min is plenty) so missed payments are picked up without anyone asking.

Three guarantees worth knowing, all verified against a mock Redash before this shipped:

- **Never double-credits.** Crediting goes through the same `wallet_transactions`
  `UNIQUE(user_id, type, reference_id)` guard as the webhook path, so the webhook and the
  reconciler can both fire for the same referral and the referrer is still paid exactly once.
- **A Redash outage never reads as "they didn't pay."** The error is parked on the affected rows
  in `last_error` and retried next pass; no status is changed. Withholding an earned reward
  because a dashboard was down would be the worst failure mode here.
- **It only ever advances a row.** A signup already confirmed by our own pipeline is never
  downgraded, and coins already credited are never revoked — a reversal is a deliberate
  decision, not something a background sweep should make.

## Reward tiers (1000 vs 500 coins)

Two coin amounts are deployed side by side — same codebase, same image, nothing forked. **There
is no default/un-tiered deployment**: `SIGNUP_BONUS_COINS` / `RECHARGE_BONUS_COINS` (see
`app/config.py`) have no default value, so a deployment that forgets to set them fails at startup
instead of silently running as some unintended reward amount.

**Locally (Docker Compose)** — two independent stacks can run at once, each with its own
Postgres, its own port, and a pinned Compose `name:` so they never collide with each other:

| Stack | Coins | API port | DB port |
|---|---|---|---|
| `docker-compose.tier-1000.yml` | 1000 | 8091 | 5533 |
| `docker-compose.tier-500.yml` | 500 | 8092 | 5534 |

```bash
docker compose -f docker-compose.tier-1000.yml up --build -d
docker compose -f docker-compose.tier-500.yml up --build -d
```

**On Kubernetes** — `k8s/tier-1000/` and `k8s/tier-500/` are the only manifest sets (there is no
top-level `k8s/`), each in its own namespace (`eaze-referral-1000` / `eaze-referral-500`) with its
own ConfigMap, Secret, Deployment, Service, and migration Job. `scripts/deploy.sh` requires a
`TIER` env var:

```bash
IMAGE=<registry>/eaze-referral-service:1.0.0 TIER=1000 ./scripts/deploy.sh
IMAGE=<registry>/eaze-referral-service:1.0.0 TIER=500  ./scripts/deploy.sh
```

**Tracking comes for free.** Because each tier is a fully separate deployment with its own
database, every existing table — `login_logs`, `referral_logs`, `message_copy_logs`,
`wallet_transactions` — is automatically scoped to that tier. There's no shared table to filter
by variant and no risk of one tier's numbers leaking into the other's; querying either database
in isolation *is* that tier's tracking. `GET /api/referral/admin/funnel` reports independently
per tier for the same reason.

On the frontend, `eaze-referral-app/.env`'s `EXPO_PUBLIC_REWARD_COINS` and
`EXPO_PUBLIC_API_BASE_URL` are what make a given build of the webapp show the right number and
talk to the right tier's backend — see that app's README.

## Generic database client

`app/db.py` accepts any standard `postgresql://` URL via the `DATABASE_URL` env var — nothing
provider-specific. Key knobs, all via env vars (see `app/config.py`):

- `DATABASE_SSL_MODE` — `disable` (default, for local Compose Postgres) or `require` (managed
  providers that mandate TLS).
- `DB_POOL_SIZE` / `DB_POOL_MAX_OVERFLOW` — per-pod connection pool sizing. With N Kubernetes
  replicas, total connections against the database is roughly `N * (pool_size + max_overflow)` —
  size this against the database's `max_connections` when choosing replica counts.
- `DB_STARTUP_RETRY_ATTEMPTS` / `DB_STARTUP_RETRY_DELAY_SECONDS` — the app retries its initial
  connectivity check with backoff at startup, covering the case where a pod starts before the
  database is reachable (fresh cluster, managed instance mid-failover, Compose `depends_on` race).

## Deploying to Kubernetes (multiple pods)

```bash
# 1. Build and push your image (same image serves both tiers)
docker build -t <your-registry>/eaze-referral-service:1.0.0 .
docker push <your-registry>/eaze-referral-service:1.0.0

# 2. Create the DB secret for the tier you're deploying (copy the template, fill in the real
#    value — or better, generate this from your actual secret manager instead of applying a
#    plain manifest)
cp k8s/tier-1000/11-secret.example.yaml k8s/tier-1000/11-secret.yaml
# edit k8s/tier-1000/11-secret.yaml with the real DATABASE_URL

# 3. Deploy — applies config, runs the migration Job to completion, THEN rolls out the Deployment
IMAGE=<your-registry>/eaze-referral-service:1.0.0 TIER=1000 ./scripts/deploy.sh
```

Repeat steps 2-3 with `k8s/tier-500/` and `TIER=500` for the other tier — the two namespaces are
fully independent. Each of `k8s/tier-1000/` and `k8s/tier-500/` contains:

| File | What |
|---|---|
| `00-namespace.yaml` | The tier's namespace (`eaze-referral-1000` / `eaze-referral-500`) |
| `10-configmap.yaml` | Non-secret config, including that tier's `SIGNUP_BONUS_COINS`/`RECHARGE_BONUS_COINS` |
| `11-secret.example.yaml` | Template for `DATABASE_URL` — copy to `11-secret.yaml` (gitignored) or generate from a real secret manager |
| `20-migration-job.yaml` | Runs `alembic upgrade head` once, exits |
| `30-deployment.yaml` | 3 replicas, rolling updates with zero downtime (`maxUnavailable: 0`), readiness/liveness probes, resource limits |
| `31-service.yaml` | ClusterIP in front of the pods |
| `32-hpa.yaml` | Optional autoscaling (3-10 replicas on 70% CPU) — requires metrics-server |

**Why a separate migration Job, not an initContainer on the Deployment**: with 3+ replicas, an
initContainer runs once *per pod* — that's 3 copies of `alembic upgrade head` racing each other.
The Job runs exactly once, and `scripts/deploy.sh` waits for it to complete before rolling out the
Deployment. Job specs are immutable, so the script deletes any previous run of the same Job name
first — this is the same ordering a `helm.sh/hook-delete-policy: before-hook-creation` pre-install
hook would give you, made explicit for plain manifests.

**Verified**: this `scripts/deploy.sh` flow (ordering: config → migration Job → Deployment) was run
end-to-end against a real local `kind` cluster during development — migration Job completed, all 3
Deployment pods became ready, and the full reward pipeline (code → intent → signup-match →
recharge-webhook) was exercised through the Service and confirmed correct, including traffic
actually being distributed across all 3 pods. That run predates the tier split and used the
single-namespace manifest set this repo no longer has; the per-tier manifests in `k8s/tier-1000/`
and `k8s/tier-500/` are the same files with only the namespace and coin ConfigMap values changed,
and the tier reward amounts themselves were verified via Docker Compose (see above).

## Superseded

`eaze-referral-backend/` (the Node/Express version) still exists but is no longer used —
`eaze-referral-app/.env` now points `EXPO_PUBLIC_API_BASE_URL` at this service instead. Remove the
Node backend whenever you're ready; nothing else depends on it.
