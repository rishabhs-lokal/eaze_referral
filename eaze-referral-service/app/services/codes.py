import secrets

# No 0/O/1/I — avoids misreads when the code is shared as plain text.
_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def generate_referral_code(prefix: str = "EAZE") -> str:
    suffix = "".join(secrets.choice(_ALPHABET) for _ in range(6))
    return f"{prefix}-{suffix}"
