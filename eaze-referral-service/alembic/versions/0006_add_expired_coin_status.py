"""Allow EXPIRED as a coin status, so dead referrals can leave the reconciler's queue.

Nothing previously took a referral out of that queue except being paid or being disqualified as
a pre-existing user. A friend who was referred and never installed stayed in it forever, and the
queue is served round-robin against a fixed per-pass budget — so over time the dead rows crowd
out the live ones.

EXPIRED rather than reusing SKIPPED (which the constraint already allows but no code writes):
the two mean different things and you want to count them separately. SKIPPED is an eligibility
verdict — this person could never have earned coins. EXPIRED is a funnel fact — this invite went
nowhere. Conflating them would make "how many invites convert" unanswerable.

Widening a CHECK constraint is backward-compatible: every existing row already satisfies the new
one, so there is no data migration and no table rewrite.

Revision ID: 0006
Revises: 0005
"""

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_CONSTRAINTS = {
    "referral_verifications_signup_coins_status": "signup_coins_status",
    "referral_verifications_referrer_coins_status": "referrer_coins_status",
}


def upgrade() -> None:
    for name, column in _CONSTRAINTS.items():
        op.drop_constraint(name, "referral_verifications", type_="check")
        op.create_check_constraint(
            name,
            "referral_verifications",
            f"{column} IN ('PENDING', 'CREDITED', 'SKIPPED', 'EXPIRED')",
        )


def downgrade() -> None:
    # Narrowing the constraint would fail against any row already marked EXPIRED, so those are
    # returned to PENDING first. That is the honest inverse: without EXPIRED in the vocabulary,
    # an expired referral is simply one still waiting.
    for name, column in _CONSTRAINTS.items():
        op.execute(
            f"UPDATE referral_verifications SET {column} = 'PENDING' WHERE {column} = 'EXPIRED'"
        )
        op.drop_constraint(name, "referral_verifications", type_="check")
        op.create_check_constraint(
            name,
            "referral_verifications",
            f"{column} IN ('PENDING', 'CREDITED', 'SKIPPED')",
        )
