"""Tenant entitlements and assertion replay records (multi-tenant stage 2)

Revision ID: 0036
Revises: 0035
Create Date: 2026-10-28

Creates, in the `commercial_core` schema, the three tables Commercial
Core's domain service reads once it runs in `dual` or `multi` tenant
mode (see Thundhai/SIE-Commercial-Core `app/models/tenant_entitlement.py`
and `docs/BOUNDARY_DECISIONS.md` section 17):

1. `tenant_entitlements` -- one row per organization Commercial Core
   serves, with a status and the capabilities granted. **No row means
   deny**, and so do `SUSPENDED` and `REVOKED`. Written only by
   Commercial Core's operator script (CC-OPS), never by any API.
2. `tenant_entitlement_events` -- append-only audit of every change to
   the table above, written in the same transaction.
3. `tenant_assertion_jti` -- each `jti` a write assertion has used, so a
   captured `decisions_write` assertion cannot be replayed (owner
   decision D3). Rows are purged once their assertion has expired.

Like migration 0033, this is DDL only and Public SIE has no model for
these tables: it never reads or writes them. `migrations/env.py`
excludes them from `alembic check` for the same reason.

**Inert until used.** The tables start empty, and the `legacy` tenant
mode production runs today never reads them, so applying this migration
changes no behaviour. Downgrade drops the tables and any rows in them;
never downgrade it in production once entitlements exist.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: `sie_contract.TenantCapability` values (sie-contract 0.9.0), spelled
#: out because a migration must not change when the contract does.
#: Adding a capability is a breaking contract change and needs its own
#: migration to widen this check.
_KNOWN_CAPABILITIES = (
    "commercial_core:attention_read",
    "commercial_core:analytics_read",
    "commercial_core:enterprise_intelligence_read",
    "commercial_core:decisions_read",
    "commercial_core:decisions_write",
    "commercial_core:rag_query",
)
_SCHEMA = "commercial_core"


def upgrade() -> None:
    known = ", ".join(f"'{cap}'" for cap in _KNOWN_CAPABILITIES)

    op.create_table(
        "tenant_entitlements",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=16), server_default="SUSPENDED", nullable=False),
        sa.Column(
            "capabilities",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("granted_by", sa.String(length=255), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("revoked_by", sa.String(length=255), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "status IN ('ACTIVE', 'SUSPENDED', 'REVOKED')", name="ck_tenant_entitlements_status"
        ),
        sa.CheckConstraint(
            f"capabilities <@ ARRAY[{known}]::text[]", name="ck_tenant_entitlements_known_capabilities"
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["public.organizations.id"],
            name="fk_tenant_entitlements_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_entitlements"),
        sa.UniqueConstraint("organization_id", name="uq_tenant_entitlements_organization_id"),
        schema=_SCHEMA,
    )

    op.create_table(
        "tenant_entitlement_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("actor", sa.String(length=255), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["public.organizations.id"],
            name="fk_tenant_entitlement_events_organization_id",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_tenant_entitlement_events"),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_tenant_entitlement_events_org_at",
        "tenant_entitlement_events",
        ["organization_id", "at"],
        unique=False,
        schema=_SCHEMA,
    )

    op.create_table(
        "tenant_assertion_jti",
        sa.Column("jti", sa.Uuid(), nullable=False),
        sa.Column("organization_id", sa.Uuid(), nullable=False),
        sa.Column("cap", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("jti", name="pk_tenant_assertion_jti"),
        schema=_SCHEMA,
    )
    op.create_index(
        "ix_tenant_assertion_jti_expires_at",
        "tenant_assertion_jti",
        ["expires_at"],
        unique=False,
        schema=_SCHEMA,
    )


def downgrade() -> None:
    op.drop_index("ix_tenant_assertion_jti_expires_at", table_name="tenant_assertion_jti", schema=_SCHEMA)
    op.drop_table("tenant_assertion_jti", schema=_SCHEMA)
    op.drop_index("ix_tenant_entitlement_events_org_at", table_name="tenant_entitlement_events", schema=_SCHEMA)
    op.drop_table("tenant_entitlement_events", schema=_SCHEMA)
    op.drop_table("tenant_entitlements", schema=_SCHEMA)
