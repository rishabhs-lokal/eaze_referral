-- Eaze referral program — initial schema.
--
-- `users` and `recharges` below are minimal STAND-INS for the real Eaze backend's tables so this
-- migration is self-contained and runnable/testable on its own. When wiring this into the real
-- Eaze backend, drop these two and point the foreign keys at the real tables instead.

-- `external_ref` is a shim for this prototype only: it lets the webapp identify "the logged-in
-- referrer" via the opaque id the banner deep-link hands it, before the real signed-token auth
-- handoff (REFERRAL_PROGRAM_PLAN.md §2) exists. Drop it once real Eaze user ids are wired through.
CREATE TABLE IF NOT EXISTS users (
  id            BIGSERIAL PRIMARY KEY,
  phone_e164    VARCHAR(16) UNIQUE NOT NULL,
  external_ref  VARCHAR(64) UNIQUE,
  status        VARCHAR(20) NOT NULL DEFAULT 'ACTIVE',
  wallet_balance INT NOT NULL DEFAULT 0,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS recharges (
  id            BIGSERIAL PRIMARY KEY,
  user_id       BIGINT NOT NULL REFERENCES users(id),
  amount_paise  BIGINT NOT NULL,
  status        VARCHAR(20) NOT NULL, -- 'SUCCESS' | 'FAILED' | 'REFUNDED'
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One durable shareable code per referrer, created lazily the first time they open the banner.
CREATE TABLE IF NOT EXISTS referral_codes (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL UNIQUE REFERENCES users(id),
  code        VARCHAR(16) NOT NULL UNIQUE,
  is_active   BOOLEAN NOT NULL DEFAULT TRUE,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Phone numbers a referrer enters directly in the webapp, before the friend has even installed
-- the app. This is the table the referral landing screen's "Add your friend's number" form
-- writes to. It's the primary attribution path (a friend's number is known up front instead of
-- relying only on a deep-link/install-referrer code surviving the app store round trip).
CREATE TABLE IF NOT EXISTS referral_intents (
  id                BIGSERIAL PRIMARY KEY,
  referrer_user_id  BIGINT NOT NULL REFERENCES users(id),
  phone_e164        VARCHAR(16) NOT NULL UNIQUE, -- first referrer to submit a number owns it, ever
  status            VARCHAR(20) NOT NULL DEFAULT 'PENDING', -- PENDING | MATCHED | EXPIRED
  matched_user_id   BIGINT REFERENCES users(id),
  matched_at        TIMESTAMPTZ,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT referral_intents_phone_format CHECK (phone_e164 ~ '^\+91[6-9]\d{9}$')
);

CREATE INDEX IF NOT EXISTS idx_referral_intents_referrer ON referral_intents(referrer_user_id);
CREATE INDEX IF NOT EXISTS idx_referral_intents_status ON referral_intents(status);

-- Click tracking on the l.eaze.app/r/:code redirect — lets us see who actually used the link,
-- before they've installed or signed up.
CREATE TABLE IF NOT EXISTS referral_clicks (
  id                BIGSERIAL PRIMARY KEY,
  referral_code_id  BIGINT NOT NULL REFERENCES referral_codes(id),
  ip_address        INET,
  user_agent        TEXT,
  clicked_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_referral_clicks_code ON referral_clicks(referral_code_id);

-- The referral relationship + its reward lifecycle. Attribution is phone-only: a referral exists
-- if and only if the referred phone number was pre-entered by the referrer as a referral_intent.
-- referral_code_id is optional and purely for analytics (correlating a signup with the referrer's
-- share link, if it happened to be clicked) — it is never itself a source of attribution.
CREATE TABLE IF NOT EXISTS referrals (
  id                      BIGSERIAL PRIMARY KEY,
  referrer_user_id        BIGINT NOT NULL REFERENCES users(id),
  referred_user_id        BIGINT NOT NULL UNIQUE REFERENCES users(id),
  referred_phone_e164     VARCHAR(16) NOT NULL,
  referral_intent_id      BIGINT NOT NULL REFERENCES referral_intents(id),
  referral_code_id        BIGINT REFERENCES referral_codes(id),
  status                  VARCHAR(20) NOT NULL DEFAULT 'SIGNED_UP', -- SIGNED_UP | REWARDED | REVERSED
  triggering_recharge_id  BIGINT REFERENCES recharges(id),
  signup_rewarded_at      TIMESTAMPTZ,
  recharge_rewarded_at    TIMESTAMPTZ,
  created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT no_self_referral CHECK (referrer_user_id <> referred_user_id)
);

CREATE INDEX IF NOT EXISTS idx_referrals_referrer ON referrals(referrer_user_id);
CREATE INDEX IF NOT EXISTS idx_referrals_status ON referrals(status);

-- Coin ledger. UNIQUE(user_id, type, reference_id) makes every credit idempotent against
-- webhook/API retries — the same reward can never be paid twice.
CREATE TABLE IF NOT EXISTS wallet_transactions (
  id              BIGSERIAL PRIMARY KEY,
  user_id         BIGINT NOT NULL REFERENCES users(id),
  amount          INT NOT NULL,
  type            VARCHAR(30) NOT NULL, -- REFERRAL_SIGNUP_BONUS | REFERRAL_RECHARGE_BONUS | REFERRAL_REVERSAL
  reference_type  VARCHAR(30) NOT NULL, -- 'referral'
  reference_id    BIGINT NOT NULL,      -- referrals.id
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, type, reference_id)
);
