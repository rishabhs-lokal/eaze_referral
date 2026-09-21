# Eaze Referral Program — Design Plan

## Implementation status

First iteration built: `eaze-referral-app/` (the landing screen, Expo/React Native Web + Android)
and `eaze-referral-service/` (Python/FastAPI + Postgres API — matches the stack the rest of the
Eaze fleet already runs). See each project's README for setup, local Docker Compose, and
Kubernetes deployment (multi-pod, with a one-shot Alembic migration Job).

`eaze-referral-backend/` (the original Node/Express prototype) is superseded and no longer wired
to the app — kept around only until someone's ready to delete it.

Two design changes made during the build, not in the original plan below:

1. Attribution is now **phone-only**, not code/deep-link-based. The referrer enters their friend's
   phone number directly in the webapp (`referral_intents` table) *before* the friend has even
   installed the app. At signup, the backend checks for a matching pending intent — if none, it's
   just a normal signup, no bonus for anyone. There is deliberately no code-entry fallback: it was
   removed because it was both weaker (deep-link capture is especially unreliable on iOS) and more
   exploitable (a code, unlike a specific phone number, could be shared/typed by anyone with no
   real tie to the referrer). `referrals.referral_intent_id` is `NOT NULL` — see
   `eaze-referral-service/app/models.py` (and its Alembic migration,
   `eaze-referral-service/alembic/versions/0001_initial_schema.py`) for the current schema, which
   supersedes the sketch in §4 below. `referral_codes` / `referral_code_id` still exist, but only
   for the share link's click-tracking analytics — never as a source of attribution.
2. Consequently, the referred user's bonus condition is "signed up with a phone number a referrer
   specifically named" rather than the original wording's "signed up via the link" — a stronger
   and more robust signal than link-clicking, and it means the real Eaze signup screen needs zero
   UI changes (no code field) to support this.

## Assumptions (flag if wrong — they change the schema)
- Eaze auth is phone number + OTP (recharge apps almost always are). Phone number is treated as the canonical identity anchor.
- There's already a `users` table and some kind of coin/wallet ledger, and a `recharges` table recording payment status. Schema below assumes these exist and only adds referral-specific tables + the columns needed to hook into them.
- "Recharge" = any successful/settled recharge transaction, and the referrer reward fires on the referred user's **first** successful recharge only (one-time, not per-recharge). Confirm this — it's the single biggest thing that changes the query logic if wrong.
- Coins are an in-app non-withdrawable currency (so clawback-on-refund is a ledger reversal, not a real refund).

---

## 1. Reward summary

| Event | Who gets coins | Amount | Trigger condition |
|---|---|---|---|
| Referred user's first login via referral link | Referred user | 50 | New phone number, valid referral code, first app open post-signup |
| Referred user's first successful recharge | Referrer | 50 | Referral row exists in `SIGNED_UP` state, recharge is the referred user's first successful one |

---

## 2. End-to-end flow

**Referrer side**
1. In-app banner → opens a webview/webapp (`refer.eaze.app`) passing the logged-in user's identity (signed token in URL, not raw user_id).
2. Webapp fetches (or lazily creates) that user's unique `referral_code`.
3. Webapp renders a **copyable message**, e.g.:
   > Join Eaze and get 50 free coins! Download: play.google.com/store/apps/details?id=com.eaze.app&referrer=EAZE-RS8K2Q (Android) or the App Store link for iOS. Enter code **EAZE-RS8K2Q** if it isn't auto-applied.
4. User copies and shares it manually (WhatsApp/SMS/etc.) — no server-side send required.

**Referred side**
1. Recipient taps the store link, installs the app.
2. On first launch, app resolves the referral code (see §3 — Android vs iOS differ) and passes it to the backend during signup.
3. User completes phone number entry + OTP verification.
4. Backend validates: phone number **never registered before** + referral code valid + referrer ≠ referred → creates `referrals` row (`SIGNED_UP`), credits referred user 50 coins immediately.
5. Later, when referred user's recharge completes successfully and it's their first ever recharge → backend credits referrer 50 coins, marks referral `REWARDED`.

---

## 3. Attribution mechanism (how the code survives install)

