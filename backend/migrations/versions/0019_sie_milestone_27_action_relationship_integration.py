"""SIE Milestone 27: Risk Assessment & Action Management Integration v0.1

Revision ID: 0019
Revises: 0018
Create Date: 2026-09-07

Purely additive: one new table, `risk_assessment_finding_actions`,
backfilled from every pre-existing non-NULL
`risk_assessment_findings.linked_action_id` (SIE Milestone 26) so the new
relationship table is a complete, correct record of "which actions are
linked to which findings" immediately upon upgrade -- not just for rows
created afterward. Nothing else in the schema changes: `linked_action_id`
itself is untouched (kept for backward compatibility, see
`app/models/risk_assessment_finding_action.py`'s own docstring for the
full rationale), and `safety_actions` gains no new column -- a
`SafetyAction`'s origin (which finding it was created from, if any) is
recorded in its own existing `attributes` JSON column instead
(`app/api/v1/risk_assessments.py::create_finding_action()`), the exact
"don't force a migration for every new field" extension point that
column's own docstring already documents.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0019'
down_revision: Union[str, None] = '0018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        'risk_assessment_finding_actions',
        sa.Column('finding_id', sa.Uuid(), nullable=False),
        sa.Column('action_id', sa.Uuid(), nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('created_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['action_id'], ['safety_actions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['finding_id'], ['risk_assessment_findings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('finding_id', 'action_id', name='uq_risk_assessment_finding_actions_finding_action'),
    )
    op.create_index(
        'ix_risk_assessment_finding_actions_finding', 'risk_assessment_finding_actions', ['finding_id'], unique=False
    )
    op.create_index(
        'ix_risk_assessment_finding_actions_action', 'risk_assessment_finding_actions', ['action_id'], unique=False
    )
    op.create_index(
        op.f('ix_risk_assessment_finding_actions_organization_id'), 'risk_assessment_finding_actions',
        ['organization_id'], unique=False,
    )

    # Backfill: one relationship row per pre-existing non-NULL
    # linked_action_id -- SIE Milestone 26 data preserved, never dropped.
    bind.execute(
        sa.text(
            "INSERT INTO risk_assessment_finding_actions "
            "(id, organization_id, finding_id, action_id, created_at, updated_at) "
            "SELECT gen_random_uuid(), organization_id, id, linked_action_id, updated_at, updated_at "
            "FROM risk_assessment_findings WHERE linked_action_id IS NOT NULL"
        )
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_risk_assessment_finding_actions_organization_id'), table_name='risk_assessment_finding_actions'
    )
    op.drop_index('ix_risk_assessment_finding_actions_action', table_name='risk_assessment_finding_actions')
    op.drop_index('ix_risk_assessment_finding_actions_finding', table_name='risk_assessment_finding_actions')
    op.drop_table('risk_assessment_finding_actions')
