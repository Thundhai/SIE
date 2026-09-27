"""Database boundary: create the commercial_core PostgreSQL schema

Revision ID: 0031
Revises: 0030
Create Date: 2026-09-26

First step of the Public SIE / Commercial Core database-boundary
separation (see backend/docs/DATABASE_BOUNDARY.md). Creates the empty
`commercial_core` PostgreSQL schema that later migrations in this same
chain (0032+) move Commercial-Core-owned tables into, via
`ALTER TABLE ... SET SCHEMA` rather than data copy/delete -- no table is
created, moved, or altered by this migration itself.

This stays a separate, minimal migration (rather than folding schema
creation into the first table move) specifically so it is independently
reviewable and reversible: creating an empty schema can never fail
against existing data, and its own downgrade is safe to attempt in
isolation (it only drops the schema if it is still empty -- if a later
migration in this chain already moved a table into it, that later
migration's own downgrade must move the table back out first).

Idempotent: `CREATE SCHEMA IF NOT EXISTS` / `DROP SCHEMA` (no CASCADE)
so upgrade is safe to re-run and downgrade fails loudly rather than
silently dropping tables if anything unexpected is already in the
schema.

PostgreSQL-only, like migration 0006's `CREATE EXTENSION vector` --
SQLite has no equivalent DDL and this project's own test suite does not
run Alembic migrations against SQLite (see tests/conftest.py; models
build their tables via `Base.metadata.create_all()` with a
`schema_translate_map` instead -- see migration 0032's own docstring).
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0031'
down_revision: Union[str, None] = '0030'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS commercial_core")


def downgrade() -> None:
    # No CASCADE: this fails loudly (rather than silently dropping
    # tables) if a later migration's own downgrade has not already
    # moved everything back out of the schema first.
    op.execute("DROP SCHEMA IF EXISTS commercial_core")
