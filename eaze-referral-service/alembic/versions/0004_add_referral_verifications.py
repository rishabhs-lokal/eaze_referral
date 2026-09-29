"""add referral_verifications

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-29

One row per referred phone number tracking whether that person actually registered on Eaze,
actually paid, and whether each side's coins were credited. See the docstring on
app.models.ReferralVerification for why this exists alongside referral_intents/referrals.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_verifications",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("phone_e164", sa.String(16), nullable=False, unique=True),
        sa.Column("referrer_external_id", sa.String(64), nullable=True),
        sa.Column("referrer_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("referral_intent_id", sa.BigInteger(), sa.ForeignKey("referral_intents.id"), nullable=True),
        sa.Column("referral_id", sa.BigInteger(), sa.ForeignKey("referrals.id"), nullable=True),
        # did they register on Eaze?
        sa.Column("signup_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("eaze_user_id", sa.String(64), nullable=True),
        sa.Column("signed_up_at", sa.DateTime(timezone=True), nullable=True),
        # did they pay? — the gate on the referrer's reward
        sa.Column("payment_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("first_payment_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_payment_amount_paise", sa.BigInteger(), nullable=True),
        sa.Column("successful_payment_count", sa.Integer(), nullable=False, server_default="0"),
        # were the coins handed out?
        sa.Column("signup_coins_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("signup_coins_amount", sa.Integer(), nullable=True),
        sa.Column("signup_coins_credited_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("referrer_coins_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("referrer_coins_amount", sa.Integer(), nullable=True),
        sa.Column("referrer_coins_credited_at", sa.DateTime(timezone=True), nullable=True),
        # reconciler bookkeeping
        sa.Column("source", sa.String(20), nullable=False, server_default="WEBHOOK"),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("check_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint(
            "signup_status IN ('PENDING', 'SIGNED_UP', 'NOT_FOUND')",
            name="referral_verifications_signup_status",
        ),
        sa.CheckConstraint(
            "payment_status IN ('PENDING', 'PAID', 'NO_PAYMENT')",
            name="referral_verifications_payment_status",
        ),
        sa.CheckConstraint(
            "signup_coins_status IN ('PENDING', 'CREDITED', 'SKIPPED')",
            name="referral_verifications_signup_coins_status",
        ),
        sa.CheckConstraint(
            "referrer_coins_status IN ('PENDING', 'CREDITED', 'SKIPPED')",
            name="referral_verifications_referrer_coins_status",
        ),
    )
    op.create_index(
        "idx_referral_verifications_pending",
        "referral_verifications",
        ["payment_status", "referrer_coins_status"],
    )
    op.create_index(
        "idx_referral_verifications_referrer", "referral_verifications", ["referrer_external_id"]
    )

    # Backfill from what's already known, so this table is complete from day one rather than
    # only covering referrals made after the deploy. Every existing intent becomes a row; the
    # signup/payment/coin columns are then filled in from referrals where a match already
    # exists. Numbers referred long ago that never signed up correctly stay all-PENDING.
    op.execute(
        """
        INSERT INTO referral_verifications (
            phone_e164, referrer_user_id, referral_intent_id, created_at
        )
        SELECT i.phone_e164, i.referrer_user_id, i.id, i.created_at
        FROM referral_intents i
        ON CONFLICT (phone_e164) DO NOTHING
        """
    )
    op.execute(
        """
        UPDATE referral_verifications v
        SET referral_id          = r.id,
            signup_status        = 'SIGNED_UP',
            signed_up_at         = r.created_at,
            signup_coins_status  = CASE WHEN r.signup_rewarded_at IS NOT NULL
                                        THEN 'CREDITED' ELSE 'PENDING' END,
            signup_coins_credited_at = r.signup_rewarded_at,
            payment_status       = CASE WHEN r.recharge_rewarded_at IS NOT NULL
                                        THEN 'PAID' ELSE 'PENDING' END,
            referrer_coins_status = CASE WHEN r.recharge_rewarded_at IS NOT NULL
                                        THEN 'CREDITED' ELSE 'PENDING' END,
            referrer_coins_credited_at = r.recharge_rewarded_at,
            updated_at           = now()
        FROM referrals r
        WHERE r.referred_phone_e164 = v.phone_e164
        """
    )


def downgrade() -> None:
    op.drop_index("idx_referral_verifications_referrer", table_name="referral_verifications")
    op.drop_index("idx_referral_verifications_pending", table_name="referral_verifications")
    op.drop_table("referral_verifications")
