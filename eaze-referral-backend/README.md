# eaze-referral-backend

Minimal Express + Postgres API for the Eaze referral program. Pairs with `eaze-referral-app`
(the referral landing screen) and implements the pipeline documented in
`../REFERRAL_PROGRAM_PLAN.md`.

## Setup

```bash
npm install
cp .env.example .env   # point DATABASE_URL at your Postgres
npm run migrate        # runs migrations/001_init.sql
npm run dev            # starts the API on :4000 (from PORT in .env)
```

`migrations/001_init.sql` creates minimal stand-in `users` and `recharges` tables so the schema
is self-contained and testable on its own. When wiring this into the real Eaze backend, drop
those two tables and point the foreign keys in `referral_intents`, `referrals` and
`wallet_transactions` at the real ones instead.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/referral/code/:userId` | Fetch or lazily create a referrer's durable code + share link |
| POST | `/api/referral/intents` | Save the phone numbers a referrer enters in the webapp |
| POST | `/api/referral/signup-match` | Called at signup (after OTP) — matches a new phone against a pending intent/code, credits the new user 50 coins |
| POST | `/api/referral/recharge-webhook` | Called by the payment gateway webhook — credits the referrer 50 coins on the referred user's first successful recharge |
| GET | `/api/referral/admin/funnel` | Quick status-count visibility into the pipeline |
| GET | `/r/:code` | The link embedded in the copyable share message — logs a click, then redirects to the Play Store or App Store based on user agent |

`:userId` in `/api/referral/code/:userId` and the `referrerUserId` in `/api/referral/intents` are
currently an opaque **external ref** (see the comment on `users.external_ref` in the migration) —
a stand-in for the real Eaze user id until the banner→webapp auth handoff described in
`REFERRAL_PROGRAM_PLAN.md` §2 exists. Swap it for the real signed-token flow before this ships.

## Manually exercising the reward pipeline

```bash
# 1. Referrer fetches their code
curl http://localhost:4000/api/referral/code/demo-referrer

# 2. Referrer submits a friend's number
curl -X POST http://localhost:4000/api/referral/intents \
  -H "Content-Type: application/json" \
  -d '{"referrerUserId":"demo-referrer","phoneNumbersE164":["+919876543210"]}'

# 3. Simulate that friend signing up (this is what the real Eaze signup flow should call)
curl -X POST http://localhost:4000/api/referral/signup-match \
  -H "Content-Type: application/json" \
  -d '{"phoneE164":"+919876543210"}'
# -> { "userId": ..., "referred": true, "coinsCredited": 50 }

# 4. Simulate that friend's first recharge (this is what the payment gateway webhook should call)
curl -X POST http://localhost:4000/api/referral/recharge-webhook \
  -H "Content-Type: application/json" \
  -d '{"userId": <userId from step 3>, "amountPaise": 10000, "status": "SUCCESS"}'
# -> { "credited": true, "referrerUserId": ..., "rechargeId": ... }

curl http://localhost:4000/api/referral/admin/funnel
```

This full loop (steps 1-4) was run against a real Postgres instance during development and
confirmed: correct coin amounts, correct idempotency (a repeated recharge-webhook call does not
double-pay), and correct first-recharge gating.

## Environment variables

See `.env.example`. `PLAY_STORE_URL` / `APP_STORE_URL` / `FALLBACK_URL` control where `/r/:code`
redirects to; `PUBLIC_BASE_URL` is what gets embedded in the share link returned by
`/api/referral/code/:userId`.
