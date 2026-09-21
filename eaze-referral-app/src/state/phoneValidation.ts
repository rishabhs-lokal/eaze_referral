// Indian mobile numbers: 10 digits, first digit 6-9. Stored/sent as E.164: +91XXXXXXXXXX.
const INDIAN_MOBILE_LOCAL = /^[6-9]\d{9}$/;

export function isValidIndianMobileLocal(local: string): boolean {
  return INDIAN_MOBILE_LOCAL.test(local);
}

export function toE164(local: string): string {
  return `+91${local}`;
}

// Keeps only digits and caps at 10 — used as the TextInput onChangeText transform.
export function sanitizeLocalDigits(raw: string): string {
  return raw.replace(/\D/g, '').slice(0, 10);
}
