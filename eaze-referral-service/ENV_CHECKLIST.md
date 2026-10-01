# Environment variables — pre-deployment checklist

Everything the referral service reads, what it's for, and what's still outstanding.

Secrets live in `eaze-referral-service/.env` locally (gitignored) and in the Kubernetes Secret in
production — **never in a tracked file**. The `.env.tier-*.example` files document the shape only.

---

## Still needed

| Variable | What it is | Example | Secret? |
|---|---|---|---|
| `REDASH_API_KEY` | Redash API key. A **user** key is safest — query keys are per-query, and there's only one slot here, so two queries with different query keys would mean one of them 403s. | `AbCd1234...` | **yes** |
| `REDASH_BASE_URL` | Redash origin only — no path, no trailing slash. If a query lives at `https://X/queries/20610/source`, this is `X`. | `https://redash.yourcompany.com` | no |
| `REDASH_PAYMENTS_QUERY_ID` | Numeric id of the **payments** query (user_id → successful payment count). The number in its URL. | `20611` | no |
| `EAZE_WALLET_API_URL` | Eaze's coin-credit endpoint — where we POST to actually give someone coins. | `https://api.eaze.in/wallet/credit/` | no |
| `EAZE_WALLET_AUTH_KEY` | Auth key for that endpoint. | `...` | **yes** |

Not env vars, but still needed before the payout can be built — tell these to the engineer, they
get written into the code, not configured:

| Thing | Why it can't be an env var |
|---|---|
| Payload shape (JSON vs CSV, single vs batched) | It's request-building code, not a value |
| Auth **header name** (e.g. `x-n8n-auth-key`) | Same |
| Which user id the wallet expects | Determines which id we send; wrong id space credits the wrong accounts and still returns success |

A working `curl` for the wallet API answers all three at once, plus the URL and key.

---

## Already set

| Variable | What it is | Secret? |
|---|---|---|
| `REDASH_VERIFY_PHONE_QUERY_ID` | Phone-lookup query id — **20610** | no |
| `GOOGLE_SHEETS_WEBHOOK_URL` | Apps Script Web App URL for the sheet mirror | no |
| `GOOGLE_SHEETS_WEBHOOK_SECRET` | Shared secret matching the script's `WEBHOOK_SECRET` property | **yes** |

---

## Per-tier, already configured in compose and k8s

| Variable | tier-1000 | tier-500 | Notes |
|---|---|---|---|
| `SIGNUP_BONUS_COINS` | `1000` | `500` | **No default on purpose** — a deployment that forgets these fails at startup rather than paying an unintended amount |
| `RECHARGE_BONUS_COINS` | `1000` | `500` | same |
| `PUBLIC_BASE_URL` | tier's own host | tier's own host | used to build share links |
| `DATABASE_URL` | tier's own DB | tier's own DB | **separate databases** — the tiers never share data |

For Kubernetes, `DATABASE_URL` goes in `k8s/tier-<n>/11-secret.yaml`, copied from
`11-secret.example.yaml`. Neither real secret file exists yet.

---

## What breaks if each is missing

| Missing | Effect |
|---|---|
| Any `REDASH_*` | Verification and payout both dormant. `/admin/reconcile` returns `redash_not_configured`; referred numbers stay `UNCHECKED`; **nobody is ever credited**, because confirmed payment is the only thing that releases coins. |
| `EAZE_WALLET_*` | The pipeline still decides correctly who is owed what, but no coins reach a real wallet — the balances move only in this service's own tables. |
| `GOOGLE_SHEETS_*` | Sheet mirror off. Rewards are unaffected; the reconciler falls back to the database queue. |
| `SIGNUP_BONUS_COINS` / `RECHARGE_BONUS_COINS` | App refuses to start. Deliberate. |

Blank values are treated as unset and are safe — that's what the optional-settings handling in
`app/config.py` exists for.

---

## Verifying before you trust it

Once the Redash values are in, run the read-only diagnostic against a number you **know** is a
registered Eaze user:

```bash
docker compose -f docker-compose.tier-1000.yml run --rm \
    --entrypoint python app scripts/check_redash.py +91XXXXXXXXXX
```

It checks both queries return the expected columns, and tries the number in three formats —
because if the warehouse stores bare digits while the service sends `+91...`, every lookup comes
back empty, which reads as "not registered" and lets pre-existing accounts through the
eligibility check.
