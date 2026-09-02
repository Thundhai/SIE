"""Real Enterprise Dataset Validation Foundation v0.1

Revision ID: 0012
Revises: 0011
Create Date: 2026-09-02

Purely additive: one new table, `hse_expert_reviews` (item 8's
structured, persisted mechanism for a future human HSE expert to review
terminology mappings, quarantined records, unexpected classifications,
representative intelligence outputs, and risk indicators — see
`app/models/hse_expert_review.py`'s own docstring). No existing table's
data, columns, or types are touched.

As with every migration since 0007, `alembic revision --autogenerate`
also detected the same pre-existing, unrelated
`ix_knowledge_chunk_embeddings_model_identity` index drift (see
0007-0011's own docstrings) — stripped out here too, so this migration
stays purely additive to what it's actually about.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0012'
down_revision: Union[str, None] = '0011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'hse_expert_reviews',
        sa.Column('target_type', sa.String(length=30), nullable=False),
        sa.Column('target_reference', sa.String(length=500), nullable=False),
        sa.Column('provenance', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('outcome', sa.String(length=30), nullable=True),
        sa.Column('reviewer_comment', sa.Text(), nullable=True),
        sa.Column('reviewer_user_id', sa.Uuid(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewer_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_hse_expert_reviews_organization_id'), 'hse_expert_reviews', ['organization_id'], unique=False)
    op.create_index(op.f('ix_hse_expert_reviews_target_type'), 'hse_expert_reviews', ['target_type'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_hse_expert_reviews_target_type'), table_name='hse_expert_reviews')
    op.drop_index(op.f('ix_hse_expert_reviews_organization_id'), table_name='hse_expert_reviews')
    op.drop_table('hse_expert_reviews')
