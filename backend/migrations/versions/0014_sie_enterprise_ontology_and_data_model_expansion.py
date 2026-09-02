"""SIE Enterprise Ontology & Data Model Expansion v0.1

Revision ID: 0014
Revises: 0013
Create Date: 2026-09-02

Purely additive: one new table, `ontology_concepts` (a persisted,
versioned, auditable record of what canonical concepts legitimately
belong to SIE's own ontology -- see `app/models/ontology_concept.py`'s
own docstring for the full lifecycle, scoping, and versioning
rationale). Deliberately has NO `organization_id` column -- SIE's
canonical ontology is one shared, platform-wide vocabulary, not a
per-tenant one (see that model's own "Deliberately NOT
OrganizationScopedMixin" note). No existing table's data, columns, or
types are touched; migration `0013` is not modified.

As with every migration since 0007, `alembic revision --autogenerate`
also detected the same pre-existing, unrelated
`ix_knowledge_chunk_embeddings_model_identity` index drift (see
0007-0013's own docstrings) -- stripped out here too, so this migration
stays purely additive to what it's actually about.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0014'
down_revision: Union[str, None] = '0013'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ontology_concepts',
        sa.Column('layer', sa.String(length=30), nullable=False),
        sa.Column('parent_domain', sa.String(length=100), nullable=True),
        sa.Column('concept_key', sa.String(length=100), nullable=False),
        sa.Column('definition', sa.Text(), nullable=False),
        sa.Column('justification', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=30), nullable=False),
        sa.Column('ontology_version', sa.Integer(), nullable=False),
        sa.Column('proposed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('proposed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('reviewer_user_id', sa.Uuid(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['proposed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['reviewer_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('layer', 'parent_domain', 'concept_key', name='uq_ontology_concepts_scope'),
    )
    op.create_index(op.f('ix_ontology_concepts_concept_key'), 'ontology_concepts', ['concept_key'], unique=False)
    op.create_index(op.f('ix_ontology_concepts_layer'), 'ontology_concepts', ['layer'], unique=False)
    op.create_index(op.f('ix_ontology_concepts_parent_domain'), 'ontology_concepts', ['parent_domain'], unique=False)
    op.create_index(op.f('ix_ontology_concepts_status'), 'ontology_concepts', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_ontology_concepts_status'), table_name='ontology_concepts')
    op.drop_index(op.f('ix_ontology_concepts_parent_domain'), table_name='ontology_concepts')
    op.drop_index(op.f('ix_ontology_concepts_layer'), table_name='ontology_concepts')
    op.drop_index(op.f('ix_ontology_concepts_concept_key'), table_name='ontology_concepts')
    op.drop_table('ontology_concepts')
