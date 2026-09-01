"""Predictive Model Validation & Governance v0.1

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-01

Purely additive — four new tables (`dataset_versions`, `model_approvals`,
`model_review_flags`, `prediction_outcomes`) plus one new nullable,
indexed foreign-key column on the existing `model_registry_entries`
table (`dataset_version_id`, `ON DELETE SET NULL`). No existing table's
data is touched or reinterpreted.

As with every migration since 0007, `alembic revision --autogenerate`
also detected the same pre-existing, unrelated
`ix_knowledge_chunk_embeddings_model_identity` index drift (see 0007/0008's
own docstrings) — stripped out here too, so this migration stays purely
additive to what it's actually about.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0009'
down_revision: Union[str, None] = '0008'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'dataset_versions',
        sa.Column('dataset_id', sa.String(length=100), nullable=False),
        sa.Column('dataset_version', sa.String(length=20), nullable=False),
        sa.Column('environment', sa.String(length=20), nullable=False),
        sa.Column('source_systems', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('date_range_start', sa.Date(), nullable=False),
        sa.Column('date_range_end', sa.Date(), nullable=False),
        sa.Column('feature_set_version', sa.String(length=30), nullable=False),
        sa.Column('target_version', sa.String(length=30), nullable=False),
        sa.Column('prediction_horizon_days', sa.Integer(), nullable=False),
        sa.Column('entity_type', sa.String(length=50), nullable=False),
        sa.Column('entity_count', sa.Integer(), nullable=False),
        sa.Column('record_count', sa.Integer(), nullable=False),
        sa.Column('quality_report', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('organization_id', 'dataset_id', 'dataset_version', name='uq_dataset_versions_id_version'),
    )
    op.create_index(op.f('ix_dataset_versions_dataset_id'), 'dataset_versions', ['dataset_id'], unique=False)
    op.create_index(op.f('ix_dataset_versions_environment'), 'dataset_versions', ['environment'], unique=False)
    op.create_index(op.f('ix_dataset_versions_organization_id'), 'dataset_versions', ['organization_id'], unique=False)

    op.create_table(
        'model_approvals',
        sa.Column('model_id', sa.Uuid(), nullable=False),
        sa.Column('model_version', sa.String(length=20), nullable=False),
        sa.Column('reviewer_user_id', sa.Uuid(), nullable=False),
        sa.Column('decision', sa.String(length=20), nullable=False),
        sa.Column('notes', sa.String(length=2000), nullable=True),
        sa.Column('validation_report', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['model_id'], ['model_registry_entries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_model_approvals_model_id'), 'model_approvals', ['model_id'], unique=False)
    op.create_index(op.f('ix_model_approvals_organization_id'), 'model_approvals', ['organization_id'], unique=False)

    op.create_table(
        'model_review_flags',
        sa.Column('model_id', sa.Uuid(), nullable=False),
        sa.Column('reason', sa.String(length=50), nullable=False),
        sa.Column('metric_name', sa.String(length=50), nullable=False),
        sa.Column('historical_value', sa.Float(), nullable=True),
        sa.Column('current_value', sa.Float(), nullable=True),
        sa.Column('detail', sa.String(length=2000), nullable=True),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('flagged_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('acknowledged_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('acknowledged_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['acknowledged_by_user_id'], ['users.id']),
        sa.ForeignKeyConstraint(['model_id'], ['model_registry_entries.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_model_review_flags_model_id'), 'model_review_flags', ['model_id'], unique=False)
    op.create_index(op.f('ix_model_review_flags_organization_id'), 'model_review_flags', ['organization_id'], unique=False)

    op.create_table(
        'prediction_outcomes',
        sa.Column('prediction_id', sa.Uuid(), nullable=False),
        sa.Column('outcome_known', sa.Boolean(), nullable=False),
        sa.Column('actual_label', sa.Integer(), nullable=True),
        sa.Column('outcome_event_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_prediction_outcomes_organization_id'), 'prediction_outcomes', ['organization_id'], unique=False)
    op.create_index(op.f('ix_prediction_outcomes_prediction_id'), 'prediction_outcomes', ['prediction_id'], unique=True)

    op.add_column('model_registry_entries', sa.Column('dataset_version_id', sa.Uuid(), nullable=True))
    op.create_index(
        op.f('ix_model_registry_entries_dataset_version_id'), 'model_registry_entries', ['dataset_version_id'], unique=False
    )
    op.create_foreign_key(
        'fk_model_registry_entries_dataset_version_id',
        'model_registry_entries', 'dataset_versions', ['dataset_version_id'], ['id'], ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_model_registry_entries_dataset_version_id', 'model_registry_entries', type_='foreignkey')
    op.drop_index(op.f('ix_model_registry_entries_dataset_version_id'), table_name='model_registry_entries')
    op.drop_column('model_registry_entries', 'dataset_version_id')

    op.drop_index(op.f('ix_prediction_outcomes_prediction_id'), table_name='prediction_outcomes')
    op.drop_index(op.f('ix_prediction_outcomes_organization_id'), table_name='prediction_outcomes')
    op.drop_table('prediction_outcomes')

    op.drop_index(op.f('ix_model_review_flags_organization_id'), table_name='model_review_flags')
    op.drop_index(op.f('ix_model_review_flags_model_id'), table_name='model_review_flags')
    op.drop_table('model_review_flags')

    op.drop_index(op.f('ix_model_approvals_organization_id'), table_name='model_approvals')
    op.drop_index(op.f('ix_model_approvals_model_id'), table_name='model_approvals')
    op.drop_table('model_approvals')

    op.drop_index(op.f('ix_dataset_versions_organization_id'), table_name='dataset_versions')
    op.drop_index(op.f('ix_dataset_versions_environment'), table_name='dataset_versions')
    op.drop_index(op.f('ix_dataset_versions_dataset_id'), table_name='dataset_versions')
    op.drop_table('dataset_versions')
