import { createHash } from 'crypto';
import { pool } from '../db';

// Prototype-only shim — see the comment on `users.external_ref` in migrations/001_init.sql.
// Deterministic so repeated calls for the same externalRef resolve to the same synthetic user.
function syntheticPhoneForExternalRef(externalRef: string): string {
  const hash = createHash('sha256').update(externalRef).digest('hex');
  const digits = BigInt('0x' + hash.slice(0, 12)) % 1_000_000_000n;
  return `+919${digits.toString().padStart(9, '0')}`;
}

export type UserRow = { id: number; phone_e164: string; external_ref: string | null; wallet_balance: number };

export async function getOrCreateUserByExternalRef(externalRef: string): Promise<UserRow> {
  const existing = await pool.query<UserRow>('SELECT * FROM users WHERE external_ref = $1', [externalRef]);
  if (existing.rows[0]) return existing.rows[0];

  const phone = syntheticPhoneForExternalRef(externalRef);
  const inserted = await pool.query<UserRow>(
    `INSERT INTO users (phone_e164, external_ref) VALUES ($1, $2)
     ON CONFLICT (external_ref) DO UPDATE SET external_ref = EXCLUDED.external_ref
     RETURNING *`,
    [phone, externalRef]
  );
  return inserted.rows[0];
}
