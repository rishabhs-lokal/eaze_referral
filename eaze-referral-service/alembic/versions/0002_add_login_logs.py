"""add login_logs

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-21

Records the first time each user_id (decoded from the banner link's base64 `user_id` param)
is seen by the webapp — one row per user_id, first-seen timestamp only.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "login_logs",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("user_id", sa.String(64), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.UniqueConstraint("user_id", name="login_logs_user_id_key"),
    )


def downgrade() -> None:
    op.drop_table("login_logs")
