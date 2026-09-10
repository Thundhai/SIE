"""SIE Milestone 37: Field Outcome Foundation

Revision ID: 0026
Revises: 0025
Create Date: 2026-09-09

Adds the first durable record of *what happened after* a human
decision/intervention -- the missing link the loop has needed since SIE
Milestone 34's `IntelligenceDecision`. See
`app/models/intelligence_outcome.py`'s own docstring for the full
architectural rationale, and `docs/FIELD_OUTCOME_FOUNDATION_V0_1.md` for
the "what an outcome is / is not" account.

Two changes, both purely additive -- no existing table, column, row, or
type is altered or removed:

1. `intelligence_decisions` gains a `UNIQUE(id, organization_id)`
   constraint -- identical precedent to `sites`/`projects`' own SIE
   Milestone 35A constraint (migration 0023) -- so a genuine, DB-
   enforced composite foreign key can reference it from the new table
   below.
2. A new `intelligence_outcomes` table, tenant-scoped, `ON DELETE
   CASCADE` on `organization_id`, with a composite foreign key
   `(decision_id, organization_id) -> intelligence_decisions(id,
   organization_id)` (mirrors `project_sites`'/`project_site_history`'s
   own SIE Milestone 35A/36 composite-FK hardening technique -- safe
   here because `ON DELETE CASCADE` applies, no `SET NULL` conflict).
   `linked_action_id`/`site_id` are deliberately plain, single-column
   foreign keys (`ON DELETE SET NULL`) -- the identical
   `IntelligenceDecision.linked_action_id` precedent already documents
   why a composite FK cannot be combined with `SET NULL` when
   `organization_id` is `NOT NULL`.

No backfill: `IntelligenceOutcome` is a brand-new concept with no
existing data to migrate.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0026'
down_revision: Union[str, None] = '0025'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_intelligence_decisions_id_organization_id", "intelligence_decisions", ["id", "organization_id"]
    )

    op.create_table(
        'intelligence_outcomes',
        sa.Column('decision_id', sa.Uuid(), nullable=False),
        sa.Column('site_id', sa.Uuid(), nullable=True),
        sa.Column('linked_action_id', sa.Uuid(), nullable=True),
        sa.Column(
            'classification',
            sa.Enum(
                'EFFECTIVE', 'PARTIALLY_EFFECTIVE', 'INEFFECTIVE', 'NO_OUTCOME_RECORDED',
                name='intelligence_outcome_classification',
            ),
            nullable=False,
        ),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column(
            'evidence_event_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column('outcome_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('recorded_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('recorded_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['linked_action_id'], ['safety_actions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['recorded_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['recorded_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['decision_id', 'organization_id'],
            ['intelligence_decisions.id', 'intelligence_decisions.organization_id'],
            ondelete='CASCADE', name='fk_intelligence_outcomes_decision_id_organization_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_intelligence_outcomes_organization_id'), 'intelligence_outcomes', ['organization_id'], unique=False
    )
    op.create_index(
        'ix_intelligence_outcomes_org_decision', 'intelligence_outcomes', ['organization_id', 'decision_id'],
        unique=False,
    )
    op.create_index(
        'ix_intelligence_outcomes_org_action', 'intelligence_outcomes', ['organization_id', 'linked_action_id'],
        unique=False,
    )
    op.create_index(
        'ix_intelligence_outcomes_org_site', 'intelligence_outcomes', ['organization_id', 'site_id'], unique=False,
    )
    op.create_index(
        'ix_intelligence_outcomes_org_outcome_at', 'intelligence_outcomes', ['organization_id', 'outcome_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_intelligence_outcomes_org_outcome_at', table_name='intelligence_outcomes')
    op.drop_index('ix_intelligence_outcomes_org_site', table_name='intelligence_outcomes')
    op.drop_index('ix_intelligence_outcomes_org_action', table_name='intelligence_outcomes')
    op.drop_index('ix_intelligence_outcomes_org_decision', table_name='intelligence_outcomes')
    op.drop_index(op.f('ix_intelligence_outcomes_organization_id'), table_name='intelligence_outcomes')
    op.drop_table('intelligence_outcomes')
    # Postgres drops the native enum type along with the table only when
    # no other table references it -- explicit drop mirrors migration
    # 0021's own downgrade() convention for its own native enum.
    sa.Enum(name='intelligence_outcome_classification').drop(op.get_bind(), checkfirst=True)

    op.drop_constraint(
        "uq_intelligence_decisions_id_organization_id", "intelligence_decisions", type_="unique"
    )
