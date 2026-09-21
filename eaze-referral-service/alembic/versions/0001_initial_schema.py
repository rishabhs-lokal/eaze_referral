"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-09-21

Ports the schema first written for the Node prototype (eaze-referral-backend/migrations/001_init.sql)
to Alembic. `users` and `recharges` are minimal stand-ins for the real Eaze backend's tables — see
the README for pointing the foreign keys at the real ones instead when this is integrated.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("external_ref", sa.String(64), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("wallet_balance", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("phone_e164", name="users_phone_e164_key"),
        sa.UniqueConstraint("external_ref", name="users_external_ref_key"),
    )

    op.create_table(
        "recharges",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount_paise", sa.BigInteger(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )

    op.create_table(
        "referral_codes",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("code", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", name="referral_codes_user_id_key"),
        sa.UniqueConstraint("code", name="referral_codes_code_key"),
    )

    op.create_table(
        "referral_intents",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("referrer_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("matched_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("phone_e164", name="referral_intents_phone_e164_key"),
        sa.CheckConstraint(r"phone_e164 ~ '^\+91[6-9]\d{9}$'", name="referral_intents_phone_format"),
    )
    op.create_index("idx_referral_intents_referrer", "referral_intents", ["referrer_user_id"])
    op.create_index("idx_referral_intents_status", "referral_intents", ["status"])

    op.create_table(
        "referral_clicks",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("referral_code_id", sa.BigInteger(), sa.ForeignKey("referral_codes.id"), nullable=False),
        sa.Column("ip_address", postgresql.INET(), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("clicked_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_referral_clicks_code", "referral_clicks", ["referral_code_id"])

    op.create_table(
        "referrals",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("referrer_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("referred_user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("referred_phone_e164", sa.String(16), nullable=False),
        sa.Column("referral_intent_id", sa.BigInteger(), sa.ForeignKey("referral_intents.id"), nullable=False),
        sa.Column("referral_code_id", sa.BigInteger(), sa.ForeignKey("referral_codes.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="SIGNED_UP"),
        sa.Column("triggering_recharge_id", sa.BigInteger(), sa.ForeignKey("recharges.id"), nullable=True),
        sa.Column("signup_rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recharge_rewarded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("referred_user_id", name="referrals_referred_user_id_key"),
        sa.CheckConstraint("referrer_user_id <> referred_user_id", name="no_self_referral"),
    )
    op.create_index("idx_referrals_referrer", "referrals", ["referrer_user_id"])
    op.create_index("idx_referrals_status", "referrals", ["status"])

    op.create_table(
        "wallet_transactions",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("amount", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(30), nullable=False),
        sa.Column("reference_type", sa.String(30), nullable=False),
        sa.Column("reference_id", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", "type", "reference_id", name="wallet_transactions_idempotency"),
    )


def downgrade() -> None:
    op.drop_table("wallet_transactions")
    op.drop_index("idx_referrals_status", table_name="referrals")
    op.drop_index("idx_referrals_referrer", table_name="referrals")
    op.drop_table("referrals")
    op.drop_index("idx_referral_clicks_code", table_name="referral_clicks")
    op.drop_table("referral_clicks")
    op.drop_index("idx_referral_intents_status", table_name="referral_intents")
    op.drop_index("idx_referral_intents_referrer", table_name="referral_intents")
    op.drop_table("referral_intents")
    op.drop_table("referral_codes")
    op.drop_table("recharges")
    op.drop_table("users")
