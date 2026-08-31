"""identity and access foundation

Revision ID: 0003
Revises: 0002
Create Date: 2026-08-31 17:06:22.165454

Adds the Identity & Access Foundation v0.1 tables (organization_memberships,
identities, audit_logs) and makes a compatibility change to the existing
`users` table so a user can belong to multiple organizations. See the
README's "Compatibility concerns" section for the full rationale; summary:

* `users.organization_id` becomes nullable and is reinterpreted as a
  convenience "default organization" — OrganizationMembership is now the
  authoritative record of org access, not this column. Its FK also
  changes from ON DELETE CASCADE to ON DELETE SET NULL: a user is no
  longer "owned" by this column's organization, so deleting that
  organization must not delete the user.
* `users.role` (a single global role string) is dropped in favor of
  `organization_memberships.role` (one role per membership — a user can
  be ORG_ADMIN in one organization and VIEWER in another) and the new
  `users.platform_role` (the one role that genuinely is global — see
  app/services/permissions.py::PLATFORM_ADMIN).
* `users.email` becomes unique platform-wide (was previously unique only
  per `organization_id`, back when one User row meant one
  organization-scoped account rather than one platform identity).

This is a schema-breaking change to `users` (a dropped column, changed
nullability, changed unique scope). It is judged low-risk here because no
production deployment of this codebase exists yet — Foundation v0.1 never
shipped a User-facing API endpoint (see app/api/v1/*.py: there has never
been a POST /users route), so there is no real user data that could be
depending on the old shape. A project with real user data at this schema
version would instead need a multi-step migration (add the new columns,
backfill `platform_role`/memberships from the old `role`+`organization_id`,
then drop `role` in a later migration) rather than the single-step change
below.

The `users` table changes are wrapped in `batch_alter_table` with an
explicit `naming_convention` for the foreign-key type. This is required
for two independent reasons: SQLite cannot ALTER a table to change a
constraint directly (batch mode's copy-and-move strategy is the standard
workaround, as already used in migration 0002), and the original FK on
`users.organization_id` (created in migration 0001) was never given an
explicit name, so SQLAlchemy/PostgreSQL assigned one automatically
(PostgreSQL's own default convention, `<table>_<column>_fkey`, which the
`naming_convention` mapping below reproduces so Alembic can identify and
drop it by that name on both dialects). The replacement FK is given an
explicit name so this ambiguity does not recur in a future migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Matches PostgreSQL's own default naming convention for an unnamed,
# single-column foreign key constraint — see the module docstring.
_FK_NAMING_CONVENTION = {"fk": "%(table_name)s_%(column_0_name)s_fkey"}


def upgrade() -> None:
    op.create_table(
        'organization_memberships',
        sa.Column('user_id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.Column('role', sa.String(length=50), nullable=False),
        sa.Column(
            'status',
            sa.Enum('ACTIVE', 'SUSPENDED', 'INVITED', 'REVOKED', name='membership_status'),
            nullable=False,
        ),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'user_id', 'organization_id', name='uq_organization_memberships_user_organization'
        ),
    )
    op.create_index(
        op.f('ix_organization_memberships_organization_id'),
        'organization_memberships',
        ['organization_id'],
        unique=False,
    )
    op.create_index(
        'ix_organization_memberships_organization_id_role',
        'organization_memberships',
        ['organization_id', 'role'],
        unique=False,
    )
    op.create_index(
        op.f('ix_organization_memberships_user_id'),
        'organization_memberships',
        ['user_id'],
        unique=False,
    )

    op.create_table(
        'identities',
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('subject', sa.String(length=255), nullable=False),
        sa.Column('issuer', sa.String(length=500), nullable=False),
        sa.Column('email', sa.String(length=320), nullable=True),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('provider', sa.String(length=100), nullable=False),
        sa.Column('last_authenticated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('issuer', 'subject', name='uq_identities_issuer_subject'),
    )
    op.create_index(op.f('ix_identities_user_id'), 'identities', ['user_id'], unique=False)

    op.create_table(
        'audit_logs',
        sa.Column('organization_id', sa.Uuid(), nullable=True),
        sa.Column('user_id', sa.Uuid(), nullable=True),
        sa.Column('action', sa.String(length=100), nullable=False),
        sa.Column('resource_type', sa.String(length=100), nullable=False),
        sa.Column('resource_id', sa.Uuid(), nullable=True),
        sa.Column('timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            'metadata',
            sa.JSON().with_variant(postgresql.JSONB(astext_type=Text()), 'postgresql'),
            nullable=True,
        ),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_audit_logs_action'), 'audit_logs', ['action'], unique=False)
    op.create_index(
        op.f('ix_audit_logs_organization_id'), 'audit_logs', ['organization_id'], unique=False
    )
    op.create_index(op.f('ix_audit_logs_user_id'), 'audit_logs', ['user_id'], unique=False)

    # See module docstring for why this whole block needs batch mode + an
    # explicit naming_convention.
    with op.batch_alter_table('users', naming_convention=_FK_NAMING_CONVENTION) as batch_op:
        batch_op.add_column(sa.Column('platform_role', sa.String(length=50), nullable=True))
        batch_op.alter_column('organization_id', existing_type=sa.Uuid(), nullable=True)
        batch_op.drop_constraint('uq_users_organization_id_email', type_='unique')
        batch_op.drop_index('ix_users_email')
        batch_op.create_index(batch_op.f('ix_users_email'), ['email'], unique=True)
        batch_op.drop_constraint('users_organization_id_fkey', type_='foreignkey')
        batch_op.create_foreign_key(
            'fk_users_organization_id',
            'organizations',
            ['organization_id'],
            ['id'],
            ondelete='SET NULL',
        )
        batch_op.drop_column('role')


def downgrade() -> None:
    with op.batch_alter_table('users', naming_convention=_FK_NAMING_CONVENTION) as batch_op:
        batch_op.add_column(sa.Column('role', sa.String(length=50), nullable=False, server_default='member'))
        batch_op.drop_constraint('fk_users_organization_id', type_='foreignkey')
        batch_op.create_foreign_key(
            'users_organization_id_fkey',
            'organizations',
            ['organization_id'],
            ['id'],
            ondelete='CASCADE',
        )
        batch_op.drop_index('ix_users_email')
        batch_op.create_index('ix_users_email', ['email'], unique=False)
        batch_op.create_unique_constraint(
            'uq_users_organization_id_email', ['organization_id', 'email']
        )
        batch_op.alter_column('organization_id', existing_type=sa.Uuid(), nullable=False)
        batch_op.drop_column('platform_role')

    op.drop_index(op.f('ix_audit_logs_user_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_organization_id'), table_name='audit_logs')
    op.drop_index(op.f('ix_audit_logs_action'), table_name='audit_logs')
    op.drop_table('audit_logs')

    op.drop_index(op.f('ix_identities_user_id'), table_name='identities')
    op.drop_table('identities')

    op.drop_index(
        op.f('ix_organization_memberships_user_id'), table_name='organization_memberships'
    )
    op.drop_index(
        'ix_organization_memberships_organization_id_role', table_name='organization_memberships'
    )
    op.drop_index(
        op.f('ix_organization_memberships_organization_id'),
        table_name='organization_memberships',
    )
    op.drop_table('organization_memberships')

    sa.Enum(name='membership_status').drop(op.get_bind(), checkfirst=True)
