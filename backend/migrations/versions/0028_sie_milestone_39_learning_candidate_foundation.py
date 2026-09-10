"""SIE Milestone 39: Learning Candidate Foundation

Revision ID: 0028
Revises: 0027
Create Date: 2026-09-09

Establishes the governed entry boundary into `LEARN` -- answering *"how
does a verified outcome become a governed learning signal without SIE
actually learning yet?"* See
`app/models/intelligence_learning_candidate.py`'s own docstring for the
full architectural rationale, and `docs/LEARNING_CANDIDATE_V0_1.md` for
the "what this milestone is / is not" account. No ML training, no
automatic model/threshold/rule mutation, no M40 organizational memory,
no M41 learning integration -- this migration only adds new, purely
additive schema.

Three changes, none altering or removing any existing table, column,
row, or type:

1. `intelligence_outcome_verifications` gains a `UNIQUE(id,
   organization_id)` constraint -- identical precedent to
   `intelligence_outcomes`' own SIE Milestone 38 constraint (migration
   0027), so a genuine, DB-enforced composite foreign key can reference
   it from the new table below.
2. A new `intelligence_learning_candidates` table, tenant-scoped, `ON
   DELETE CASCADE` on `organization_id`, with composite foreign keys
   `(outcome_id, organization_id) -> intelligence_outcomes(id,
   organization_id)` and `(verification_id, organization_id) ->
   intelligence_outcome_verifications(id, organization_id)`, plus a
   `UNIQUE(organization_id, outcome_id)` natural key (idempotent by
   construction -- M39 spec §15).
3. A new `intelligence_learning_candidate_governance_decisions` table,
   tenant-scoped, `ON DELETE CASCADE` on `organization_id`, with a
   composite foreign key `(candidate_id, organization_id) ->
   intelligence_learning_candidates(id, organization_id)` -- the
   append-only ACCEPT/REJECT governance history for one candidate.

No backfill: `IntelligenceLearningCandidate` and
`IntelligenceLearningCandidateGovernanceDecision` are brand-new concepts
with no existing data to migrate.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0028'
down_revision: Union[str, None] = '0027'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_intelligence_outcome_verifications_id_organization_id",
        "intelligence_outcome_verifications",
        ["id", "organization_id"],
    )

    op.create_table(
        'intelligence_learning_candidates',
        sa.Column('outcome_id', sa.Uuid(), nullable=False),
        sa.Column('verification_id', sa.Uuid(), nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('created_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['outcome_id', 'organization_id'],
            ['intelligence_outcomes.id', 'intelligence_outcomes.organization_id'],
            ondelete='CASCADE', name='fk_learning_candidates_outcome_id_organization_id',
        ),
        sa.ForeignKeyConstraint(
            ['verification_id', 'organization_id'],
            ['intelligence_outcome_verifications.id', 'intelligence_outcome_verifications.organization_id'],
            ondelete='CASCADE', name='fk_learning_candidates_verification_id_organization_id',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'outcome_id', name='uq_intelligence_learning_candidates_org_outcome'
        ),
        sa.UniqueConstraint(
            'id', 'organization_id', name='uq_intelligence_learning_candidates_id_organization_id'
        ),
    )
    op.create_index(
        op.f('ix_intelligence_learning_candidates_organization_id'), 'intelligence_learning_candidates',
        ['organization_id'], unique=False,
    )
    op.create_index(
        'ix_intelligence_learning_candidates_org_outcome', 'intelligence_learning_candidates',
        ['organization_id', 'outcome_id'], unique=False,
    )
    op.create_index(
        'ix_intelligence_learning_candidates_org_verification', 'intelligence_learning_candidates',
        ['organization_id', 'verification_id'], unique=False,
    )

    op.create_table(
        'intelligence_learning_candidate_governance_decisions',
        sa.Column('candidate_id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ACCEPTED', 'REJECTED', name='intelligence_learning_candidate_governance_status'),
            nullable=False,
        ),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('decided_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('decided_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['decided_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['candidate_id', 'organization_id'],
            ['intelligence_learning_candidates.id', 'intelligence_learning_candidates.organization_id'],
            ondelete='CASCADE', name='fk_learning_candidate_gov_decisions_candidate_id_org_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_intelligence_learning_candidate_governance_decisions_organization_id'),
        'intelligence_learning_candidate_governance_decisions', ['organization_id'], unique=False,
    )
    op.create_index(
        'ix_intelligence_learning_candidate_gov_decisions_org_candidate',
        'intelligence_learning_candidate_governance_decisions', ['organization_id', 'candidate_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_intelligence_learning_candidate_gov_decisions_org_candidate',
        table_name='intelligence_learning_candidate_governance_decisions',
    )
    op.drop_index(
        op.f('ix_intelligence_learning_candidate_governance_decisions_organization_id'),
        table_name='intelligence_learning_candidate_governance_decisions',
    )
    op.drop_table('intelligence_learning_candidate_governance_decisions')
    # Postgres drops the native enum type along with the table only when
    # no other table references it -- explicit drop mirrors migration
    # 0027's own downgrade() convention for its own native enum.
    sa.Enum(name='intelligence_learning_candidate_governance_status').drop(op.get_bind(), checkfirst=True)

    op.drop_index(
        'ix_intelligence_learning_candidates_org_verification', table_name='intelligence_learning_candidates'
    )
    op.drop_index(
        'ix_intelligence_learning_candidates_org_outcome', table_name='intelligence_learning_candidates'
    )
    op.drop_index(
        op.f('ix_intelligence_learning_candidates_organization_id'), table_name='intelligence_learning_candidates'
    )
    op.drop_table('intelligence_learning_candidates')

    op.drop_constraint(
        "uq_intelligence_outcome_verifications_id_organization_id",
        "intelligence_outcome_verifications",
        type_="unique",
    )
