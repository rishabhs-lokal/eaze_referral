"""add referral_logs and message_copy_logs

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-21

referral_logs: every phone number a referrer submitted, append-only, no dedup (distinct from
referral_intents, which drives the reward pipeline).
message_copy_logs: one row per "Copy message" tap.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "referral_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("phone_e164", sa.String(16), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_referral_logs_user_id", "referral_logs", ["user_id"])

    op.create_table(
        "message_copy_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("copied_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("idx_message_copy_logs_user_id", "message_copy_logs", ["user_id"])


def downgrade() -> None:
    op.drop_index("idx_message_copy_logs_user_id", table_name="message_copy_logs")
    op.drop_table("message_copy_logs")
    op.drop_index("idx_referral_logs_user_id", table_name="referral_logs")
    op.drop_table("referral_logs")
