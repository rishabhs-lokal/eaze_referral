// Indian mobile numbers: 10 digits, first digit 6-9. Stored/sent as E.164: +91XXXXXXXXXX.
const INDIAN_MOBILE_LOCAL = /^[6-9]\d{9}$/;

export function isValidIndianMobileLocal(local: string): boolean {
  return INDIAN_MOBILE_LOCAL.test(local);
}

// Mirrors app/services/phone.py's is_likely_fake — keep both in sync. Same-account instant
// feedback for the two junk patterns real fraud never bothers with: every digit the same
// (9999999999, this field's own placeholder text being the likeliest accidental submission)
// or a run of simple sequential digits. Only meaningful once isValidIndianMobileLocal is
// already true.
const ASCENDING_DIGITS = '01234567890123456789';
const DESCENDING_DIGITS = '98765432109876543210';

export function isLikelyFakeIndianMobileLocal(local: string): boolean {
  if (new Set(local).size === 1) return true;
  return ASCENDING_DIGITS.includes(local) || DESCENDING_DIGITS.includes(local);
}

export function toE164(local: string): string {
  return `+91${local}`;
}

// Keeps only digits and caps at 10 — used as the TextInput onChangeText transform.
export function sanitizeLocalDigits(raw: string): string {
  return raw.replace(/\D/g, '').slice(0, 10);
}
