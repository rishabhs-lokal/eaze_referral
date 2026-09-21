"""Decodes the base64 user_id the webapp receives from the Eaze app's banner link (see
eaze-referral-app/src/state/useReferrerId.ts) back to its original form. Decoding happens here,
centrally, at the API boundary — not on the frontend — so every caller (the current webapp, any
future native client, direct API use) gets the same normalization for free, and everything
downstream (users.external_ref, login_logs, referral_logs, message_copy_logs) stores and queries
against the real user id, never a base64 encoding of it.
"""

import base64
import binascii


def decode_user_id(raw: str) -> str:
    """Accepts standard or URL-safe base64, with or without padding. Raises ValueError on
    anything that doesn't decode to valid UTF-8 text."""
    if not raw:
        raise ValueError("user_id is required")

    normalized = raw.replace("-", "+").replace("_", "/")
    normalized += "=" * ((-len(normalized)) % 4)

    try:
        return base64.b64decode(normalized, validate=False).decode("utf-8")
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(f"Invalid base64 user_id: {raw!r}") from exc
