"""Enterprise Data Ingestion & Validation Foundation v0.1

Revision ID: 0011
Revises: 0010
Create Date: 2026-09-01

Purely additive: two new tables (`enterprise_ingestion_batches`,
`enterprise_ingestion_records` — item 3's batch/record traceability
layer) plus nullable columns on two existing tables — `data_sources`
(`system_identifier`, `schema_version`, `config_metadata`,
`api_client_id`, reusing that model as the "ingestion source" concept —
see `app/models/data_source.py`'s own docstring for why) and
`safety_events` (`source_record_version`, `correlation_id`,
`source_schema_version`, `ingestion_source_id` — item 8's source-record
versioning and item 9's provenance chain). No existing table's data is
touched or reinterpreted, and no existing column changes type or
nullability.

As with every migration since 0007, `alembic revision --autogenerate`
also detected the same pre-existing, unrelated
`ix_knowledge_chunk_embeddings_model_identity` index drift (see
0007-0010's own docstrings) — stripped out here too, so this migration
stays purely additive to what it's actually about.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0011'
down_revision: Union[str, None] = '0010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'enterprise_ingestion_batches',
        sa.Column('source_id', sa.Uuid(), nullable=True),
        sa.Column('received_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('total_records', sa.Integer(), nullable=False),
        sa.Column('accepted_records', sa.Integer(), nullable=False),
        sa.Column('partial_records', sa.Integer(), nullable=False),
        sa.Column('quarantined_records', sa.Integer(), nullable=False),
        sa.Column('rejected_records', sa.Integer(), nullable=False),
        sa.Column('duplicate_records', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=True),
        sa.Column('error_summary', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['data_sources.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_enterprise_ingestion_batches_organization_id'), 'enterprise_ingestion_batches', ['organization_id'], unique=False)
    op.create_index(op.f('ix_enterprise_ingestion_batches_source_id'), 'enterprise_ingestion_batches', ['source_id'], unique=False)

    op.create_table(
        'enterprise_ingestion_records',
        sa.Column('batch_id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('external_record_id', sa.String(length=255), nullable=True),
        sa.Column('source_record_version', sa.String(length=50), nullable=True),
        sa.Column('correlation_id', sa.String(length=255), nullable=True),
        sa.Column('content_hash', sa.String(length=128), nullable=True),
        sa.Column('duplicate_in_batch', sa.Boolean(), nullable=False),
        sa.Column('outcome', sa.String(length=30), nullable=False),
        sa.Column('quality_state', sa.String(length=20), nullable=True),
        sa.Column('rejection_reason', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
        sa.Column('canonical_event_id', sa.Uuid(), nullable=True),
        sa.Column('payload', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['batch_id'], ['enterprise_ingestion_batches.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['canonical_event_id'], ['safety_events.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_enterprise_ingestion_records_batch_id'), 'enterprise_ingestion_records', ['batch_id'], unique=False)
    op.create_index(op.f('ix_enterprise_ingestion_records_canonical_event_id'), 'enterprise_ingestion_records', ['canonical_event_id'], unique=False)
    op.create_index(op.f('ix_enterprise_ingestion_records_organization_id'), 'enterprise_ingestion_records', ['organization_id'], unique=False)

    op.add_column('data_sources', sa.Column('system_identifier', sa.String(length=255), nullable=True))
    op.add_column('data_sources', sa.Column('schema_version', sa.String(length=20), nullable=True))
    op.add_column('data_sources', sa.Column('config_metadata', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False, server_default='{}'))
    op.alter_column('data_sources', 'config_metadata', server_default=None)
    op.add_column('data_sources', sa.Column('api_client_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_data_sources_api_client_id'), 'data_sources', ['api_client_id'], unique=False)
    op.create_foreign_key('fk_data_sources_api_client_id', 'data_sources', 'api_clients', ['api_client_id'], ['id'], ondelete='SET NULL')

    op.add_column('safety_events', sa.Column('source_record_version', sa.String(length=50), nullable=True))
    op.add_column('safety_events', sa.Column('correlation_id', sa.String(length=255), nullable=True))
    op.add_column('safety_events', sa.Column('source_schema_version', sa.String(length=20), nullable=True))
    op.add_column('safety_events', sa.Column('ingestion_source_id', sa.Uuid(), nullable=True))
    op.create_index(op.f('ix_safety_events_correlation_id'), 'safety_events', ['correlation_id'], unique=False)
    op.create_index(op.f('ix_safety_events_ingestion_source_id'), 'safety_events', ['ingestion_source_id'], unique=False)
    op.create_foreign_key('fk_safety_events_ingestion_source_id', 'safety_events', 'data_sources', ['ingestion_source_id'], ['id'], ondelete='SET NULL')


def downgrade() -> None:
    op.drop_constraint('fk_safety_events_ingestion_source_id', 'safety_events', type_='foreignkey')
    op.drop_index(op.f('ix_safety_events_ingestion_source_id'), table_name='safety_events')
    op.drop_index(op.f('ix_safety_events_correlation_id'), table_name='safety_events')
    op.drop_column('safety_events', 'ingestion_source_id')
    op.drop_column('safety_events', 'source_schema_version')
    op.drop_column('safety_events', 'correlation_id')
    op.drop_column('safety_events', 'source_record_version')

    op.drop_constraint('fk_data_sources_api_client_id', 'data_sources', type_='foreignkey')
    op.drop_index(op.f('ix_data_sources_api_client_id'), table_name='data_sources')
    op.drop_column('data_sources', 'api_client_id')
    op.drop_column('data_sources', 'config_metadata')
    op.drop_column('data_sources', 'schema_version')
    op.drop_column('data_sources', 'system_identifier')

    op.drop_index(op.f('ix_enterprise_ingestion_records_organization_id'), table_name='enterprise_ingestion_records')
    op.drop_index(op.f('ix_enterprise_ingestion_records_canonical_event_id'), table_name='enterprise_ingestion_records')
    op.drop_index(op.f('ix_enterprise_ingestion_records_batch_id'), table_name='enterprise_ingestion_records')
    op.drop_table('enterprise_ingestion_records')

    op.drop_index(op.f('ix_enterprise_ingestion_batches_source_id'), table_name='enterprise_ingestion_batches')
    op.drop_index(op.f('ix_enterprise_ingestion_batches_organization_id'), table_name='enterprise_ingestion_batches')
    op.drop_table('enterprise_ingestion_batches')
