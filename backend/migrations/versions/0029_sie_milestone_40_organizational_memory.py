"""SIE Milestone 40: Organizational Memory Architecture

Revision ID: 0029
Revises: 0028
Create Date: 2026-09-09

Establishes the durable, governed knowledge layer answering *"what does
this organization remember from verified operational experience?"* --
the missing link the loop has needed since SIE Milestone 39's
`IntelligenceLearningCandidate`. See
`app/models/organizational_memory.py`'s own docstring for the full
architectural rationale, and `docs/ORGANIZATIONAL_MEMORY_V0_1.md` for
the "what organizational memory is / is not" account.

Two new tables, both purely additive -- no existing table, column, row,
or type is altered or removed:

1. A new `organizational_memories` table, tenant-scoped, `ON DELETE
   CASCADE` on `organization_id`, with a composite foreign key
   `(learning_candidate_id, organization_id) ->
   intelligence_learning_candidates(id, organization_id)` (mirrors
   `intelligence_learning_candidates`' own SIE Milestone 39
   composite-FK hardening technique -- safe here because `ON DELETE
   CASCADE` applies, no `SET NULL` conflict). No new constraint is
   needed on `intelligence_learning_candidates` itself -- its own
   `UNIQUE(id, organization_id)` constraint already exists from
   migration 0028.
2. A new `organizational_memory_governance_decisions` table,
   tenant-scoped, `ON DELETE CASCADE` on `organization_id`, with a
   composite foreign key `(memory_id, organization_id) ->
   organizational_memories(id, organization_id)` -- the append-only
   ACTIVE/RETRACTED governance history for one memory. Requires
   `organizational_memories`' own `UNIQUE(id, organization_id)`
   constraint, added in this same migration.

No backfill: `OrganizationalMemory` and
`OrganizationalMemoryGovernanceDecision` are brand-new concepts with no
existing data to migrate.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0029'
down_revision: Union[str, None] = '0028'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'organizational_memories',
        sa.Column('learning_candidate_id', sa.Uuid(), nullable=False),
        sa.Column(
            'memory_type',
            sa.Enum(
                'LESSON_LEARNED', 'EFFECTIVE_PRACTICE', 'FAILED_APPROACH',
                'EARLY_WARNING_PATTERN', 'CONTROL_INSIGHT',
                name='organizational_memory_type',
            ),
            nullable=False,
        ),
        sa.Column('title', sa.String(length=200), nullable=False),
        sa.Column('memory_content', sa.Text(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
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
            ['learning_candidate_id', 'organization_id'],
            ['intelligence_learning_candidates.id', 'intelligence_learning_candidates.organization_id'],
            ondelete='CASCADE', name='fk_organizational_memories_candidate_id_organization_id',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'learning_candidate_id', name='uq_organizational_memories_org_candidate'
        ),
        sa.UniqueConstraint(
            'id', 'organization_id', name='uq_organizational_memories_id_organization_id'
        ),
    )
    op.create_index(
        op.f('ix_organizational_memories_organization_id'), 'organizational_memories',
        ['organization_id'], unique=False,
    )
    op.create_index(
        'ix_organizational_memories_org_candidate', 'organizational_memories',
        ['organization_id', 'learning_candidate_id'], unique=False,
    )
    op.create_index(
        'ix_organizational_memories_org_memory_type', 'organizational_memories',
        ['organization_id', 'memory_type'], unique=False,
    )

    op.create_table(
        'organizational_memory_governance_decisions',
        sa.Column('memory_id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'RETRACTED', name='organizational_memory_governance_status'),
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
            ['memory_id', 'organization_id'],
            ['organizational_memories.id', 'organizational_memories.organization_id'],
            ondelete='CASCADE', name='fk_organizational_memory_gov_decisions_memory_id_org_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_organizational_memory_governance_decisions_organization_id'),
        'organizational_memory_governance_decisions', ['organization_id'], unique=False,
    )
    op.create_index(
        'ix_organizational_memory_gov_decisions_org_memory',
        'organizational_memory_governance_decisions', ['organization_id', 'memory_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        'ix_organizational_memory_gov_decisions_org_memory',
        table_name='organizational_memory_governance_decisions',
    )
    op.drop_index(
        op.f('ix_organizational_memory_governance_decisions_organization_id'),
        table_name='organizational_memory_governance_decisions',
    )
    op.drop_table('organizational_memory_governance_decisions')
    # Postgres drops the native enum type along with the table only when
    # no other table references it -- explicit drop mirrors migration
    # 0028's own downgrade() convention for its own native enum.
    sa.Enum(name='organizational_memory_governance_status').drop(op.get_bind(), checkfirst=True)

    op.drop_index(
        'ix_organizational_memories_org_memory_type', table_name='organizational_memories'
    )
    op.drop_index(
        'ix_organizational_memories_org_candidate', table_name='organizational_memories'
    )
    op.drop_index(
        op.f('ix_organizational_memories_organization_id'), table_name='organizational_memories'
    )
    op.drop_table('organizational_memories')
    sa.Enum(name='organizational_memory_type').drop(op.get_bind(), checkfirst=True)