- **Android**: use the Play Install Referrer API. The store link carries `&referrer=<code>`; on first launch the app reads it via `com.android.installreferrer` and sends it to the backend during signup. Reliable, first-party, no SDK cost.
- **iOS**: Apple has no native equivalent — App Store doesn't pass params through install. Options:
  - Cheapest/simplest (recommended to start): the referral code is human-readable in the copied message itself, so signup just has a "Got a referral code?" field the user pastes/types in. No dependency, slightly more drop-off.
  - Better UX later: a deferred deep-linking SDK (Branch, AppsFlyer, Adjust) for clipboard/fingerprint matching — add only if manual entry conversion proves too lossy.
- Either path converges on the same backend contract: signup API receives an optional `referral_code` string.

---

## 4. Schema

```sql
-- One durable code per user, created lazily on first banner open.
CREATE TABLE referral_codes (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL UNIQUE REFERENCES users(id),
  code          VARCHAR(16) NOT NULL UNIQUE,   -- e.g. base62, "EAZE-RS8K2Q"
  is_active     BOOLEAN NOT NULL DEFAULT TRUE,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- The referral relationship + its reward lifecycle.
CREATE TABLE referrals (
  id                      BIGSERIAL PRIMARY KEY,
  referral_code_id        BIGINT NOT NULL REFERENCES referral_codes(id),
  referrer_user_id        BIGINT NOT NULL REFERENCES users(id),
  referred_user_id        BIGINT NOT NULL UNIQUE REFERENCES users(id), -- a user can be referred exactly once, ever
  referred_phone_e164     VARCHAR(16) NOT NULL,                        -- normalized +91XXXXXXXXXX, kept even if user later changes number
  status                  VARCHAR(20) NOT NULL DEFAULT 'SIGNED_UP',    -- SIGNED_UP | RECHARGED | REWARDED | REVERSED
  triggering_recharge_id  BIGINT REFERENCES recharges(id),
  signup_rewarded_at      TIMESTAMPTZ,
  recharge_rewarded_at    TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT no_self_referral CHECK (referrer_user_id <> referred_user_id)
);

CREATE INDEX idx_referrals_referrer ON referrals(referrer_user_id);
CREATE INDEX idx_referrals_status   ON referrals(status);

-- Optional: pre-signup funnel visibility (click → install → signup drop-off).
CREATE TABLE referral_clicks (
  id                BIGSERIAL PRIMARY KEY,
  referral_code_id  BIGINT NOT NULL REFERENCES referral_codes(id),
  device_id         VARCHAR(128),
  ip_address        INET,
  clicked_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Coin ledger entry for the reward itself, idempotent per (user, type, reference).
CREATE TABLE wallet_transactions (
  id             BIGSERIAL PRIMARY KEY,
  user_id        BIGINT NOT NULL REFERENCES users(id),
  amount         INT NOT NULL,
  type           VARCHAR(30) NOT NULL,       -- 'REFERRAL_SIGNUP_BONUS' | 'REFERRAL_RECHARGE_BONUS' | 'REFERRAL_REVERSAL'
  reference_type VARCHAR(30) NOT NULL,       -- 'referral'
  reference_id   BIGINT NOT NULL,            -- referrals.id
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, type, reference_id)       -- guarantees a reward can never be double-credited on retry
);
```

---

## 5. Core queries

**Fetch or lazily create a referral code**
```sql
INSERT INTO referral_codes (user_id, code)
VALUES ($1, $2)
ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE
RETURNING code;
```

**Validate referral code + phone is genuinely new, at signup** (run inside the signup transaction, before the user row is even considered "new"):
```sql
-- 1. phone must never have existed before (blocks reinstall farming)
SELECT 1 FROM users WHERE phone_e164 = $1;  -- must return 0 rows, INCLUDING soft-deleted accounts

-- 2. resolve the code
SELECT rc.id AS referral_code_id, rc.user_id AS referrer_user_id
FROM referral_codes rc
WHERE rc.code = $2 AND rc.is_active = TRUE;
```

