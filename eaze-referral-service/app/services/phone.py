import re

# Indian mobile numbers: 10 digits, first digit 6-9. Mirrors
# eaze-referral-app/src/state/phoneValidation.ts — keep both in sync.
_INDIAN_E164 = re.compile(r"^\+91[6-9]\d{9}$")

_ASCENDING_DIGITS = "01234567890123456789"
_DESCENDING_DIGITS = "98765432109876543210"


def is_valid_indian_e164(phone: str) -> bool:
    return bool(_INDIAN_E164.match(phone))


def is_likely_fake(phone: str) -> bool:
    """Cheap first filter against obviously junk input — every digit the same
    (9999999999, the field's own placeholder text being the most likely accidental
    submission) or a run of simple sequential digits (6789012345 or the reverse). Not a
    fraud-detection system, just catches the two patterns real fraud never bothers with
    because they're this easy to catch. Only called on already-format-valid numbers."""
    local = phone[3:]  # strip the "+91" prefix
    if len(set(local)) == 1:
        return True
    return local in _ASCENDING_DIGITS or local in _DESCENDING_DIGITS
