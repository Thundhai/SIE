"""knowledge quality and semantic chunking foundation

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-31 21:54:32.505412

Additive-only expansion of `knowledge_chunks` for the Knowledge Quality &
Semantic Chunking Foundation v0.1 — see app/models/knowledge_chunk.py's
own docstring for the full rationale behind each new column. No existing
table other than `knowledge_chunks` is touched, and no existing column on
it is altered or dropped.

Wrapped in `batch_alter_table` (with an explicit `naming_convention`, same
as migrations/versions/0003_identity_and_access_foundation.py) purely for
SQLite portability: SQLite cannot ALTER a table to add a foreign key
constraint directly, so batch mode's copy-and-move strategy is required
there. On PostgreSQL, batch mode transparently degrades to direct ALTER
statements — this migration's effect on Postgres is identical to issuing
the add_column/create_foreign_key/create_index calls directly.

Two new columns are declared NOT NULL (`content_type`, `quality_status`)
even though this is an additive migration on a table that may already
hold rows in some environment: both get a `server_default` so the ALTER
succeeds against any pre-existing rows (backfilling them with the most
conservative/neutral value — `ContentType.TEXT` and
`QualityStatus.MEDIUM` respectively) without requiring a separate data
migration, the same `server_default=` pattern 0003 used to add a NOT NULL
column to a pre-existing table. New rows written through the ORM always
supply both explicitly (see app/services/chunking_service.py) — the
server-side default is purely a safety net for legacy rows, not a value
any real ingestion path relies on. The defaults are dropped again at the
end of upgrade() once that backfill has happened, so nothing downstream
comes to depend on the database silently filling either column in.

`extraction_method` reuses the existing `extraction_method` PostgreSQL
enum type created by migration 0004 (referenced here by name, not
redeclared) — its downgrade() below therefore must not drop that type,
since 0004's own tables may still be using it; only the two enum types
newly created by *this* migration are dropped on downgrade.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0005'
down_revision: Union[str, None] = '0004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Matches PostgreSQL's own default naming convention for an unnamed,
# single-column foreign key constraint — see the module docstring.
_FK_NAMING_CONVENTION = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}


def upgrade() -> None:
    with op.batch_alter_table('knowledge_chunks', naming_convention=_FK_NAMING_CONVENTION) as batch_op:
        batch_op.add_column(sa.Column('document_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('source_id', sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column('organization_id', sa.Uuid(), nullable=True))
        batch_op.add_column(
            sa.Column(
                'content_type',
                sa.Enum(
                    'TEXT', 'TABLE', 'IMAGE', 'STRUCTURED_RECORD',
                    name='knowledge_chunk_content_type',
                ),
                nullable=False,
                server_default='TEXT',
            )
        )
        batch_op.add_column(sa.Column('sheet_name', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('row_number', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('slide_number', sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                'section_path',
                sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'),
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column('source_reference', sa.String(length=500), nullable=True))
        batch_op.add_column(
            sa.Column(
                'extraction_method',
                sa.Enum(
                    'TEXT_EXTRACTION', 'STRUCTURED_PARSE', 'OCR', 'NONE',
                    name='extraction_method',
                ),
                nullable=True,
            )
        )
        batch_op.add_column(
            sa.Column(
                'quality_status',
                sa.Enum(
                    'HIGH', 'MEDIUM', 'LOW', 'INSUFFICIENT',
                    name='knowledge_chunk_quality_status',
                ),
                nullable=False,
                server_default='MEDIUM',
            )
        )
        batch_op.create_index(
            batch_op.f('ix_knowledge_chunks_document_id'), ['document_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_knowledge_chunks_organization_id'), ['organization_id'], unique=False
        )
        batch_op.create_index(
            batch_op.f('ix_knowledge_chunks_source_id'), ['source_id'], unique=False
        )
        batch_op.create_foreign_key(
            'fk_knowledge_chunks_source_id', 'knowledge_sources', ['source_id'], ['id'], ondelete='CASCADE'
        )
        batch_op.create_foreign_key(
            'fk_knowledge_chunks_document_id', 'knowledge_documents', ['document_id'], ['id'], ondelete='CASCADE'
        )
        batch_op.create_foreign_key(
            'fk_knowledge_chunks_organization_id', 'organizations', ['organization_id'], ['id'], ondelete='CASCADE'
        )

    # Drop the server defaults once existing rows (if any) are backfilled
    # — every future insert goes through the ORM, which always supplies
    # both columns explicitly (see app/services/chunking_service.py), so
    # there is no reason for the database to keep silently defaulting them.
    with op.batch_alter_table('knowledge_chunks', naming_convention=_FK_NAMING_CONVENTION) as batch_op:
        batch_op.alter_column('content_type', server_default=None)
        batch_op.alter_column('quality_status', server_default=None)


def downgrade() -> None:
    with op.batch_alter_table('knowledge_chunks', naming_convention=_FK_NAMING_CONVENTION) as batch_op:
        batch_op.drop_constraint('fk_knowledge_chunks_organization_id', type_='foreignkey')
        batch_op.drop_constraint('fk_knowledge_chunks_document_id', type_='foreignkey')
        batch_op.drop_constraint('fk_knowledge_chunks_source_id', type_='foreignkey')
        batch_op.drop_index(batch_op.f('ix_knowledge_chunks_source_id'))
        batch_op.drop_index(batch_op.f('ix_knowledge_chunks_organization_id'))
        batch_op.drop_index(batch_op.f('ix_knowledge_chunks_document_id'))
        batch_op.drop_column('quality_status')
        batch_op.drop_column('extraction_method')
        batch_op.drop_column('source_reference')
        batch_op.drop_column('section_path')
        batch_op.drop_column('slide_number')
        batch_op.drop_column('row_number')
        batch_op.drop_column('sheet_name')
        batch_op.drop_column('content_type')
        batch_op.drop_column('organization_id')
        batch_op.drop_column('source_id')
        batch_op.drop_column('document_id')

    # Native enum types created by the sa.Enum columns above are not
    # dropped automatically by op.drop_column() on PostgreSQL; drop them
    # explicitly (see migrations 0002/0003/0004 for the same pattern).
    # 'extraction_method' is NOT dropped here — it was created by
    # migration 0004 and is still used by ingested_files/ingestion_jobs;
    # only the two enum types this migration itself created are dropped.
    sa.Enum(name='knowledge_chunk_quality_status').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='knowledge_chunk_content_type').drop(op.get_bind(), checkfirst=True)