**Create the referral + credit the referred user (single transaction)**
```sql
BEGIN;

INSERT INTO referrals (referral_code_id, referrer_user_id, referred_user_id, referred_phone_e164, status, signup_rewarded_at)
VALUES ($referral_code_id, $referrer_user_id, $new_user_id, $phone, 'SIGNED_UP', now())
RETURNING id;

INSERT INTO wallet_transactions (user_id, amount, type, reference_type, reference_id)
VALUES ($new_user_id, 50, 'REFERRAL_SIGNUP_BONUS', 'referral', $referral_id)
ON CONFLICT DO NOTHING;

UPDATE wallets SET balance = balance + 50 WHERE user_id = $new_user_id;

COMMIT;
```

**On recharge-success webhook — credit the referrer, only on the referred user's first-ever successful recharge**
```sql
-- Guard: is this actually the user's first successful recharge?
SELECT COUNT(*) FROM recharges WHERE user_id = $referred_user_id AND status = 'SUCCESS';
-- proceed only if this equals 1 (i.e. the row just committed is the only one)

BEGIN;

UPDATE referrals
SET status = 'REWARDED', recharge_rewarded_at = now(), triggering_recharge_id = $recharge_id, updated_at = now()
WHERE referred_user_id = $referred_user_id AND status = 'SIGNED_UP'
RETURNING id, referrer_user_id;

INSERT INTO wallet_transactions (user_id, amount, type, reference_type, reference_id)
VALUES ($referrer_user_id, 50, 'REFERRAL_RECHARGE_BONUS', 'referral', $referral_id)
ON CONFLICT DO NOTHING;   -- idempotent if the webhook retries

UPDATE wallets SET balance = balance + 50 WHERE user_id = $referrer_user_id;

COMMIT;
```

**Refund clawback** (if the triggering recharge is reversed within the settlement window):
```sql
INSERT INTO wallet_transactions (user_id, amount, type, reference_type, reference_id)
VALUES ($referrer_user_id, -50, 'REFERRAL_REVERSAL', 'referral', $referral_id)
ON CONFLICT (user_id, type, reference_id) DO NOTHING;
UPDATE wallets SET balance = balance - 50 WHERE user_id = $referrer_user_id;
UPDATE referrals SET status = 'REVERSED' WHERE id = $referral_id;
```

**Funnel / admin metrics**
```sql
SELECT status, COUNT(*) FROM referrals GROUP BY status;

SELECT u.phone_e164, COUNT(r.id) AS successful_referrals, COUNT(r.id) * 50 AS coins_earned
FROM users u JOIN referrals r ON r.referrer_user_id = u.id AND r.status = 'REWARDED'
GROUP BY u.id ORDER BY successful_referrals DESC LIMIT 50;
```

---

## 6. Fraud / abuse controls

- **Self-referral**: blocked at the DB level (`CHECK` constraint) and should also be blocked in-app (don't let a referrer's own device/number redeem their own code).
- **One reward per person, ever**: `referred_user_id UNIQUE` on `referrals` — a phone number can only ever trigger one signup bonus.
- **Reinstall farming**: the "phone never existed before" check (including soft-deleted rows) stops someone uninstalling/reinstalling to re-claim.
- **Device/SIM farming**: optionally capture `device_id` at signup and flag/block when the same device has been the "referred" device more than N times (config, e.g. 3/month).
- **Rate limits**: cap rewarded referrals per referrer per day/month (e.g. 20/month) — check with a `COUNT(*) WHERE referrer_user_id = ? AND status='REWARDED' AND recharge_rewarded_at > now() - interval '30 days'` before crediting.
- **Refund safety**: credit the referrer immediately on first recharge (good UX), but reverse via the `REVERSAL` ledger entry if that specific recharge is refunded/charged-back within your settlement window.
- **Idempotency everywhere**: every credit path uses `ON CONFLICT DO NOTHING` on `(user_id, type, reference_id)` so webhook retries can never double-pay.

---

## 7. Edge cases

