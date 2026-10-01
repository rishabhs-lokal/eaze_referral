from functools import lru_cache
from typing import Annotated, Any

from pydantic import BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _blank_to_none(value: Any) -> Any:
    """Treat an empty/whitespace env var as absent.

    Docker Compose's `${VAR:-}` substitution passes an EMPTY STRING when the variable isn't set,
    not nothing at all — so an optional setting declared in a compose file but left unconfigured
    arrives as "". Without this, `int | None` fields reject "" outright and the app refuses to
    start, which is exactly backwards: these settings are optional, and not setting them is the
    normal case. Applies to the k8s manifests too, where an unset ConfigMap value behaves the
    same way.
    """
    if isinstance(value, str) and not value.strip():
        return None
    return value


# Optional settings whose absence is normal and must not be a startup error. Deliberately NOT
# used for signup_bonus_coins/recharge_bonus_coins — those have no default on purpose, so a
# deployment that forgets them fails loudly rather than paying out some unintended amount.
OptionalStr = Annotated[str | None, BeforeValidator(_blank_to_none)]
OptionalInt = Annotated[int | None, BeforeValidator(_blank_to_none)]


class Settings(BaseSettings):
    """All configuration comes from the environment — nothing hardcoded, nothing read from a
    committed file. This is what makes the service deployable unchanged across local Docker
    Compose, staging, and multiple Kubernetes pods: only the env differs.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Any Postgres-wire-compatible database: vanilla Postgres, RDS, Cloud SQL, Supabase, Neon,
    # CockroachDB in Postgres mode, etc. Standard libpq-style URL, e.g.
    # postgresql://user:pass@host:5432/dbname?sslmode=require
    database_url: str = "postgresql://postgres:postgres@localhost:5432/eaze"
    # "disable" for local Docker Compose Postgres (no TLS listener); set to "require" for managed
    # providers (RDS, Cloud SQL, Supabase, ...) that mandate TLS.
    database_ssl_mode: str = "disable"
    # Session timezone set on every connection this app opens — every timestamp we write or read
    # (login_logs, referral_logs, message_copy_logs, ...) is interpreted/displayed in this zone.
    db_timezone: str = "Asia/Kolkata"

    # Per-pod pool sizing. With N pod replicas, total connections against the database is
    # N * (db_pool_size + db_pool_max_overflow) — keep this in mind against the database's
    # max_connections when choosing replica counts.
    db_pool_size: int = 5
    db_pool_max_overflow: int = 5
    db_pool_timeout_seconds: int = 30
    db_pool_recycle_seconds: int = 1800  # recycle connections periodically; managed Postgres
    # instances (e.g. RDS Proxy, PgBouncer in front of Cloud SQL) often close idle connections
    # server-side without warning.

    # How long to retry the initial DB connectivity check at startup before giving up — covers
    # the case where the database isn't ready yet when the pod starts (e.g. a fresh cluster still
    # bringing up its Postgres StatefulSet).
    db_startup_retry_attempts: int = 10
    db_startup_retry_delay_seconds: float = 2.0

    # The two things that actually differ between the 1000-coin and 500-coin deployments of this
    # exact same codebase — see docker-compose.tier-*.yml and k8s/tier-*/. No default: there is no
    # un-tiered deployment anymore, so a config that forgets to set these fails at startup instead
    # of silently running as some other, unintended reward amount.
    signup_bonus_coins: int
    recharge_bonus_coins: int

    # Optional mirror of every accepted referral into a Google Sheet, via an Apps Script Web
    # App endpoint — see google-apps-script/referral_sheet_webhook.gs for the script and its
    # deployment steps. Unset (the default) means the feature is entirely off: submit_intents
    # behaves exactly as it did before this existed.
    google_sheets_webhook_url: OptionalStr = None
    google_sheets_webhook_secret: OptionalStr = None

    # Payment verification against Eaze's real warehouse data, via Redash — see
    # app/services/redash.py and the README's "Payment verification via Redash" section.
    # Unset (the default) means the reconciler is off and the reward pipeline behaves exactly
    # as it did before: coins follow our own recharge webhook alone. With these set, a
    # referrer's coins are additionally confirmed against real payment data before crediting.
    redash_base_url: OptionalStr = None
    redash_api_key: OptionalStr = None
    # Query that maps a phone number to Eaze's own user id — proves the referred person really
    # registered. Parameter: mobile_numbers.
    redash_verify_phone_query_id: OptionalInt = None
    # Query that returns payment facts for a given Eaze user id — proves they really paid.
    # Parameter: user_ids.
    redash_payments_query_id: OptionalInt = None
    # How many phone numbers / user ids to pack into one Redash query. Redash parameters are
    # substituted into SQL, so this bounds the generated statement size.
    redash_batch_size: int = 200

    # Eaze's coin-credit API — the thing that actually puts coins in a user's wallet. Unset
    # means the reward pipeline still decides who is owed what and records it, but no coins
    # reach a real wallet; see app/services/eaze_wallet.py.
    eaze_free_coins_api_url: OptionalStr = None
    eaze_free_coins_auth_key: OptionalStr = None
    # The header the key is sent in. Configurable because it differs per deployment of this API
    # (the equivalent Dostt service uses x-n8n-auth-key; Eaze does not) and guessing wrong means
    # every credit call 401s. Change this without a code change if the API expects another name.
    eaze_free_coins_auth_header: str = "Authorization"
    # Some deployments of this endpoint want a human-readable batch label alongside the file.
    eaze_free_coins_batch_name: str = "Eaze Referral Program"

    public_base_url: str = "http://localhost:8000"
    play_store_url: str = "https://play.google.com/store/apps/details?id=com.eaze.app"
    app_store_url: str = "https://apps.apple.com/app/idXXXXXXXXX"
    fallback_url: str = "https://play.google.com/store/apps/details?id=com.eaze.app"

    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()
