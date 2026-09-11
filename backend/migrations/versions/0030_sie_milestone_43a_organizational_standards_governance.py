"""SIE Milestone 43A: Organizational Standards & Governance Foundation

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-11

Establishes the governance foundation letting SIE distinguish
available/selected/applicable standards and frameworks. See
`app/models/governing_standard.py`'s own docstring for the full
architectural rationale.

Two new tables, both purely additive -- no existing table, column, row,
or type is altered or removed:

1. A new `governing_standards` table -- the catalogue ("available"),
   GLOBAL or ORGANIZATION-scoped exactly like `knowledge_sources`
   (its own, distinctly-named, native enum types -- not a reuse of
   `knowledge_scope_type`/`knowledge_verification_status`, to keep this
   migration fully independent of the knowledge_sources table's own
   type lifecycle).
2. A new `organization_governing_standards` table -- the append-only
   SELECTED/RETIRED selection event log ("selected"), tenant-scoped,
   `ON DELETE CASCADE` on `organization_id`.

No backfill: both are brand-new concepts with no existing data to
migrate. No GLOBAL catalogue rows are seeded by this migration itself --
see `app/services/governing_standard_service.py::seed_global_catalogue()`
for the idempotent, separately-invoked seed helper.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0030'
down_revision: Union[str, None] = '0029'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'governing_standards',
        sa.Column(
            'scope_type',
            sa.Enum('GLOBAL', 'ORGANIZATION', name='governing_standard_scope_type'),
            nullable=False,
        ),
        sa.Column('organization_id', sa.Uuid(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('short_description', sa.Text(), nullable=False),
        sa.Column('issuing_organization', sa.String(length=255), nullable=False),
        sa.Column(
            'standard_type',
            sa.Enum(
                'REGULATORY', 'INTERNATIONAL_STANDARD', 'INDUSTRY_GUIDANCE',
                'MANAGEMENT_FRAMEWORK', 'CLIENT_STANDARD', 'ORGANIZATION_SPECIFIC', 'OTHER',
                name='governing_standard_type',
            ),
            nullable=False,
        ),
        sa.Column('regions', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('industry_sectors', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('version', sa.String(length=100), nullable=True),
        sa.Column('publication_date', sa.Date(), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column(
            'verification_status',
            sa.Enum(
                'PENDING', 'UNDER_REVIEW', 'VERIFIED', 'REJECTED', 'EXPIRED', 'SUPERSEDED',
                name='governing_standard_verification_status',
            ),
            nullable=False,
        ),
        sa.Column('knowledge_source_id', sa.Uuid(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('created_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['knowledge_source_id'], ['knowledge_sources.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.CheckConstraint(
            "(scope_type = 'GLOBAL' AND organization_id IS NULL) OR "
            "(scope_type = 'ORGANIZATION' AND organization_id IS NOT NULL)",
            name='ck_governing_standards_scope_org_consistency',
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('id', 'organization_id', name='uq_governing_standards_id_organization_id'),
    )
    op.create_index(
        op.f('ix_governing_standards_organization_id'), 'governing_standards', ['organization_id'], unique=False,
    )
    op.create_index(
        op.f('ix_governing_standards_name'), 'governing_standards', ['name'], unique=False,
    )
    op.create_index(
        'ix_governing_standards_scope_type', 'governing_standards', ['scope_type'], unique=False,
    )
    op.create_index(
        'ix_governing_standards_standard_type', 'governing_standards', ['standard_type'], unique=False,
    )
    op.create_index(
        'ix_governing_standards_is_active', 'governing_standards', ['is_active'], unique=False,
    )

    op.create_table(
        'organization_governing_standards',
        sa.Column('standard_id', sa.Uuid(), nullable=False),
        sa.Column(
            'status',
            sa.Enum('SELECTED', 'RETIRED', name='organization_governing_standard_status'),
            nullable=False,
        ),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column('retirement_date', sa.Date(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('configured_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('configured_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['standard_id'], ['governing_standards.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['configured_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['configured_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_organization_governing_standards_organization_id'),
        'organization_governing_standards', ['organization_id'], unique=False,
    )
    op.create_index(
        'ix_org_governing_standards_org_standard',
        'organization_governing_standards', ['organization_id', 'standard_id'], unique=False,
    )
    op.create_index(
        'ix_org_governing_standards_org_status',
        'organization_governing_standards', ['organization_id', 'status'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_org_governing_standards_org_status', table_name='organization_governing_standards')
    op.drop_index('ix_org_governing_standards_org_standard', table_name='organization_governing_standards')
    op.drop_index(
        op.f('ix_organization_governing_standards_organization_id'),
        table_name='organization_governing_standards',
    )
    op.drop_table('organization_governing_standards')
    sa.Enum(name='organization_governing_standard_status').drop(op.get_bind(), checkfirst=True)

    op.drop_index('ix_governing_standards_is_active', table_name='governing_standards')
    op.drop_index('ix_governing_standards_standard_type', table_name='governing_standards')
    op.drop_index('ix_governing_standards_scope_type', table_name='governing_standards')
    op.drop_index(op.f('ix_governing_standards_name'), table_name='governing_standards')
    op.drop_index(op.f('ix_governing_standards_organization_id'), table_name='governing_standards')
    op.drop_table('governing_standards')
    sa.Enum(name='governing_standard_verification_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='governing_standard_type').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='governing_standard_scope_type').drop(op.get_bind(), checkfirst=True)
