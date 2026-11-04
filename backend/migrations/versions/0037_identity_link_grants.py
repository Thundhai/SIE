"""Identity link grants (invitations and account links)

Revision ID: 0037
Revises: 0036
Create Date: 2026-11-02

Creates `identity_link_grants`: the one-time invitations and account-link
grants an unknown OIDC identity must redeem before it is bound to a SIE
user. Email is no longer matched automatically (see
app/services/identity_service.py and app/models/identity_link_grant.py).

DDL only. It adds one empty table and changes no existing row: users and
identities are untouched, and identities already bound by (issuer,
subject) keep authenticating exactly as before.

The table holds hashed one-time codes, so on Supabase the `anon` and
`authenticated` API roles get no privileges on it, in case the project's
default privileges grant them on new `public` tables. The revoke is
skipped where those roles don't exist (plain PostgreSQL, CI).
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "identity_link_grants",
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("token_sha256", sa.String(length=64), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=True),
        sa.Column("organization_id", sa.Uuid(), nullable=True),
        sa.Column("role", sa.String(length=50), nullable=True),
        sa.Column("invited_email", sa.String(length=320), nullable=True),
        sa.Column("allows_platform_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_identity_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("kind IN ('INVITATION', 'ACCOUNT_LINK')", name="ck_identity_link_grants_kind"),
        sa.CheckConstraint(
            "(kind = 'INVITATION' AND organization_id IS NOT NULL AND role IS NOT NULL "
            "AND invited_email IS NOT NULL) "
            "OR (kind = 'ACCOUNT_LINK' AND target_user_id IS NOT NULL)",
            name="ck_identity_link_grants_shape",
        ),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["organization_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["redeemed_identity_id"], ["identities.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_sha256"),
    )
    op.create_index(
        op.f("ix_identity_link_grants_target_user_id"), "identity_link_grants", ["target_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_identity_link_grants_organization_id"), "identity_link_grants", ["organization_id"], unique=False
    )
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
                REVOKE ALL ON TABLE identity_link_grants FROM anon;
            END IF;
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
                REVOKE ALL ON TABLE identity_link_grants FROM authenticated;
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_identity_link_grants_organization_id"), table_name="identity_link_grants")
    op.drop_index(op.f("ix_identity_link_grants_target_user_id"), table_name="identity_link_grants")
    op.drop_table("identity_link_grants")
