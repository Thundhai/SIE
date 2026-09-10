"""SIE Milestone 38: Outcome Verification & Evidence

Revision ID: 0027
Revises: 0026
Create Date: 2026-09-09

Adds the governance layer answering *"can this recorded outcome be
trusted?"* -- the missing link the loop has needed since SIE Milestone
37's `IntelligenceOutcome`. See
`app/models/intelligence_outcome_verification.py`'s own docstring for
the full architectural rationale, and `docs/OUTCOME_VERIFICATION_V0_1.md`
for the "what a verification is / is not" account.

Two changes, both purely additive -- no existing table, column, row, or
type is altered or removed:

1. `intelligence_outcomes` gains a `UNIQUE(id, organization_id)`
   constraint -- identical precedent to `intelligence_decisions`' own
   SIE Milestone 37 constraint (migration 0026), and `sites`/`projects`'
   own SIE Milestone 35A constraint before that -- so a genuine,
   DB-enforced composite foreign key can reference it from the new
   table below.
2. A new `intelligence_outcome_verifications` table, tenant-scoped,
   `ON DELETE CASCADE` on `organization_id`, with a composite foreign
   key `(outcome_id, organization_id) -> intelligence_outcomes(id,
   organization_id)` (mirrors `intelligence_outcomes`'/
   `intelligence_decisions`' own SIE Milestone 37 composite-FK
   hardening technique -- safe here because `ON DELETE CASCADE`
   applies, no `SET NULL` conflict).

No backfill: `IntelligenceOutcomeVerification` is a brand-new concept
with no existing data to migrate.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0027'
down_revision: Union[str, None] = '0026'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_intelligence_outcomes_id_organization_id", "intelligence_outcomes", ["id", "organization_id"]
    )

    op.create_table(
        'intelligence_outcome_verifications',
        sa.Column('outcome_id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum(
                'VERIFIED', 'INSUFFICIENT_EVIDENCE', 'DISPUTED',
                name='intelligence_outcome_verification_status',
            ),
            nullable=False,
        ),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('verified_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('verified_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['verified_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['verified_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['outcome_id', 'organization_id'],
            ['intelligence_outcomes.id', 'intelligence_outcomes.organization_id'],
            ondelete='CASCADE', name='fk_outcome_verifications_outcome_id_organization_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_intelligence_outcome_verifications_organization_id'), 'intelligence_outcome_verifications',
        ['organization_id'], unique=False,
    )
    op.create_index(
        'ix_intelligence_outcome_verifications_org_outcome', 'intelligence_outcome_verifications',
        ['organization_id', 'outcome_id'], unique=False,
    )
    op.create_index(
        'ix_intelligence_outcome_verifications_org_verified_at', 'intelligence_outcome_verifications',
        ['organization_id', 'verified_at'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_intelligence_outcome_verifications_org_verified_at', table_name='intelligence_outcome_verifications'
    )
    op.drop_index(
        'ix_intelligence_outcome_verifications_org_outcome', table_name='intelligence_outcome_verifications'
    )
    op.drop_index(
        op.f('ix_intelligence_outcome_verifications_organization_id'), table_name='intelligence_outcome_verifications'
    )
    op.drop_table('intelligence_outcome_verifications')
    # Postgres drops the native enum type along with the table only when
    # no other table references it -- explicit drop mirrors migration
    # 0026's own downgrade() convention for its own native enum.
    sa.Enum(name='intelligence_outcome_verification_status').drop(op.get_bind(), checkfirst=True)

    op.drop_constraint(
        "uq_intelligence_outcomes_id_organization_id", "intelligence_outcomes", type_="unique"
    )
