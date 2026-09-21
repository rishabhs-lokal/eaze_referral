"""SQLAlchemy models — the single source of truth for the schema. Alembic's initial migration
(alembic/versions/0001_initial_schema.py) mirrors this by hand for a readable first migration;
every schema change after this one should be authored with:

    alembic revision --autogenerate -m "describe the change"

which diffs the live database against these models and writes the migration for you — that's the
"generate migrations for every database change" requirement satisfied going forward.
"""

import datetime as dt

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import INET
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


# `users` and `recharges` are minimal stand-ins for the real Eaze backend's tables, matching the
# Node prototype — see the README for how to point this at the real tables instead.
class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    phone_e164: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    # Shim for the referral webapp's pre-auth-handoff flow — see REFERRAL_PROGRAM_PLAN.md §2.
    external_ref: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="ACTIVE")
    wallet_balance: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Recharge(Base):
    __tablename__ = "recharges"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    amount_paise: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)  # SUCCESS | FAILED | REFUNDED
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReferralCode(Base):
    __tablename__ = "referral_codes"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReferralIntent(Base):
    """A phone number a referrer entered directly in the webapp — the sole attribution mechanism.
    There is no code/deep-link fallback (see REFERRAL_PROGRAM_PLAN.md): a referral relationship
    exists if and only if a matching PENDING row exists here at signup time."""

    __tablename__ = "referral_intents"
    __table_args__ = (
        CheckConstraint(r"phone_e164 ~ '^\+91[6-9]\d{9}$'", name="referral_intents_phone_format"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")  # PENDING | MATCHED | EXPIRED
    matched_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    matched_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReferralClick(Base):
    """Click tracking on the /r/{code} redirect — funnel visibility only, never a source of
    reward attribution."""

    __tablename__ = "referral_clicks"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    referral_code_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("referral_codes.id"), nullable=False)
    ip_address: Mapped[str | None] = mapped_column(INET, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    clicked_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (
        CheckConstraint("referrer_user_id <> referred_user_id", name="no_self_referral"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    referrer_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    referred_user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), unique=True, nullable=False)
    referred_phone_e164: Mapped[str] = mapped_column(String(16), nullable=False)
    referral_intent_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("referral_intents.id"), nullable=False)
    # Analytics-only correlation with the share link that was clicked, if any — never attribution.
    referral_code_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("referral_codes.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="SIGNED_UP")  # SIGNED_UP | REWARDED | REVERSED
    triggering_recharge_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("recharges.id"), nullable=True)
    signup_rewarded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    recharge_rewarded_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class LoginLog(Base):
    """Records the first time each user_id (as decoded from the banner link's base64 `user_id`
    query param — see eaze-referral-app/src/state/useReferrerId.ts) is seen by the webapp.
    One row per user_id, ever — `first_seen_at` is never updated on later visits."""

    __tablename__ = "login_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    first_seen_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class ReferralLog(Base):
    """Append-only audit trail of every phone number a referrer submitted, and when — distinct
    from `referral_intents`, which enforces one-referrer-per-phone and drives the reward
    pipeline. This table has no dedup: the program's own reporting depends on seeing every
    submission a user made, not just the one that won attribution."""

    __tablename__ = "referral_logs"
    __table_args__ = (Index("idx_referral_logs_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phone_e164: Mapped[str] = mapped_column(String(16), nullable=False)
    recorded_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class MessageCopyLog(Base):
    """One row per tap of "Copy message" — user_id and when. The count of times a user copied
    is COUNT(*) GROUP BY user_id; kept as a full log rather than a running counter so individual
    click times are preserved too, not just a total."""

    __tablename__ = "message_copy_logs"
    __table_args__ = (Index("idx_message_copy_logs_user_id", "user_id"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=False)
    copied_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WalletTransaction(Base):
    """Coin ledger. UNIQUE(user_id, type, reference_id) makes every credit idempotent against
    retries — the same reward can never be paid twice."""

    __tablename__ = "wallet_transactions"
    __table_args__ = (UniqueConstraint("user_id", "type", "reference_id", name="wallet_transactions_idempotency"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    type: Mapped[str] = mapped_column(String(30), nullable=False)  # REFERRAL_SIGNUP_BONUS | REFERRAL_RECHARGE_BONUS | REFERRAL_REVERSAL
    reference_type: Mapped[str] = mapped_column(String(30), nullable=False)  # 'referral'
    reference_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