- Referred person already has an Eaze account → signup blocked anyway by normal auth (phone exists), so no referral row is created — this is naturally handled by the "phone never existed" check.
- Invalid/typo'd/expired code at signup → ignore silently, signup proceeds without any bonus.
- Referrer account banned/deactivated before the referred user recharges → check `users.status = 'ACTIVE'` on the referrer before crediting; if inactive, leave referral in `SIGNED_UP` (don't pay) or write it to a manual-review queue.
- Referred user recharges multiple times → only the first successful one matters; the `UNIQUE (user_id, type, reference_id)` constraint plus the `status='SIGNED_UP' → 'REWARDED'` transition (a one-way door) prevents any further credit on later recharges.

---

## 8. Build order

1. `referral_codes` + `referrals` + `wallet_transactions` tables; API to fetch/create a referral code.
2. Webapp: banner deep link → auth handoff → copyable message with store links + code.
3. Android Play Install Referrer wiring; iOS manual code-entry field at signup.
4. Signup-bonus crediting transaction (§5).
5. Recharge-webhook → referrer-bonus crediting transaction (§5), with the first-recharge guard.
6. Fraud checks (§6) and admin funnel dashboard (§5 metrics queries).
7. QA pass specifically on: self-referral block, reinstall-farming block, double-credit-on-retry, refund clawback.

---

## 9. User journeys

### Referrer (e.g. Ravi — existing user)

1. **Discovers the offer**: opens Eaze for his own recharge, sees the "Refer a friend, earn 50 coins" banner on the home screen.
2. **Taps banner**: webview opens instantly — he's already logged in (identity passed via signed token), no second login. Shows his personal code and a ready-made message with **Copy** / **Share to WhatsApp** buttons.
3. **Shares**: taps Copy (or Share), picks a contact, sends. ~15 seconds, no waiting on anything but the initial code fetch.
4. **Then… nothing** — this is the gap worth fixing. Ravi has no idea whether his friend even opened the link, let alone signed up. Without feedback, the program feels like it "didn't work." Recommend adding:
   - A **"My Referrals"** screen listing each referral by status (Invited → Joined → Recharged → Rewarded).
   - A push notification when the friend signs up ("Priya joined using your link! 🎉") — no coins yet, just confirmation it worked.
   - A push notification + visible coin-balance bump the moment the referrer bonus is actually credited ("You just earned 50 coins — Priya recharged!"). This is the real payoff moment and should feel celebratory, not a silent ledger update.

### Referred (e.g. Priya — new user)

1. **Receives the message** on WhatsApp/SMS from Ravi — pitch + store link + human-readable code.
2. **Taps the link** → Play Store / App Store listing for Eaze.
3. **Installs and opens** the app for the first time.
4. **Referral capture** (invisible on Android, visible on iOS):
   - *Android*: the app silently reads the Play Install Referrer in the background — Priya sees nothing extra.
   - *iOS*: she sees a "Have a referral code?" field on the signup screen and has to type/paste the code herself (unless a paid deferred-deep-link SDK is added later). **This is the single highest-drop-off point in the whole journey** — if she skips it, there's no error, just a silent miss: no bonus for her, no credit for Ravi either.
5. **Signs up**: enters phone number, receives OTP, verifies.
6. **Instant reward**: on successful verification she immediately sees "Welcome! You've earned 50 coins for joining via Ravi's invite" — visible, immediate, reinforces trust from the first screen.
7. **Uses the app**, and — on her own timeline, maybe same day, maybe weeks later — does her first recharge. This is a separate, intent-driven action outside the referral system's control, which is exactly why the referrer needs a status/notification loop rather than expecting an instant payoff.
8. **Recharge completes**: nothing changes on her screen by default (the 50 coins go to Ravi, not her). Consider a small closing-the-loop toast — "Thanks for recharging — this just earned Ravi 50 coins!" — since it costs nothing and nudges her toward becoming a referrer herself.

### Drop-off risks along the journey

| Point | Risk | Mitigation |
|---|---|---|
| iOS manual code entry | Highest risk — silent miss, no error shown | Make the field prominent; consider a deferred-deep-link SDK once volume justifies the cost |
| Signup → first recharge | Can be days/weeks; referrer reward is naturally delayed | "My Referrals" status screen + notifications so the referrer doesn't assume it failed |
| Link tap → install | Normal store-page abandonment | Outside the referral system — store listing quality, not a coding fix |
