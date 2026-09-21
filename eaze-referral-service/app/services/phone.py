import re

# Indian mobile numbers: 10 digits, first digit 6-9. Mirrors
# eaze-referral-app/src/state/phoneValidation.ts — keep both in sync.
_INDIAN_E164 = re.compile(r"^\+91[6-9]\d{9}$")


def is_valid_indian_e164(phone: str) -> bool:
    return bool(_INDIAN_E164.match(phone))
