"""Database boundary: port recommendation_candidates schema requirement

Revision ID: 0033
Revises: 0032
Create Date: 2026-09-26

Ports the *database schema* SIE Milestone 43C (Recommendation Generation
Layer, Commercial Core) needs from the shared PostgreSQL database, per
backend/docs/DATABASE_BOUNDARY.md: Commercial Core has no Alembic chain
of its own (see its `migrations_reference/README.md`) and depends on
this repository's chain to create every table its models map onto.

Two additive operations, mirroring exactly the schema-level content of
Commercial Core's own `migrations_reference/0031_sie_milestone_43c_
recommendation_generation.py` -- **column/table DDL only**. No
application logic (`app/recommendation/generation.py`, prompt
construction, citation validation, LLM invocation) is ported or
reimplemented here, and no SQLAlchemy model for `recommendation_candidates`
is added to this repository -- Public SIE has no business reason to ever
construct or read a row in this table (every route that could is a 501
per M43-IP-03); the table exists here purely because this is the only
live Alembic chain that can create it in the shared database Commercial
Core also runs against.

1. `commercial_core.recommendation_candidates` -- created directly in
   the `commercial_core` schema (never `public`, never moved later).
2. One additive, nullable `recommendation_candidate_id` column (with its
   own foreign key and index) on `intelligence_decisions` -- still in
   `public` at this point in the chain (migration `0035` moves it to
   `commercial_core` later); the FK this migration creates is already
   cross-schema and needs no further change when that move happens (see
   migration `0032`'s own docstring for why `ALTER TABLE ... SET SCHEMA`
   never invalidates an existing FK either direction).

No backfill: both are brand-new concepts with no existing data to
migrate -- identical to Commercial Core's own migration note.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0033'
down_revision: Union[str, None] = '0032'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'recommendation_candidates',
        sa.Column('attention_reference', sa.String(length=500), nullable=False),
        sa.Column('pathway', sa.String(length=50), nullable=False),
        sa.Column('assessment_reference', sa.String(length=500), nullable=False),
        sa.Column('evidence_fingerprint', sa.String(length=64), nullable=False),
        sa.Column('m43a_provenance_sha', sa.String(length=40), nullable=False),
        sa.Column('standards_conflict_outcome', sa.String(length=50), nullable=True),
        sa.Column('as_of', sa.DateTime(timezone=True), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('title', sa.String(length=120), nullable=False),
        sa.Column('rationale_text', sa.Text(), nullable=False),
        sa.Column('suggested_action_description', sa.Text(), nullable=False),
        sa.Column(
            'cited_evidence_ids',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column(
            'cited_standard_ids',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column(
            'limitations',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column('generated_with_limitations', sa.Boolean(), nullable=False),
        sa.Column('llm_provider', sa.String(length=100), nullable=False),
        sa.Column('llm_model', sa.String(length=150), nullable=False),
        sa.Column('llm_model_version', sa.String(length=50), nullable=True),
        sa.Column('prompt_version', sa.String(length=100), nullable=False),
        sa.Column('generated_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('generated_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['generated_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['generated_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        schema='commercial_core',
    )
    op.create_index(
        op.f('ix_recommendation_candidates_organization_id'),
        'recommendation_candidates', ['organization_id'], unique=False, schema='commercial_core',
    )
    op.create_index(
        'ix_recommendation_candidates_org_attention_ref',
        'recommendation_candidates', ['organization_id', 'attention_reference'], unique=False,
        schema='commercial_core',
    )
    op.create_index(
        'ix_recommendation_candidates_org_generated_at',
        'recommendation_candidates', ['organization_id', 'generated_at'], unique=False, schema='commercial_core',
    )

    op.add_column(
        'intelligence_decisions',
        sa.Column('recommendation_candidate_id', sa.Uuid(), nullable=True),
    )
    op.create_foreign_key(
        'fk_intelligence_decisions_recommendation_candidate_id',
        'intelligence_decisions', 'recommendation_candidates',
        ['recommendation_candidate_id'], ['id'], ondelete='SET NULL',
        referent_schema='commercial_core',
    )
    op.create_index(
        'ix_intelligence_decisions_org_recommendation_candidate',
        'intelligence_decisions', ['organization_id', 'recommendation_candidate_id'], unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_intelligence_decisions_org_recommendation_candidate', table_name='intelligence_decisions')
    op.drop_constraint(
        'fk_intelligence_decisions_recommendation_candidate_id', 'intelligence_decisions', type_='foreignkey',
    )
    op.drop_column('intelligence_decisions', 'recommendation_candidate_id')

    op.drop_index(
        'ix_recommendation_candidates_org_generated_at', table_name='recommendation_candidates',
        schema='commercial_core',
    )
    op.drop_index(
        'ix_recommendation_candidates_org_attention_ref', table_name='recommendation_candidates',
        schema='commercial_core',
    )
    op.drop_index(
        op.f('ix_recommendation_candidates_organization_id'), table_name='recommendation_candidates',
        schema='commercial_core',
    )
    op.drop_table('recommendation_candidates', schema='commercial_core')
