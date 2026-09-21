// Mirrors eaze-referral-app/src/state/phoneValidation.ts — keep both in sync.
const INDIAN_E164 = /^\+91[6-9]\d{9}$/;

export function isValidIndianE164(phone: string): boolean {
  return INDIAN_E164.test(phone);
}
