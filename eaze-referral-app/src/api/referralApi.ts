import { API_BASE_URL } from './config';

export type ReferralCodeResponse = {
  code: string;
  shareUrl: string;
  // How much of this referrer's allowance is already spent, and what the allowance is. Both
  // come from the server on every load: the allowance is per referrer and persists across
  // sessions, so there is nothing local the page could work it out from.
  referralsUsed: number;
  referralsLimit: number;
};

export type SubmitIntentsResponse = {
  saved: number;
  skipped: { phone: string; reason: string }[];
  referralsUsed: number;
  referralsLimit: number;
};

export async function fetchReferralCode(referrerUserId: string): Promise<ReferralCodeResponse> {
  const res = await fetch(`${API_BASE_URL}/api/referral/code/${encodeURIComponent(referrerUserId)}`);
  if (!res.ok) throw new Error(`fetchReferralCode failed: ${res.status}`);
  return res.json();
}

export async function submitReferralIntents(params: {
  referrerUserId: string;
  phoneNumbersE164: string[];
}): Promise<SubmitIntentsResponse> {
  const res = await fetch(`${API_BASE_URL}/api/referral/intents`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(params),
  });
  if (!res.ok) throw new Error(`submitReferralIntents failed: ${res.status}`);
  return res.json();
}

// Fire-and-forget from the caller's point of view — logging a copy-button click should never
// block or surface an error on top of the actual copy action.
export async function logMessageCopy(userId: string): Promise<void> {
  await fetch(`${API_BASE_URL}/api/referral/copy-log`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ userId }),
  });
}
