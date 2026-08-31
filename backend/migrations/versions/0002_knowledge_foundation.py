"""knowledge foundation

Revision ID: 0002
Revises: 0001
Create Date: 2026-08-31 16:43:56.787146

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0002'
down_revision: Union[str, None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'knowledge_sources',
        sa.Column(
            'scope_type',
            sa.Enum('GLOBAL', 'ORGANIZATION', name='knowledge_scope_type'),
            nullable=False,
        ),
        sa.Column('organization_id', sa.Uuid(), nullable=True),
        sa.Column('publisher', sa.String(length=255), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=100), nullable=False),
        sa.Column('jurisdiction', sa.String(length=100), nullable=True),
        sa.Column('industry_sector', sa.String(length=100), nullable=True),
        sa.Column('authority_level', sa.String(length=100), nullable=True),
        sa.Column(
            'verification_status',
            sa.Enum(
                'PENDING',
                'UNDER_REVIEW',
                'VERIFIED',
                'REJECTED',
                'EXPIRED',
                'SUPERSEDED',
                name='knowledge_verification_status',
            ),
            nullable=False,
        ),
        sa.Column('external_reference', sa.Text(), nullable=True),
        sa.Column('publication_date', sa.Date(), nullable=True),
        sa.Column('review_date', sa.Date(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(scope_type = 'GLOBAL' AND organization_id IS NULL) OR "
            "(scope_type = 'ORGANIZATION' AND organization_id IS NOT NULL)",
            name='ck_knowledge_sources_scope_org_consistency',
        ),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_knowledge_sources_name'), 'knowledge_sources', ['name'], unique=False)
    op.create_index(
        op.f('ix_knowledge_sources_organization_id'),
        'knowledge_sources',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        'ix_knowledge_sources_scope_type', 'knowledge_sources', ['scope_type'], unique=False
    )
    op.create_index(
        'ix_knowledge_sources_verification_status',
        'knowledge_sources',
        ['verification_status'],
        unique=False,
    )

    # `current_version_id` is added as a plain column here, with its foreign
    # key to knowledge_document_versions added via a separate
    # op.create_foreign_key() below, once that table exists. The two tables
    # reference each other (documents -> its current version, versions ->
    # their document), so this table can't carry both FKs inline in a single
    # CREATE TABLE statement without one of them pointing at a table that
    # doesn't exist yet.
    op.create_table(
        'knowledge_documents',
        sa.Column('source_id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=True),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('document_type', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('language', sa.String(length=20), nullable=True),
        sa.Column('external_document_id', sa.String(length=255), nullable=True),
        sa.Column('current_version_id', sa.Uuid(), nullable=True),
        sa.Column('status', sa.String(length=50), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['knowledge_sources.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'ix_knowledge_documents_organization_id',
        'knowledge_documents',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_documents_source_id'), 'knowledge_documents', ['source_id'], unique=False
    )
    op.create_index(
        op.f('ix_knowledge_documents_title'), 'knowledge_documents', ['title'], unique=False
    )

    op.create_table(
        'knowledge_document_versions',
        sa.Column('document_id', sa.Uuid(), nullable=False),
        sa.Column('version_label', sa.String(length=100), nullable=False),
        sa.Column('content_hash', sa.String(length=128), nullable=False),
        sa.Column('storage_reference', sa.String(length=1000), nullable=False),
        sa.Column('extracted_text', sa.Text(), nullable=True),
        sa.Column('publication_date', sa.Date(), nullable=True),
        sa.Column('effective_date', sa.Date(), nullable=True),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            'ingestion_status',
            sa.Enum(
                'RECEIVED',
                'PROCESSING',
                'PROCESSED',
                'FAILED',
                'ARCHIVED',
                name='knowledge_ingestion_status',
            ),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['document_id'], ['knowledge_documents.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'document_id', 'content_hash', name='uq_knowledge_document_versions_document_content'
        ),
    )
    op.create_index(
        op.f('ix_knowledge_document_versions_content_hash'),
        'knowledge_document_versions',
        ['content_hash'],
        unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_document_versions_document_id'),
        'knowledge_document_versions',
        ['document_id'],
        unique=False,
    )

    # Now that knowledge_document_versions exists, add the deferred FK from
    # knowledge_documents.current_version_id. batch_alter_table is used
    # (rather than a bare op.create_foreign_key) because SQLite cannot ALTER
    # a table to add a constraint directly; batch mode handles that via its
    # copy-and-move strategy there while compiling to a plain ALTER TABLE ADD
    # CONSTRAINT on PostgreSQL.
    with op.batch_alter_table('knowledge_documents') as batch_op:
        batch_op.create_foreign_key(
            'fk_knowledge_documents_current_version_id',
            'knowledge_document_versions',
            ['current_version_id'],
            ['id'],
            ondelete='SET NULL',
        )

    op.create_table(
        'knowledge_chunks',
        sa.Column('document_version_id', sa.Uuid(), nullable=False),
        sa.Column('chunk_index', sa.Integer(), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('character_count', sa.Integer(), nullable=False),
        sa.Column('page_number', sa.Integer(), nullable=True),
        sa.Column('section_title', sa.String(length=500), nullable=True),
        sa.Column(
            'metadata',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ['document_version_id'], ['knowledge_document_versions.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'document_version_id', 'chunk_index', name='uq_knowledge_chunks_version_index'
        ),
    )
    op.create_index(
        op.f('ix_knowledge_chunks_document_version_id'),
        'knowledge_chunks',
        ['document_version_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_knowledge_chunks_document_version_id'), table_name='knowledge_chunks'
    )
    op.drop_table('knowledge_chunks')

    with op.batch_alter_table('knowledge_documents') as batch_op:
        batch_op.drop_constraint(
            'fk_knowledge_documents_current_version_id', type_='foreignkey'
        )

    op.drop_index(
        op.f('ix_knowledge_document_versions_document_id'),
        table_name='knowledge_document_versions',
    )
    op.drop_index(
        op.f('ix_knowledge_document_versions_content_hash'),
        table_name='knowledge_document_versions',
    )
    op.drop_table('knowledge_document_versions')

    op.drop_index(op.f('ix_knowledge_documents_title'), table_name='knowledge_documents')
    op.drop_index(op.f('ix_knowledge_documents_source_id'), table_name='knowledge_documents')
    op.drop_index('ix_knowledge_documents_organization_id', table_name='knowledge_documents')
    op.drop_table('knowledge_documents')

    op.drop_index('ix_knowledge_sources_verification_status', table_name='knowledge_sources')
    op.drop_index('ix_knowledge_sources_scope_type', table_name='knowledge_sources')
    op.drop_index(op.f('ix_knowledge_sources_organization_id'), table_name='knowledge_sources')
    op.drop_index(op.f('ix_knowledge_sources_name'), table_name='knowledge_sources')
    op.drop_table('knowledge_sources')

    # Native enum types created by the sa.Enum columns above are dropped
    # automatically by op.drop_table() on PostgreSQL only if unused
    # elsewhere; drop them explicitly for a clean downgrade.
    sa.Enum(name='knowledge_ingestion_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='knowledge_verification_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='knowledge_scope_type').drop(op.get_bind(), checkfirst=True)
