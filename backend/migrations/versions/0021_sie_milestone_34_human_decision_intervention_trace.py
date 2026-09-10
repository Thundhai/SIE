"""SIE Milestone 34: Human Decision & Intervention Trace

Revision ID: 0021
Revises: 0020
Create Date: 2026-09-08

Purely additive: exactly one new table, `intelligence_decisions`, plus
its one new native enum type, `intelligence_decision_type`. No existing
table, column, row, or type value is altered or removed. See
`app/models/intelligence_decision.py` for the full design rationale.

This is the first durable write in the SIE intelligence workflow
(M30-M33 were architecture/read-only, M32/M33 remain unchanged by this
migration). Deliberately narrow, per the milestone's own "database
discipline" instruction: no intelligence snapshot table, no duplicated
event/action table, no `FieldState`, no outcome/learning table -- one
governed record of a human decision, referencing `organizations`,
`sites`, `safety_actions`, `users`, and `api_clients` by foreign key,
never duplicating their data.

The new `decision` column's native enum type is introduced via
`op.create_table()`, which auto-creates the enum type as part of the
table DDL -- exactly like every earlier native-enum column first
introduced alongside its own table in this schema (see migration 0015's
own docstring for why this is safe despite migration 0005's
enum-type-creation defect, which only affects `op.add_column()` onto an
*existing* table). No separate, explicit `sa.Enum(...).create()` call is
needed or made here -- doing so as well would emit a redundant `CREATE
TYPE` for the same type.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0021'
down_revision: Union[str, None] = '0020'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_DECISION_TYPE_VALUES = ('ACT', 'DO_NOT_ACT', 'DEFER', 'ALREADY_ADDRESSED', 'NOT_RELEVANT')


def upgrade() -> None:
    op.create_table(
        'intelligence_decisions',
        sa.Column('site_id', sa.Uuid(), nullable=True),
        sa.Column('scope', sa.String(length=20), nullable=False),
        sa.Column('attention_reference', sa.String(length=500), nullable=False),
        sa.Column('attention_category', sa.String(length=50), nullable=False),
        sa.Column('attention_priority', sa.String(length=20), nullable=False),
        sa.Column('attention_title', sa.String(length=255), nullable=False),
        sa.Column('attention_explanation', sa.Text(), nullable=False),
        sa.Column('intelligence_as_of', sa.DateTime(timezone=True), nullable=False),
        sa.Column('intelligence_window_days', sa.Integer(), nullable=False),
        sa.Column('calculation_version', sa.String(length=50), nullable=True),
        sa.Column('evidence_source', sa.String(length=50), nullable=True),
        sa.Column(
            'evidence_entity_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column(
            'evidence_event_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column('decision', sa.Enum(*_DECISION_TYPE_VALUES, name='intelligence_decision_type'), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('linked_action_id', sa.Uuid(), nullable=True),
        sa.Column('decided_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('decided_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['linked_action_id'], ['safety_actions.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['decided_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['decided_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_intelligence_decisions_organization_id'), 'intelligence_decisions', ['organization_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_intelligence_decisions_site_id'), 'intelligence_decisions', ['site_id'], unique=False,
    )
    op.create_index(
        'ix_intelligence_decisions_org_attention_ref', 'intelligence_decisions',
        ['organization_id', 'attention_reference'], unique=False,
    )
    op.create_index(
        'ix_intelligence_decisions_org_site', 'intelligence_decisions', ['organization_id', 'site_id'],
        unique=False,
    )
    op.create_index(
        'ix_intelligence_decisions_org_decided_at', 'intelligence_decisions', ['organization_id', 'decided_at'],
        unique=False,
    )
    op.create_index(
        'ix_intelligence_decisions_org_linked_action', 'intelligence_decisions',
        ['organization_id', 'linked_action_id'], unique=False,
    )


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index('ix_intelligence_decisions_org_linked_action', table_name='intelligence_decisions')
    op.drop_index('ix_intelligence_decisions_org_decided_at', table_name='intelligence_decisions')
    op.drop_index('ix_intelligence_decisions_org_site', table_name='intelligence_decisions')
    op.drop_index('ix_intelligence_decisions_org_attention_ref', table_name='intelligence_decisions')
    op.drop_index(op.f('ix_intelligence_decisions_site_id'), table_name='intelligence_decisions')
    op.drop_index(op.f('ix_intelligence_decisions_organization_id'), table_name='intelligence_decisions')
    op.drop_table('intelligence_decisions')

    sa.Enum(name='intelligence_decision_type').drop(bind, checkfirst=True)
