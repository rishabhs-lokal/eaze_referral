# Deploying tier-1000

The 1000-coin deployment, first. tier-500 is identical bar two numbers and a namespace — see
the bottom of this file.

Built and verified at commit `2e7fc51`.

---

## 1. Build and push the image

```bash
cd eaze-referral-service
docker build -t <registry>/eaze-referral-service:2e7fc51 .
docker push <registry>/eaze-referral-service:2e7fc51
```

One image serves both tiers. Tag it with the commit rather than `latest` so a rollback has
something to point at.

## 2. Create the Secret

`k8s/tier-1000/11-secret.example.yaml` is a template — copy it, fill it, apply it through
whatever secret workflow you use. **Do not commit the filled copy**; `k8s/tier-*/11-secret.yaml`
is gitignored for that reason.

| Key | Value |
|---|---|
| `DATABASE_URL` | tier-1000's own Postgres. **Not shared with tier-500.** |
| `REDASH_API_KEY` | the user API key |
| `EAZE_FREE_COINS_AUTH_KEY` | the coin-credit key |
| `GOOGLE_SHEETS_WEBHOOK_SECRET` | matches the Apps Script's `WEBHOOK_SECRET` property |

## 3. Everything else is already in the ConfigMap

`k8s/tier-1000/10-configmap.yaml` is committed and complete. For reference:

| Key | Value | Why |
|---|---|---|
| `SIGNUP_BONUS_COINS` | `1000` | **differs per tier** |
| `RECHARGE_BONUS_COINS` | `1000` | **differs per tier** |
| `REDASH_BASE_URL` | `https://analytics.getlokalapp.com` | |
| `REDASH_VERIFY_PHONE_QUERY_ID` | `20610` | phone → account, for the save-time check |
| `REDASH_PAYMENTS_QUERY_ID` | `20649` | phone → payment history |
| `PHONE_CHECK_TIMEOUT_SECONDS` | `8` | measured ~3.1s against real Redash |
| `RECONCILE_INTERVAL_SECONDS` | `900` | **the payout loop. `0` disables all payouts.** |
| `EAZE_FREE_COINS_API_URL` | `https://api.eazeapp.com/payments/free-coins/upload/` | |
| `EAZE_FREE_COINS_AUTH_HEADER` | `x-n8n-auth-key` | confirmed against the live endpoint |
| `GOOGLE_SHEETS_WEBHOOK_URL` | the Apps Script Web App URL | optional |
| `PUBLIC_BASE_URL` | tier-1000's host | builds share links |

## 4. Deploy

```bash
IMAGE=<registry>/eaze-referral-service:2e7fc51 TIER=1000 ./scripts/deploy.sh
```

Applies config, runs the migration Job **to completion**, then rolls the Deployment. Migrations
`0004` and `0005` must land before the new code serves traffic.

## 5. Check it came up doing something

```bash
curl https://<tier-1000-host>/api/referral/admin/verification-summary
curl -X POST https://<tier-1000-host>/api/referral/admin/reconcile
```

`reconcile` returning `redash_not_configured` means the Secret didn't apply. A healthy pod that
reports that is the failure mode to watch for — it looks fine and pays nobody.

---

## The frontend is a separate build

`EXPO_PUBLIC_REWARD_COINS` is inlined at build time, so the 1000-coin web build is its own
artifact:

```bash
cd eaze-referral-app
cp .env.tier-1000.example .env     # EXPO_PUBLIC_REWARD_COINS=1000
# point EXPO_PUBLIC_API_BASE_URL at the tier-1000 host, then build
```

A build with the wrong value shows the wrong coin amount in the headline, the invite message and
every popup. There is no runtime fallback — a missing value fails the build rather than shipping
a made-up number.

## Apps Script

Already deployed, **version 3**, same URL and Deployment ID. Verified live: `append`, `update`
and `list` all work, and the phone column is written as text so `+91` survives.

Both tiers point at the same Sheet. Rows do not carry a tier label, so 1000- and 500-coin
referrals are indistinguishable there — fine while only tier-1000 is live, worth fixing before
tier-500 joins it.

## Before the first payout

The payout loop credits real coins on its first pass. Two things to settle first:

- **The database must not carry test referrals.** A test phone that resolves to a real Eaze
  account who has paid would credit real coins to a real wallet.
- **Nothing has yet moved a coin end to end against production.** Every payout test ran against
  a mock. The first real one should be watched, ideally with `RECONCILE_INTERVAL_SECONDS=0` and
  a manual `POST /admin/reconcile` so it runs once, under supervision, rather than on a timer.

---

## Then tier-500

Same image, same commit, same Secret keys with tier-500's own `DATABASE_URL`:

```bash
IMAGE=<registry>/eaze-referral-service:2e7fc51 TIER=500 ./scripts/deploy.sh
```

Its ConfigMap already differs only in `SIGNUP_BONUS_COINS` / `RECHARGE_BONUS_COINS` (`500`) and
the namespace. Afterwards:

```bash
./scripts/check_tier_parity.sh
```

which compares the running images, schema versions and API surface. Tier drift has happened
twice in this project — a change landed, one tier was rebuilt, and the other kept serving older
code while looking perfectly healthy.
