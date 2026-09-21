import { Router } from 'express';
import { pool } from '../db';
import { asyncHandler } from '../lib/asyncHandler';
import { isValidIndianE164 } from '../lib/phone';
import { generateReferralCode } from '../lib/referralCode';
import { getOrCreateUserByExternalRef } from '../lib/users';

export const referralRouter = Router();

const PUBLIC_BASE_URL = process.env.PUBLIC_BASE_URL ?? 'http://localhost:4000';

// GET /api/referral/code/:userId — fetch or lazily create the referrer's durable code.
referralRouter.get('/code/:userId', asyncHandler(async (req, res) => {
  const user = await getOrCreateUserByExternalRef(req.params.userId);

  const existing = await pool.query<{ code: string }>('SELECT code FROM referral_codes WHERE user_id = $1', [
    user.id,
  ]);
  let code = existing.rows[0]?.code;

  if (!code) {
    // Retry on the rare code collision (UNIQUE constraint) rather than trusting one draw.
    for (let attempt = 0; attempt < 5 && !code; attempt++) {
      const candidate = generateReferralCode();
      try {
        const inserted = await pool.query<{ code: string }>(
          `INSERT INTO referral_codes (user_id, code) VALUES ($1, $2)
           ON CONFLICT (user_id) DO UPDATE SET is_active = TRUE
           RETURNING code`,
          [user.id, candidate]
        );
        code = inserted.rows[0].code;
      } catch (err: any) {
        if (err.code !== '23505') throw err; // unique_violation on code — retry with a new one
      }
    }
  }

  if (!code) {
    res.status(500).json({ error: 'Could not allocate a referral code' });
    return;
  }

  res.json({ code, shareUrl: `${PUBLIC_BASE_URL}/r/${code}` });
}));

// POST /api/referral/intents — the webapp's "add your friend's number" form.
referralRouter.post('/intents', asyncHandler(async (req, res) => {
  const { referrerUserId, phoneNumbersE164 } = req.body ?? {};

  if (typeof referrerUserId !== 'string' || !Array.isArray(phoneNumbersE164) || phoneNumbersE164.length === 0) {
    res.status(400).json({ error: 'referrerUserId and a non-empty phoneNumbersE164 array are required' });
    return;
  }
  if (phoneNumbersE164.length > 5) {
    res.status(400).json({ error: 'At most 5 phone numbers per submission' });
    return;
  }

  const referrer = await getOrCreateUserByExternalRef(referrerUserId);

  let saved = 0;
  const skipped: { phone: string; reason: string }[] = [];

  for (const phone of phoneNumbersE164) {
    if (typeof phone !== 'string' || !isValidIndianE164(phone)) {
      skipped.push({ phone: String(phone), reason: 'invalid_format' });
      continue;
    }
    if (phone === referrer.phone_e164) {
      skipped.push({ phone, reason: 'self_referral' });
      continue;
    }

    const result = await pool.query(
      `INSERT INTO referral_intents (referrer_user_id, phone_e164)
       VALUES ($1, $2)
       ON CONFLICT (phone_e164) DO NOTHING
       RETURNING id`,
      [referrer.id, phone]
    );
    if (result.rowCount && result.rowCount > 0) {
      saved += 1;
    } else {
      skipped.push({ phone, reason: 'already_referred' });
    }
  }

  res.json({ saved, skipped });
}));

