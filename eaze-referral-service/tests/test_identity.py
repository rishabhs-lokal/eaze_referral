import base64

import pytest

from app.services.identity import decode_user_id


def test_decodes_standard_base64():
    encoded = base64.b64encode(b"eaze-user-123").decode()
    assert decode_user_id(encoded) == "eaze-user-123"


def test_decodes_url_safe_base64_without_padding():
    encoded = base64.urlsafe_b64encode(b"eaze-user-123").decode().rstrip("=")
    assert decode_user_id(encoded) == "eaze-user-123"


def test_rejects_empty_string():
    with pytest.raises(ValueError):
        decode_user_id("")


def test_rejects_invalid_base64():
    with pytest.raises(ValueError):
        decode_user_id("not valid base64!!!")
