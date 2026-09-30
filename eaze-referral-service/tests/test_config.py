"""Docker Compose's `${VAR:-}` and an unset ConfigMap value both pass an EMPTY STRING rather
than nothing at all. Every optional setting therefore has to survive being handed "" — a real
outage came from this: the Redash query-id fields were declared in the compose files with no
values, arrived as "", failed `int | None` validation, and the app refused to boot on both
tiers even though the feature they configure is off by default.
"""

import os
from unittest import mock

import pytest

from app.config import Settings

_REQUIRED = {"SIGNUP_BONUS_COINS": "1000", "RECHARGE_BONUS_COINS": "1000"}

_OPTIONAL_ENV_VARS = [
    "GOOGLE_SHEETS_WEBHOOK_URL",
    "GOOGLE_SHEETS_WEBHOOK_SECRET",
    "REDASH_BASE_URL",
    "REDASH_API_KEY",
    "REDASH_VERIFY_PHONE_QUERY_ID",
    "REDASH_PAYMENTS_QUERY_ID",
]


def _settings(env: dict[str, str]) -> Settings:
    with mock.patch.dict(os.environ, {**_REQUIRED, **env}, clear=True):
        # _env_file=None so a developer's local .env can't mask what's being asserted here.
        return Settings(_env_file=None)


@pytest.mark.parametrize("var", _OPTIONAL_ENV_VARS)
def test_blank_optional_env_var_does_not_break_startup(var: str) -> None:
    settings = _settings({var: ""})
    assert getattr(settings, var.lower()) is None


def test_all_optional_vars_blank_at_once() -> None:
    """The actual shape of a default deployment: every optional var declared, none configured."""
    settings = _settings({var: "" for var in _OPTIONAL_ENV_VARS})
    for var in _OPTIONAL_ENV_VARS:
        assert getattr(settings, var.lower()) is None


def test_whitespace_only_is_also_treated_as_unset() -> None:
    settings = _settings({"REDASH_BASE_URL": "   ", "REDASH_PAYMENTS_QUERY_ID": "  "})
    assert settings.redash_base_url is None
    assert settings.redash_payments_query_id is None


def test_real_values_still_parse() -> None:
    settings = _settings(
        {"REDASH_BASE_URL": "https://redash.example.com", "REDASH_PAYMENTS_QUERY_ID": "17564"}
    )
    assert settings.redash_base_url == "https://redash.example.com"
    assert settings.redash_payments_query_id == 17564


def test_missing_coin_amounts_still_fail_loudly() -> None:
    """The blank-to-None leniency must not have leaked onto the reward amounts — a deployment
    that forgets those has to fail, not quietly pay out something unintended."""
    with mock.patch.dict(os.environ, {}, clear=True):
        with pytest.raises(Exception):
            Settings(_env_file=None)