// POST /api/referral/signup-match — stands in for the hook the real Eaze signup flow would call
// right after OTP verification succeeds for a brand-new phone number.
//
// Attribution is phone-only: a referral exists if and only if this exact number was pre-entered
// by a referrer via /api/referral/intents. There is no code/deep-link fallback — if the number
// wasn't named up front, this is just a normal signup with no bonus for anyone.
referralRouter.post('/signup-match', asyncHandler(async (req, res) => {
  const { phoneE164 } = req.body ?? {};

  if (typeof phoneE164 !== 'string' || !isValidIndianE164(phoneE164)) {
    res.status(400).json({ error: 'A valid phoneE164 is required' });
    return;
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    const already = await client.query('SELECT id FROM users WHERE phone_e164 = $1', [phoneE164]);
    if (already.rowCount && already.rowCount > 0) {
      await client.query('ROLLBACK');
      res.status(409).json({ error: 'Phone number already registered' });
      return;
    }

    const newUser = await client.query<{ id: number }>(
      'INSERT INTO users (phone_e164) VALUES ($1) RETURNING id',
      [phoneE164]
    );
    const newUserId = newUser.rows[0].id;

    const intent = await client.query<{ id: number; referrer_user_id: number }>(
      `SELECT id, referrer_user_id FROM referral_intents WHERE phone_e164 = $1 AND status = 'PENDING'`,
      [phoneE164]
    );

    const referrerUserId: number | null = intent.rows[0]?.referrer_user_id ?? null;

    if (!referrerUserId || referrerUserId === newUserId) {
      await client.query('COMMIT');
      res.json({ userId: newUserId, referred: false });
      return;
    }

    const referral = await client.query<{ id: number }>(
      `INSERT INTO referrals (referrer_user_id, referred_user_id, referred_phone_e164, referral_intent_id, signup_rewarded_at)
       VALUES ($1, $2, $3, $4, now())
       ON CONFLICT (referred_user_id) DO NOTHING
       RETURNING id`,
      [referrerUserId, newUserId, phoneE164, intent.rows[0].id]
    );
    const referralId = referral.rows[0]?.id;

    if (referralId) {
      await client.query(
        `UPDATE referral_intents SET status = 'MATCHED', matched_user_id = $1, matched_at = now() WHERE id = $2`,
        [newUserId, intent.rows[0].id]
      );
      await client.query(
        `INSERT INTO wallet_transactions (user_id, amount, type, reference_type, reference_id)
         VALUES ($1, 50, 'REFERRAL_SIGNUP_BONUS', 'referral', $2)
         ON CONFLICT DO NOTHING`,
        [newUserId, referralId]
      );
      await client.query('UPDATE users SET wallet_balance = wallet_balance + 50 WHERE id = $1', [newUserId]);
    }

    await client.query('COMMIT');
    res.json({ userId: newUserId, referred: Boolean(referralId), coinsCredited: referralId ? 50 : 0 });
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}));

// POST /api/referral/recharge-webhook — stands in for the payment gateway webhook handler.
// Credits the referrer only on the referred user's first-ever successful recharge, idempotently.
referralRouter.post('/recharge-webhook', asyncHandler(async (req, res) => {
  const { userId, amountPaise, status } = req.body ?? {};

  if (typeof userId !== 'number' || typeof amountPaise !== 'number' || typeof status !== 'string') {
    res.status(400).json({ error: 'userId (number), amountPaise (number) and status (string) are required' });
    return;
  }

  const client = await pool.connect();
  try {
    await client.query('BEGIN');

    const recharge = await client.query<{ id: number }>(
      'INSERT INTO recharges (user_id, amount_paise, status) VALUES ($1, $2, $3) RETURNING id',
      [userId, amountPaise, status]
    );
    const rechargeId = recharge.rows[0].id;

    if (status !== 'SUCCESS') {
      await client.query('COMMIT');
      res.json({ credited: false, reason: 'recharge_not_successful', rechargeId });
      return;
    }

    const successCount = await client.query<{ count: string }>(
      `SELECT COUNT(*) FROM recharges WHERE user_id = $1 AND status = 'SUCCESS'`,
      [userId]
    );
    if (Number(successCount.rows[0].count) !== 1) {
      await client.query('COMMIT');
      res.json({ credited: false, reason: 'not_first_recharge', rechargeId });
      return;
    }

    const updated = await client.query<{ id: number; referrer_user_id: number }>(
      `UPDATE referrals
       SET status = 'REWARDED', recharge_rewarded_at = now(), triggering_recharge_id = $1, updated_at = now()
       WHERE referred_user_id = $2 AND status = 'SIGNED_UP'
       RETURNING id, referrer_user_id`,
      [rechargeId, userId]
    );

    if (!updated.rows[0]) {
      await client.query('COMMIT');
      res.json({ credited: false, reason: 'no_pending_referral', rechargeId });
      return;
    }

    const { id: referralId, referrer_user_id: referrerUserId } = updated.rows[0];

    await client.query(
      `INSERT INTO wallet_transactions (user_id, amount, type, reference_type, reference_id)
       VALUES ($1, 50, 'REFERRAL_RECHARGE_BONUS', 'referral', $2)
       ON CONFLICT DO NOTHING`,
      [referrerUserId, referralId]
    );
    await client.query('UPDATE users SET wallet_balance = wallet_balance + 50 WHERE id = $1', [referrerUserId]);

    await client.query('COMMIT');
    res.json({ credited: true, referrerUserId, rechargeId });
  } catch (err) {
    await client.query('ROLLBACK');
    throw err;
  } finally {
    client.release();
  }
}));

// GET /api/referral/admin/funnel — quick visibility into the pipeline.
referralRouter.get('/admin/funnel', asyncHandler(async (_req, res) => {
  const byStatus = await pool.query('SELECT status, COUNT(*) FROM referrals GROUP BY status');
  const intents = await pool.query('SELECT status, COUNT(*) FROM referral_intents GROUP BY status');
  const clicks = await pool.query('SELECT COUNT(*) FROM referral_clicks');
  res.json({
    referrals: byStatus.rows,
    intents: intents.rows,
    totalClicks: Number(clicks.rows[0].count),
  });
}));
