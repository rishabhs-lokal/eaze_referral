import { randomBytes } from 'crypto';

const ALPHABET = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // no 0/O/1/I to avoid misreads when shared as text

export function generateReferralCode(prefix = 'EAZE'): string {
  const bytes = randomBytes(6);
  let suffix = '';
  for (const b of bytes) suffix += ALPHABET[b % ALPHABET.length];
  return `${prefix}-${suffix}`;
}
