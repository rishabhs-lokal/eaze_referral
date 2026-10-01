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

That's the whole outstanding list — all three are Redash. Without them nothing is ever
confirmed, and because a confirmed payment is the only thing that releases coins, **nobody is
ever credited**.

---

## Coin dispersal — resolved

| Variable | Value | Secret? |
|---|---|---|
| `EAZE_FREE_COINS_API_URL` | `https://api.eazeapp.com/payments/free-coins/upload/` | no |
| `EAZE_FREE_COINS_AUTH_KEY` | set | **yes** |
| `EAZE_FREE_COINS_AUTH_HEADER` | `x-n8n-auth-key` | no |

| Thing | Answer |
|---|---|
| Payload shape | multipart form-data, field `file` = CSV `user_id,coins`, plus a `name` field |
| Auth header | `x-n8n-auth-key` — confirmed against the live endpoint; every other name returns `403 {"detail":"Invalid or missing N8N API key"}`. Legacy name on a shared Lokal service; unrelated to whether Eaze uses n8n. |
| Which user id | friend's from Redash, referrer's decoded from the banner link — resolved separately per side |

### Known caveat: the coin endpoint is asynchronous

It replies `202 {"message":"Bulk upload started","upload_id":N}` and credits afterwards. Acceptance
is **not** confirmation the wallet was credited — if a batch fails inside Eaze later, nothing tells
this service, and the referral will already be marked CREDITED. The `upload_id` is logged on every
credit so a disputed payout can be traced back to its batch.

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
| `EAZE_FREE_COINS_*` | The pipeline still decides correctly who is owed what, but no coins reach a real wallet — balances move only in this service's own tables. |
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
