import { useEffect, useState } from 'react';
import * as Linking from 'expo-linking';

// The in-app banner opens this screen with the referrer's identity in the URL
// (web: https://refer.eaze.app/?ref=<id>, native: eaze://refer?ref=<id>).
// `expo-linking` reads both through one cross-platform API, so this needs no
// platform-suffixed adapter.
//
// TODO: this currently trusts a plain `ref` query param. Before this ships, the banner
// should hand off a short-lived signed token instead of a raw user id (see
// REFERRAL_PROGRAM_PLAN.md §2) and this hook should verify it server-side rather than
// trusting the client-supplied value directly.
export function useReferrerId(): string | null {
  const [referrerId, setReferrerId] = useState<string | null>(null);

  useEffect(() => {
    let mounted = true;

    Linking.getInitialURL().then((url) => {
      if (!mounted || !url) return;
      const { queryParams } = Linking.parse(url);
      const ref = queryParams?.ref;
      if (typeof ref === 'string') setReferrerId(ref);
    });

    const subscription = Linking.addEventListener('url', ({ url }) => {
      const { queryParams } = Linking.parse(url);
      const ref = queryParams?.ref;
      if (typeof ref === 'string') setReferrerId(ref);
    });

    return () => {
      mounted = false;
      subscription.remove();
    };
  }, []);

  return referrerId;
}
