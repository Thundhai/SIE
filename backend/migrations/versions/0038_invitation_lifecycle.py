"""Invitation lifecycle on identity_link_grants

Revision ID: 0038
Revises: 0037
Create Date: 2026-11-02

Adds the invitation lifecycle (PENDING -> REGISTRATION_STARTED ->
VERIFIED -> ACCEPTED, or EXPIRED / REVOKED) to `identity_link_grants`:

* `status`, its timestamps, `revoked_by_user_id`, `accepted_membership_id`,
  `issue_count` (resends) and `failed_attempts` (email mismatches).
* A partial unique index: one open invitation per (organization, email).
* An (organization_id, status) index for the administrator's list.

Upgrade: redeemed rows become `ACCEPTED`; unredeemed invitations from
0037 (issued when the code alone was enough) become `EXPIRED`, which also
clears any duplicates before the unique index is built. Administrators
resend any that are still wanted. Account-link grants stay `PENDING`.

Downgrade: every unredeemed invitation and every revoked grant is expired
first, so 0037 can't revive a withdrawn link or accept an invitation
without the verified-email checks. Then the columns and indexes are
dropped. No user, identity or membership is touched in either direction.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OPEN_INVITATION_WHERE = "kind = 'INVITATION' AND status IN ('PENDING', 'REGISTRATION_STARTED', 'VERIFIED')"


def upgrade() -> None:
    with op.batch_alter_table("identity_link_grants") as batch:
        batch.add_column(sa.Column("status", sa.String(length=24), server_default="PENDING", nullable=False))
        batch.add_column(sa.Column("registration_started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("revoked_by_user_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("accepted_membership_id", sa.Uuid(), nullable=True))
        batch.add_column(sa.Column("issue_count", sa.Integer(), server_default="1", nullable=False))
        batch.add_column(sa.Column("failed_attempts", sa.Integer(), server_default="0", nullable=False))
        batch.create_foreign_key(
            "identity_link_grants_revoked_by_user_id_fkey", "users", ["revoked_by_user_id"], ["id"], ondelete="SET NULL"
        )
        batch.create_foreign_key(
            "identity_link_grants_accepted_membership_id_fkey",
            "organization_memberships",
            ["accepted_membership_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch.create_check_constraint(
            "ck_identity_link_grants_status",
            "status IN ('PENDING', 'REGISTRATION_STARTED', 'VERIFIED', 'ACCEPTED', 'EXPIRED', 'REVOKED')",
        )

    op.execute("UPDATE identity_link_grants SET status = 'ACCEPTED' WHERE redeemed_at IS NOT NULL")
    # Unredeemed invitations from 0037 were issued when the code alone was
    # enough to accept. They must not become acceptable under any rule but
    # the new one, and 0037 allowed duplicates per organization and email
    # that would break the unique index below. Expire them all; an
    # administrator resends any that are still wanted.
    op.execute("UPDATE identity_link_grants SET status = 'EXPIRED' WHERE kind = 'INVITATION' AND redeemed_at IS NULL")
    op.create_index(
        "uq_identity_link_grants_open_invitation",
        "identity_link_grants",
        ["organization_id", "invited_email"],
        unique=True,
        postgresql_where=sa.text(_OPEN_INVITATION_WHERE),
        sqlite_where=sa.text(_OPEN_INVITATION_WHERE),
    )
    op.create_index("ix_identity_link_grants_org_status", "identity_link_grants", ["organization_id", "status"])


def downgrade() -> None:
    # Without the status column, 0037 would treat a revoked invitation as
    # live again, and would accept outstanding invitations without the
    # verified-email checks. Expire every unredeemed invitation and every
    # revoked grant first, so a rollback can't revive a withdrawn link.
    op.execute(
        "UPDATE identity_link_grants "
        "SET expires_at = CASE WHEN expires_at < CURRENT_TIMESTAMP THEN expires_at ELSE CURRENT_TIMESTAMP END "
        "WHERE redeemed_at IS NULL AND (kind = 'INVITATION' OR status = 'REVOKED')"
    )
    op.drop_index("ix_identity_link_grants_org_status", table_name="identity_link_grants")
    op.drop_index("uq_identity_link_grants_open_invitation", table_name="identity_link_grants")
    with op.batch_alter_table("identity_link_grants") as batch:
        batch.drop_constraint("ck_identity_link_grants_status", type_="check")
        batch.drop_constraint("identity_link_grants_accepted_membership_id_fkey", type_="foreignkey")
        batch.drop_constraint("identity_link_grants_revoked_by_user_id_fkey", type_="foreignkey")
        for column in (
            "failed_attempts",
            "issue_count",
            "accepted_membership_id",
            "revoked_by_user_id",
            "revoked_at",
            "verified_at",
            "registration_started_at",
            "status",
        ):
            batch.drop_column(column)
