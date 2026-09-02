"""Real Enterprise Terminology & Ontology Calibration v0.1

Revision ID: 0013
Revises: 0012
Create Date: 2026-09-02

Purely additive: one new table, `terminology_mapping_decisions` (item 3's
persisted, versioned, auditable terminology-mapping decision record —
see `app/models/terminology_mapping_decision.py`'s own docstring for the
full lifecycle and scoping rationale). No existing table's data, columns,
or types are touched.

As with every migration since 0007, `alembic revision --autogenerate`
also detected the same pre-existing, unrelated
`ix_knowledge_chunk_embeddings_model_identity` index drift (see
0007-0012's own docstrings) — stripped out here too, so this migration
stays purely additive to what it's actually about.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0013'
down_revision: Union[str, None] = '0012'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'terminology_mapping_decisions',
        sa.Column('source_system', sa.String(length=100), nullable=False),
        sa.Column('domain', sa.String(length=30), nullable=False),
        sa.Column('context', sa.String(length=100), nullable=True),
        sa.Column('source_term', sa.String(length=255), nullable=False),
        sa.Column('normalized_term', sa.String(length=255), nullable=False),
        sa.Column('mapping_version', sa.Integer(), nullable=False),
        sa.Column('superseded_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('proposed_canonical_term', sa.String(length=100), nullable=True),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('occurrence_count', sa.Integer(), nullable=False),
        sa.Column('example_source_record_ids', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('proposed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('proposed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewer_user_id', sa.Uuid(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('hse_expert_review_id', sa.Uuid(), nullable=True),
        sa.Column('provenance', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['hse_expert_review_id'], ['hse_expert_reviews.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['proposed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reviewer_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'organization_id', 'source_system', 'domain', 'context', 'source_term', 'mapping_version',
            name='uq_terminology_mapping_decisions_scope_version',
        ),
    )
    op.create_index(op.f('ix_terminology_mapping_decisions_domain'), 'terminology_mapping_decisions', ['domain'], unique=False)
    op.create_index(op.f('ix_terminology_mapping_decisions_normalized_term'), 'terminology_mapping_decisions', ['normalized_term'], unique=False)
    op.create_index(op.f('ix_terminology_mapping_decisions_organization_id'), 'terminology_mapping_decisions', ['organization_id'], unique=False)
    op.create_index(op.f('ix_terminology_mapping_decisions_source_system'), 'terminology_mapping_decisions', ['source_system'], unique=False)
    op.create_index(op.f('ix_terminology_mapping_decisions_status'), 'terminology_mapping_decisions', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_terminology_mapping_decisions_status'), table_name='terminology_mapping_decisions')
    op.drop_index(op.f('ix_terminology_mapping_decisions_source_system'), table_name='terminology_mapping_decisions')
    op.drop_index(op.f('ix_terminology_mapping_decisions_organization_id'), table_name='terminology_mapping_decisions')
    op.drop_index(op.f('ix_terminology_mapping_decisions_normalized_term'), table_name='terminology_mapping_decisions')
    op.drop_index(op.f('ix_terminology_mapping_decisions_domain'), table_name='terminology_mapping_decisions')
    op.drop_table('terminology_mapping_decisions')
