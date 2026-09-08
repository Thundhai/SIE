"""SIE Milestone 36: Project/Site Temporal Scope Integrity

Revision ID: 0025
Revises: 0024
Create Date: 2026-09-08

Corrects the remaining gap SIE Milestone 35B left open: `ProjectSite`
membership ("which sites does this project operate at") was still
current-state only, so a historical `as_of` query could only ever
answer "was Project P associated with Site S at instant T" using
*today's* `project_sites` row -- wrong the moment that membership has
ever changed. See `app/models/project_site_history.py`'s own docstring
for the full rationale, and
`app/intelligence/temporal.py::is_project_site_associated_as_of()`/
`project_site_ids_as_of()` for the reconstruction this enables.

Adds one new table, `project_site_history` -- purely additive: no
existing table, column, row, or type is altered or removed.
`project_sites` is unchanged and remains the fast, current-state
representation every current-operations read already uses.

Composite foreign keys, mirroring `project_sites`' own SIE Milestone
35A hardening exactly (not `SafetyEventProjectAttributionHistory`'s
single-column exception -- nothing here needs `ON DELETE SET NULL`
semantics, so the identical technique applies cleanly).

**Backfill.** Every existing `project_sites` row gets one `LINKED`
history row, using that row's own `created_at` -- the *actual* link
creation timestamp, not an approximation. This is more precise than
SIE Milestone 35B's own `SafetyEvent.attributed_project_id` backfill
(which had to use `updated_at` as a best-available proxy, since no
column on `SafetyEvent` records exactly when its attribution was set):
`ProjectSite.created_at` genuinely *is* the moment the link was made,
because `ProjectSite` rows are never updated after creation (see that
model's own docstring -- unlink is a hard delete, not a status change),
so no proxy is needed here.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0025'
down_revision: Union[str, None] = '0024'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'project_site_history',
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('site_id', sa.Uuid(), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('changed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('changed_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['changed_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(
            ['project_id', 'organization_id'], ['projects.id', 'projects.organization_id'],
            ondelete='CASCADE', name='fk_project_site_history_project_id_organization_id',
        ),
        sa.ForeignKeyConstraint(
            ['site_id', 'organization_id'], ['sites.id', 'sites.organization_id'],
            ondelete='CASCADE', name='fk_project_site_history_site_id_organization_id',
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_project_site_history_organization_id'), 'project_site_history', ['organization_id'], unique=False
    )
    op.create_index(
        'ix_project_site_history_project_site_created', 'project_site_history',
        ['project_id', 'site_id', 'created_at'], unique=False,
    )

    # Backfill -- see module docstring's "Backfill" section. Same
    # per-dialect random-UUID expression migration 0024 uses (Postgres:
    # gen_random_uuid(); SQLite, local/CI-less test runs only:
    # randomblob-based UUID string).
    bind = op.get_bind()
    if bind.dialect.name == 'postgresql':
        uuid_expr = 'gen_random_uuid()'
    else:
        uuid_expr = (
            "lower(hex(randomblob(4)) || '-' || hex(randomblob(2)) || '-4' || "
            "substr(hex(randomblob(2)),2) || '-' || substr('89ab',abs(random()) % 4 + 1,1) || "
            "substr(hex(randomblob(2)),2) || '-' || hex(randomblob(6)))"
        )
    bind.execute(
        sa.text(
            f"""
            INSERT INTO project_site_history
                (id, organization_id, project_id, site_id, action, created_at)
            SELECT {uuid_expr}, organization_id, project_id, site_id, 'LINKED', created_at
            FROM project_sites
            """
        )
    )


def downgrade() -> None:
    op.drop_index('ix_project_site_history_project_site_created', table_name='project_site_history')
    op.drop_index(op.f('ix_project_site_history_organization_id'), table_name='project_site_history')
    op.drop_table('project_site_history')
