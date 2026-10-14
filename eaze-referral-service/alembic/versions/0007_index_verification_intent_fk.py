"""Index the foreign key the per-referrer cap joins through.

Capping referrals per referrer turns "how many has this person made" into a hot query: it runs
on every page load (GET /api/referral/code/{user_id}) and again inside the write transaction of
every save, where it is evaluated while the referrer's row is locked. The count outer-joins
referral_verifications to exclude numbers later disqualified as pre-existing Eaze accounts, and
referral_intent_id is a foreign key — which Postgres, unlike a primary key or a unique
constraint, does NOT index on its own.

referral_intents.referrer_user_id is deliberately NOT here: 0001 has always created
idx_referral_intents_referrer. app/models.py had simply never declared it, so the model read as
though the column were unindexed. This revision landing alongside a models.py that now declares
both is what brings the two back into agreement — the index itself predates all of this.

Index-only addition: no data is read or written, every existing row is untouched, and the
downgrade is exact.

Revision ID: 0007
Revises: 0006
"""

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_referral_verifications_intent", "referral_verifications", ["referral_intent_id"]
    )


def downgrade() -> None:
    op.drop_index("idx_referral_verifications_intent", table_name="referral_verifications")
