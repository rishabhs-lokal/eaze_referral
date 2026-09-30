import { useEffect, useState } from 'react';
import * as Linking from 'expo-linking';
import { decodeUserId } from './identity';

// The in-app banner opens this screen with the user's identity base64-encoded in the URL
// (web: https://refer.eaze.app/?user_id=<base64>, native: eaze://refer?user_id=<base64>).
//
// The base64 is decoded in both places. The BACKEND (app/services/identity.py) decodes at the
// API boundary because it cannot trust a client, and because everything downstream
// (users.external_ref, login_logs, referral_logs, message_copy_logs) must store the real user id
// no matter which client called it. Here, it's decoded so the real id is available on the device
// rather than only ever existing server-side.
//
// `userId` is still the RAW base64 and is still what gets sent on every API call — the wire
// contract is unchanged. `decodedUserId` is the opened form, for local use only.
//
// Decoding here deliberately gates nothing: the id comes from a link the Eaze app generated, so
// it's well-formed in practice, and a decode that somehow failed should never be what stops a
// real user from referring someone. `decodedUserId` is simply null in that case and the backend
// stays the authority.
//
// There is no fallback for a *missing* user_id though: a user can only ever reach this screen via
// the app's own banner, so no user_id at all means the link didn't come from the app and the
// screen refuses to proceed (see ReferralScreen's `missing` state).
export type ReferrerIdStatus =
  | { status: 'loading' }
  | { status: 'ready'; userId: string; decodedUserId: string | null }
  | { status: 'missing' };

function extractReferrer(url: string): { userId: string; decodedUserId: string | null } | null {
  const { queryParams } = Linking.parse(url);
  const raw = queryParams?.user_id;
  if (typeof raw !== 'string' || raw.length === 0) return null;

  return { userId: raw, decodedUserId: decodeUserId(raw) };
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
