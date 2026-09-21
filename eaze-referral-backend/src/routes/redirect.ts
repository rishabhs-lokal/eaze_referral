import { Router } from 'express';
import { pool } from '../db';
import { asyncHandler } from '../lib/asyncHandler';

export const redirectRouter = Router();

const PLAY_STORE_URL = process.env.PLAY_STORE_URL ?? 'https://play.google.com/store/apps/details?id=com.eaze.app';
const APP_STORE_URL = process.env.APP_STORE_URL ?? 'https://apps.apple.com/app/idXXXXXXXXX';
const FALLBACK_URL = process.env.FALLBACK_URL ?? PLAY_STORE_URL;

// GET /r/:code — the link embedded in the copyable share message. Logs the click (this is the
// "tracking to verify users who used the link" piece) then forwards to the right store.
redirectRouter.get('/r/:code', asyncHandler(async (req, res) => {
  const codeRow = await pool.query<{ id: number }>(
    'SELECT id FROM referral_codes WHERE code = $1 AND is_active = TRUE',
    [req.params.code]
  );

  if (!codeRow.rows[0]) {
    res.redirect(302, FALLBACK_URL);
    return;
  }

  await pool.query(
    'INSERT INTO referral_clicks (referral_code_id, ip_address, user_agent) VALUES ($1, $2, $3)',
    [codeRow.rows[0].id, req.ip, req.get('user-agent') ?? null]
  );

  const ua = (req.get('user-agent') ?? '').toLowerCase();
  const target = ua.includes('android') ? PLAY_STORE_URL : ua.includes('iphone') || ua.includes('ipad') ? APP_STORE_URL : FALLBACK_URL;

  // Pass the code through as `referrer` too, so a future Play Install Referrer integration
  // (REFERRAL_PROGRAM_PLAN.md §3) can read it straight off the install without extra wiring.
  const separator = target.includes('?') ? '&' : '?';
  res.redirect(302, `${target}${separator}referrer=${encodeURIComponent(req.params.code)}`);
}));
