import { useEffect, useState } from 'react';
import * as Linking from 'expo-linking';

// The in-app banner opens this screen with the user's identity base64-encoded in the URL
// (web: https://refer.eaze.app/?user_id=<base64>, native: eaze://refer?user_id=<base64>).
// The base64 decode happens on the BACKEND (app/services/identity.py), not here — the webapp
// just extracts the raw param and passes it straight through on every API call, so decoding is
// centralized in one place regardless of which client (this webapp, a future native client,
// direct API use) sends the request.
//
// There is no fallback: a user can only ever reach this screen via a link the Eaze app itself
// generated, so a missing user_id means the link didn't come from the app and the screen refuses
// to proceed (see ReferralScreen's `missing` state).
export type ReferrerIdStatus =
  | { status: 'loading' }
  | { status: 'ready'; userId: string }
  | { status: 'missing' };

function extractUserId(url: string): string | null {
  const { queryParams } = Linking.parse(url);
  const raw = queryParams?.user_id;
  return typeof raw === 'string' && raw.length > 0 ? raw : null;
}

export function useReferrerId(): ReferrerIdStatus {
  const [state, setState] = useState<ReferrerIdStatus>({ status: 'loading' });

  useEffect(() => {
    let mounted = true;

    Linking.getInitialURL().then((url) => {
      if (!mounted) return;
      const userId = url ? extractUserId(url) : null;
      setState(userId ? { status: 'ready', userId } : { status: 'missing' });
    });

    const subscription = Linking.addEventListener('url', ({ url }) => {
      const userId = extractUserId(url);
      setState(userId ? { status: 'ready', userId } : { status: 'missing' });
    });

    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);

  return state;
}
