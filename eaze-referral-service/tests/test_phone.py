from app.services.phone import is_valid_indian_e164


def test_valid_number():
    assert is_valid_indian_e164("+919876543210")


def test_rejects_missing_country_code():
    assert not is_valid_indian_e164("9876543210")


def test_rejects_landline_prefix():
    assert not is_valid_indian_e164("+915876543210")  # starts with 5, not 6-9


def test_rejects_wrong_length():
    assert not is_valid_indian_e164("+91987654321")  # 9 digits
    assert not is_valid_indian_e164("+9198765432100")  # 11 digits


def test_rejects_non_digits():
    assert not is_valid_indian_e164("+9198765abcde")
