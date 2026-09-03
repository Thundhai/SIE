"""SIE Milestone 17: Actions & Intervention Foundation v0.1

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-03

Purely additive: two new tables. `safety_actions` (see
`app/models/safety_action.py`'s own docstring) — the first persisted
Actions/Intervention domain record, tenant-scoped, with nullable
`site_id`/`source_event_id`/`owner_user_id` foreign keys (each validated
at the application layer, not just the schema, to belong to the same
organization — see `app/services/safety_action_service.py`), and a
native-PostgreSQL-enum `status`/`priority`/`action_type` (see
`app/models/safety_action_enums.py`'s own docstring for why this is
safe here despite migration 0005's enum-type-creation defect: every
enum column here is introduced via `op.create_table()`, which auto-
creates the enum type, exactly like every earlier native-enum column in
this schema). `safety_action_history` (see
`app/models/safety_action_history.py`) — an immutable, tenant-scoped
per-action audit trail, distinct from the existing platform-wide
`audit_logs` table.

No existing table's data, columns, or types are touched; migration 0014
is not modified.

As with every migration since 0007, `alembic revision --autogenerate`
also detected the same pre-existing, unrelated
`ix_knowledge_chunk_embeddings_model_identity` index drift (see
0007-0014's own docstrings) — stripped out here too, so this migration
stays purely additive to what it's actually about.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0015'
down_revision: Union[str, None] = '0014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'safety_actions',
        sa.Column('site_id', sa.Uuid(), nullable=True),
        sa.Column('source_event_id', sa.Uuid(), nullable=True),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column(
            'action_type',
            sa.Enum(
                'CORRECTIVE', 'PREVENTIVE', 'INVESTIGATION', 'FOLLOW_UP', 'CONTROL_IMPROVEMENT', 'OTHER',
                name='safety_action_type',
            ),
            nullable=False,
        ),
        sa.Column(
            'priority',
            sa.Enum('LOW', 'MEDIUM', 'HIGH', 'CRITICAL', name='safety_action_priority'),
            nullable=False,
        ),
        sa.Column(
            'status',
            sa.Enum('OPEN', 'IN_PROGRESS', 'BLOCKED', 'COMPLETED', 'CANCELLED', name='safety_action_status'),
            nullable=False,
        ),
        sa.Column('owner_user_id', sa.Uuid(), nullable=True),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('created_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('cancelled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('external_reference', sa.String(length=255), nullable=True),
        sa.Column(
            'attributes',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=False,
        ),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['created_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['owner_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['source_event_id'], ['safety_events.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_safety_actions_due_date', 'safety_actions', ['due_date'], unique=False)
    op.create_index('ix_safety_actions_org_owner', 'safety_actions', ['organization_id', 'owner_user_id'], unique=False)
    op.create_index('ix_safety_actions_org_priority', 'safety_actions', ['organization_id', 'priority'], unique=False)
    op.create_index('ix_safety_actions_org_site', 'safety_actions', ['organization_id', 'site_id'], unique=False)
    op.create_index(
        'ix_safety_actions_org_source_event', 'safety_actions', ['organization_id', 'source_event_id'], unique=False
    )
    op.create_index('ix_safety_actions_org_status', 'safety_actions', ['organization_id', 'status'], unique=False)
    op.create_index(op.f('ix_safety_actions_organization_id'), 'safety_actions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_safety_actions_owner_user_id'), 'safety_actions', ['owner_user_id'], unique=False)
    op.create_index(op.f('ix_safety_actions_site_id'), 'safety_actions', ['site_id'], unique=False)
    op.create_index(op.f('ix_safety_actions_source_event_id'), 'safety_actions', ['source_event_id'], unique=False)
    op.create_index(op.f('ix_safety_actions_status'), 'safety_actions', ['status'], unique=False)

    op.create_table(
        'safety_action_history',
        sa.Column('action_id', sa.Uuid(), nullable=False),
        sa.Column('change_type', sa.String(length=50), nullable=False),
        sa.Column('from_status', sa.String(length=20), nullable=True),
        sa.Column('to_status', sa.String(length=20), nullable=True),
        sa.Column('changed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('changed_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['action_id'], ['safety_actions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_safety_action_history_action_id'), 'safety_action_history', ['action_id'], unique=False)
    op.create_index(
        op.f('ix_safety_action_history_organization_id'), 'safety_action_history', ['organization_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_safety_action_history_organization_id'), table_name='safety_action_history')
    op.drop_index(op.f('ix_safety_action_history_action_id'), table_name='safety_action_history')
    op.drop_table('safety_action_history')
    op.drop_index(op.f('ix_safety_actions_status'), table_name='safety_actions')
    op.drop_index(op.f('ix_safety_actions_source_event_id'), table_name='safety_actions')
    op.drop_index(op.f('ix_safety_actions_site_id'), table_name='safety_actions')
    op.drop_index(op.f('ix_safety_actions_owner_user_id'), table_name='safety_actions')
    op.drop_index(op.f('ix_safety_actions_organization_id'), table_name='safety_actions')
    op.drop_index('ix_safety_actions_org_status', table_name='safety_actions')
    op.drop_index('ix_safety_actions_org_source_event', table_name='safety_actions')
    op.drop_index('ix_safety_actions_org_site', table_name='safety_actions')
    op.drop_index('ix_safety_actions_org_priority', table_name='safety_actions')
    op.drop_index('ix_safety_actions_org_owner', table_name='safety_actions')
    op.drop_index('ix_safety_actions_due_date', table_name='safety_actions')
    op.drop_table('safety_actions')

    # Native enum types created by the sa.Enum columns above are dropped
    # automatically by op.drop_table() on PostgreSQL only if unused
    # elsewhere; drop them explicitly for a clean downgrade -- exactly
    # migration 0002's own precedent for knowledge_scope_type/
    # knowledge_verification_status.
    sa.Enum(name='safety_action_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='safety_action_priority').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='safety_action_type').drop(op.get_bind(), checkfirst=True)
