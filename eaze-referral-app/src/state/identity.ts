// Mirrors eaze-referral-service/app/services/identity.py's decode_user_id — keep both in sync.
//
// The banner link carries the user's identity base64-encoded. The backend still does its own
// decode at the API boundary (it must: it can't trust a client), and this webapp still sends the
// raw base64 through untouched, so the API contract is unchanged. Decoding here as well buys two
// things the pass-through alone couldn't:
//   - a link whose user_id isn't real base64 is caught immediately, on the device, instead of
//     after a round trip that comes back 400
//   - the real user id is available to the UI, rather than only ever existing server-side
//
// Accepts standard or URL-safe base64, with or without padding, matching the Python.

// Python's base64.b64decode(validate=False) silently discards anything outside the base64
// alphabet; atob throws on it instead. Stripping first keeps the two implementations agreeing on
// which inputs are acceptable, rather than the web rejecting a link the backend would have taken.
const NON_BASE64 = /[^A-Za-z0-9+/=]/g;

export function decodeUserId(raw: string): string | null {
  if (!raw) return null;

  const normalized = raw.replace(/-/g, '+').replace(/_/g, '/').replace(NON_BASE64, '');
  const padded = normalized + '='.repeat((4 - (normalized.length % 4)) % 4);

  try {
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    // `fatal` so invalid UTF-8 throws rather than silently becoming U+FFFD, matching Python's
    // .decode("utf-8") — a user id that decoded to replacement characters would be worse than
    // no user id at all, because it would look valid all the way to the API call.
    const decoded = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
    return decoded.length > 0 ? decoded : null;
  } catch {
    return null;
  }
}
