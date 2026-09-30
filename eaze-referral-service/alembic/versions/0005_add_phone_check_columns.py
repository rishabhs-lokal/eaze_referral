"""add pre-existing-user phone check to referral_verifications

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-30

Records whether a referred number was ALREADY an Eaze user at the moment it was referred, as
confirmed against the real user base via Redash. That disqualifies the referral outright, and is
a different question from signup_status (which asks whether they have registered by now — the
outcome we want). See the column comments on app.models.ReferralVerification.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "referral_verifications",
        sa.Column("phone_check_status", sa.String(20), nullable=False, server_default="UNCHECKED"),
    )
    op.add_column(
        "referral_verifications",
        sa.Column("phone_checked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "referral_verifications",
        sa.Column("pre_existing_eaze_user_id", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "referral_verifications_phone_check_status",
        "referral_verifications",
        "phone_check_status IN ('UNCHECKED', 'VERIFIED', 'ALREADY_REGISTERED')",
    )
    # The reconciler's queue for numbers still awaiting their pre-existing-user check.
    op.create_index(
        "idx_referral_verifications_phone_check",
        "referral_verifications",
        ["phone_check_status"],
    )


def downgrade() -> None:
    op.drop_index("idx_referral_verifications_phone_check", table_name="referral_verifications")
    op.drop_constraint(
        "referral_verifications_phone_check_status", "referral_verifications", type_="check"
    )
    op.drop_column("referral_verifications", "pre_existing_eaze_user_id")
    op.drop_column("referral_verifications", "phone_checked_at")
    op.drop_column("referral_verifications", "phone_check_status")
