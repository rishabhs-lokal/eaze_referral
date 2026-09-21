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

```bash
docker compose up --build
```

This runs three services, matching the `db` / `migrate` / `app` pattern:

1. `db` — Postgres 16, host port **5532** (not 5432, to avoid clashing with any other local
   Postgres already using the default port).
2. `migrate` — runs `alembic upgrade head` once and exits. `app` won't start until this completes
   successfully (`depends_on: condition: service_completed_successfully`).
3. `app` — the API, host port **8090** (8000 was already taken locally in this environment; change
   freely in `docker-compose.yml`).

```bash
curl http://localhost:8090/healthz
curl http://localhost:8090/api/referral/code/demo-referrer
```

## Run it locally (without Docker)

```bash
python3.14 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
docker compose up -d db          # just the database
cp .env.example .env             # DATABASE_URL already points at localhost:5532
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
| POST | `/api/referral/signup-match` | Called at signup — phone-only attribution (see below), credits the new user 50 coins if matched |
| POST | `/api/referral/recharge-webhook` | Credits the referrer 50 coins on the referred user's first successful recharge |
| GET | `/api/referral/admin/funnel` | Status-count visibility into the pipeline |
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
# 1. Build and push your image
docker build -t <your-registry>/eaze-referral-service:1.0.0 .
docker push <your-registry>/eaze-referral-service:1.0.0

# 2. Create the DB secret (copy the template, fill in the real value — or better, generate this
#    from your actual secret manager instead of applying a plain manifest)
cp k8s/11-secret.example.yaml k8s/11-secret.yaml
# edit k8s/11-secret.yaml with the real DATABASE_URL

# 3. Deploy — applies config, runs the migration Job to completion, THEN rolls out the Deployment
IMAGE=<your-registry>/eaze-referral-service:1.0.0 ./scripts/deploy.sh
```

`k8s/` contains:

| File | What |
|---|---|
| `00-namespace.yaml` | `eaze-referral` namespace |
| `10-configmap.yaml` | Non-secret config |
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

**Verified**: this exact `scripts/deploy.sh` flow was run end-to-end against a real local `kind`
cluster during development — migration Job completed, all 3 Deployment pods became ready, and the
full reward pipeline (code → intent → signup-match → recharge-webhook) was exercised through the
Service and confirmed correct, including traffic actually being distributed across all 3 pods.

## Superseded

`eaze-referral-backend/` (the Node/Express version) still exists but is no longer used —
`eaze-referral-app/.env` now points `EXPO_PUBLIC_API_BASE_URL` at this service instead. Remove the
Node backend whenever you're ready; nothing else depends on it.
