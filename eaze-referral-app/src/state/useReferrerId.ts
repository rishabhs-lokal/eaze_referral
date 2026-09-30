import { useEffect, useState } from 'react';
import * as Linking from 'expo-linking';
import { decodeUserId } from './identity';

// The in-app banner opens this screen with the user's identity base64-encoded in the URL
// (web: https://refer.eaze.app/?user_id=<base64>, native: eaze://refer?user_id=<base64>).
//
// The base64 is decoded in BOTH places, on purpose, and they are not redundant:
//   - the BACKEND (app/services/identity.py) decodes at the API boundary because it cannot trust
//     a client, and because everything downstream (users.external_ref, login_logs, referral_logs,
//     message_copy_logs) must store the real user id no matter which client called it
//   - here, so a link carrying a malformed user_id is rejected on the spot instead of after a
//     round trip that returns 400, and so the real user id exists on the device rather than only
//     ever server-side
// `userId` below is still the RAW base64, and that is still what gets sent on every API call —
// the wire contract is unchanged. `decodedUserId` is the opened form, for local use only.
//
// There is no fallback: a user can only ever reach this screen via a link the Eaze app itself
// generated, so a missing user_id means the link didn't come from the app and the screen refuses
// to proceed (see ReferralScreen's `missing` state). A user_id that is present but doesn't decode
// is treated the same way — it cannot have come from the app either.
export type ReferrerIdStatus =
  | { status: 'loading' }
  | { status: 'ready'; userId: string; decodedUserId: string }
  | { status: 'missing' };

function extractReferrer(url: string): { userId: string; decodedUserId: string } | null {
  const { queryParams } = Linking.parse(url);
  const raw = queryParams?.user_id;
  if (typeof raw !== 'string' || raw.length === 0) return null;

  const decodedUserId = decodeUserId(raw);
  return decodedUserId ? { userId: raw, decodedUserId } : null;
}

export function useReferrerId(): ReferrerIdStatus {
  const [state, setState] = useState<ReferrerIdStatus>({ status: 'loading' });

  useEffect(() => {
    let mounted = true;

    Linking.getInitialURL().then((url) => {
      if (!mounted) return;
      const referrer = url ? extractReferrer(url) : null;
      setState(referrer ? { status: 'ready', ...referrer } : { status: 'missing' });
    });

    const subscription = Linking.addEventListener('url', ({ url }) => {
      const referrer = extractReferrer(url);
      setState(referrer ? { status: 'ready', ...referrer } : { status: 'missing' });
    });

    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);

  return state;
}
