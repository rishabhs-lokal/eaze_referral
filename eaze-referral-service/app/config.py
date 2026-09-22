from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


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

    public_base_url: str = "http://localhost:8000"
    play_store_url: str = "https://play.google.com/store/apps/details?id=com.eaze.app"
    app_store_url: str = "https://apps.apple.com/app/idXXXXXXXXX"
    fallback_url: str = "https://play.google.com/store/apps/details?id=com.eaze.app"

    log_level: str = "info"


@lru_cache
def get_settings() -> Settings:
    return Settings()
