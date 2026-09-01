"""Intelligence Platform Integration & Enterprise API v0.1

Revision ID: 0010
Revises: 0009
Create Date: 2026-09-01

Purely additive — one new table (`idempotency_keys`, item 12's
transport-level `Idempotency-Key` support) plus two new nullable columns
on existing tables: `api_clients.expires_at` (item 25's optional
credential expiration) and `audit_logs.request_id` (item 11's "associate
a request id with audit events"). No existing table's data is touched or
reinterpreted, and no existing column changes type or nullability.

As with every migration since 0007, `alembic revision --autogenerate`
also detected the same pre-existing, unrelated
`ix_knowledge_chunk_embeddings_model_identity` index drift (see
0007-0009's own docstrings) — stripped out here too, so this migration
stays purely additive to what it's actually about.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0010'
down_revision: Union[str, None] = '0009'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'idempotency_keys',
        sa.Column('organization_id', sa.Uuid(), nullable=True),
        sa.Column('api_client_id', sa.Uuid(), nullable=True),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('endpoint', sa.String(length=200), nullable=False),
        sa.Column('idempotency_key', sa.String(length=255), nullable=False),
        sa.Column('request_hash', sa.String(length=64), nullable=False),
        sa.Column('response_status_code', sa.Integer(), nullable=False),
        sa.Column('response_body', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'endpoint', 'idempotency_key', 'organization_id', 'api_client_id', 'user_id',
            name='uq_idempotency_keys_scope',
        ),
    )
    op.create_index(op.f('ix_idempotency_keys_organization_id'), 'idempotency_keys', ['organization_id'], unique=False)

    op.add_column('api_clients', sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True))

    op.add_column('audit_logs', sa.Column('request_id', sa.String(length=64), nullable=True))
    op.create_index(op.f('ix_audit_logs_request_id'), 'audit_logs', ['request_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_audit_logs_request_id'), table_name='audit_logs')
    op.drop_column('audit_logs', 'request_id')

    op.drop_column('api_clients', 'expires_at')

    op.drop_index(op.f('ix_idempotency_keys_organization_id'), table_name='idempotency_keys')
    op.drop_table('idempotency_keys')
