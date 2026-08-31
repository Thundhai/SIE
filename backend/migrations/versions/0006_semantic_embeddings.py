"""semantic knowledge engine: pgvector embeddings

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-31 23:10:00.000000

SIE Semantic Knowledge Engine v0.1. Additive only — no existing table or
column is altered or dropped. Enables the PostgreSQL `vector` extension
(pgvector) and creates one new table, `knowledge_chunk_embeddings`, one
row per (`knowledge_chunk_id`, `provider`, `model_name`, `model_version`)
combination — see app/models/embedding.py's own docstring for the full
multiple-embedding-models-over-time rationale.

The vector column's width is `Vector(settings.EMBEDDING_DIMENSIONS)` —
imported from application configuration, not a second hardcoded literal;
see that setting's own docstring in app/core/config.py for why (a
pgvector column's dimension is fixed at creation time, so changing it
later is itself a new migration, never a silent config-only change).

**Indexing decision — no ANN vector index in this migration.** pgvector
supports approximate-nearest-neighbor indexes (IVFFlat, HNSW) for large
vector datasets, but both require dataset-size-dependent tuning (IVFFlat
needs a `lists` parameter sized to the row count; HNSW's `m`/
`ef_construction` trade recall for build cost) that cannot be chosen
responsibly for a dataset that does not exist yet. This milestone's own
evaluation corpus is a few dozen rows (see
tests/fixtures/evaluation/README.md) — pgvector's exact sequential scan
via the `<=>` (cosine distance) operator is both fast enough at that
scale and exact (an approximate index would only ever *cost* recall
here, never help). Adding an IVFFlat or HNSW index, correctly tuned, is
explicitly future work once a real dataset size is known — see the
README's "Semantic Knowledge Architecture" section.

**A pre-existing defect in migration 0005, discovered while integrating
this migration against a real PostgreSQL + pgvector server for the first
time in this project's history.** `0005`'s `batch_alter_table.add_column()`
calls add two brand-new PostgreSQL enum-typed columns
(`content_type`, `quality_status`) to the already-existing
`knowledge_chunks` table. On real PostgreSQL, Alembic's `add_column`
operation (batched or not) does **not** auto-create the enum type the
column references — only `op.create_table()` does that, as a side effect
of the CREATE TABLE statement's own type visitation. `op.add_column()` is
a narrower ALTER TABLE construct that never gets that same treatment.
Every other native-enum column added by an earlier migration
(0002, 0003, 0004) was introduced via `op.create_table()`, not
`add_column()` on a pre-existing table, which is why this specific defect
was never previously triggered — and why it went undetected until this
milestone, since 0005 itself had only ever been verified via SQLite
(where the distinction is invisible) and an offline `--sql` dry run
against PostgreSQL (which prints the ALTER statement's text without ever
executing it, and so cannot detect that the referenced type does not yet
exist). Confirmed live in this session: a fresh PostgreSQL 16 + pgvector
0.6.0 database, migrated from empty via `alembic upgrade head`, fails at
revision 0005 with `psycopg.errors.UndefinedObject: type
"knowledge_chunk_content_type" does not exist`.

This migration (0006) cannot fix that defect — by the time any migration
numbered after 0005 runs, 0005 has already failed and the whole
`alembic upgrade head` invocation has rolled back as one transaction (see
migrations/env.py), so nothing after 0005 in the chain can rescue it. The
only real fix is inside 0005 itself (creating the two enum types with
`sa.Enum(...).create(op.get_bind(), checkfirst=True)` before the
`add_column` calls that reference them) — which this milestone's explicit
instruction not to modify migrations 0001-0005 deliberately leaves
untouched here. **This is called out prominently in the final report as
a decision requiring the user's sign-off, not silently patched.** Until
resolved, `alembic upgrade head` against a *fresh* PostgreSQL database
fails at 0005 before ever reaching this migration; this migration's own
SQL was still verified for real, end-to-end, against a live local
PostgreSQL 16 + pgvector 0.6.0 server whose schema was first brought to
revision 0005 by pre-creating those two enum types out-of-band (not by
editing 0005's file) — see the final report for the exact commands used.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector

from app.core.config import settings


# revision identifiers, used by Alembic.
revision: str = '0006'
down_revision: Union[str, None] = '0005'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        'knowledge_chunk_embeddings',
        sa.Column('knowledge_chunk_id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=True),
        sa.Column('provider', sa.String(length=100), nullable=False),
        sa.Column('model_name', sa.String(length=200), nullable=False),
        sa.Column('model_version', sa.String(length=50), nullable=False),
        sa.Column('dimensions', sa.Integer(), nullable=False),
        sa.Column('content_hash', sa.String(length=128), nullable=False),
        sa.Column('embedding', Vector(settings.EMBEDDING_DIMENSIONS), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['knowledge_chunk_id'], ['knowledge_chunks.id'], ondelete='CASCADE'
        ),
        sa.ForeignKeyConstraint(
            ['organization_id'], ['organizations.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'knowledge_chunk_id', 'provider', 'model_name', 'model_version',
            name='uq_knowledge_chunk_embeddings_chunk_model',
        ),
    )
    op.create_index(
        op.f('ix_knowledge_chunk_embeddings_knowledge_chunk_id'),
        'knowledge_chunk_embeddings', ['knowledge_chunk_id'], unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_chunk_embeddings_organization_id'),
        'knowledge_chunk_embeddings', ['organization_id'], unique=False,
    )
    op.create_index(
        op.f('ix_knowledge_chunk_embeddings_content_hash'),
        'knowledge_chunk_embeddings', ['content_hash'], unique=False,
    )
    # Speeds "search within this one embedding model identity" — the
    # query RetrievalService always issues (see its own docstring for why
    # vectors from different models are never compared).
    op.create_index(
        'ix_knowledge_chunk_embeddings_model_identity',
        'knowledge_chunk_embeddings', ['provider', 'model_name', 'model_version'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_knowledge_chunk_embeddings_model_identity', table_name='knowledge_chunk_embeddings')
    op.drop_index(
        op.f('ix_knowledge_chunk_embeddings_content_hash'), table_name='knowledge_chunk_embeddings'
    )
    op.drop_index(
        op.f('ix_knowledge_chunk_embeddings_organization_id'), table_name='knowledge_chunk_embeddings'
    )
    op.drop_index(
        op.f('ix_knowledge_chunk_embeddings_knowledge_chunk_id'), table_name='knowledge_chunk_embeddings'
    )
    op.drop_table('knowledge_chunk_embeddings')

    # The vector extension is left enabled on downgrade — dropping a
    # PostgreSQL extension is a heavier, more surprising operation than
    # dropping the one table that used it (and would fail outright if any
    # other object in the database happened to depend on it), so this
    # follows the same conservative convention already used for
    # `plpgsql` (never dropped by any earlier migration either).
