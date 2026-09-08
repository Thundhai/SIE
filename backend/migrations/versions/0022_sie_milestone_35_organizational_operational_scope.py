"""SIE Milestone 35: Organizational & Operational Scope Foundation v0.1

Revision ID: 0022
Revises: 0021
Create Date: 2026-09-08

Purely additive: two new tables (`projects`, `project_sites`) and one
new native enum type (`project_status`). No existing table, column,
row, or type value is altered or removed. See
`app/models/project.py`/`app/models/project_site.py` for the full
design rationale.

`projects` establishes the new `Project` identity (organization-owned:
name, optional code, closed lifecycle status, optional description) --
deliberately no task/schedule/budget columns, per the milestone's own
"identity and relationships only" instruction. `project_sites` is the
many-to-many join table letting a project span multiple sites and a
site host multiple projects, tenant-scoped and `ON DELETE CASCADE` on
both `project_id`/`site_id` (see that model's own docstring for why
this differs from `SafetyAction.site_id`'s `SET NULL`).

No existing table (`safety_events`, `safety_actions`, `risk_assessments`,
`risk_assessment_findings`, `intelligence_decisions`, ...) gains a new
column in this migration -- project/site membership is resolved at
query time through `project_sites`, never duplicated as a `project_id`
foreign key onto every table that could conceivably mention a project
(see `app/models/project.py`'s own docstring for the full "why not"
rationale).

The new `project_status` enum type is introduced via `op.create_table()`
(`projects`), which auto-creates the enum type as part of the table DDL
-- the same, already-established pattern migrations 0015/0021 use (see
either's own docstring). No separate, explicit `sa.Enum(...).create()`
call is made here.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0022'
down_revision: Union[str, None] = '0021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_PROJECT_STATUS_VALUES = ('ACTIVE', 'ON_HOLD', 'COMPLETED', 'CANCELLED')


def upgrade() -> None:
    op.create_table(
        'projects',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('code', sa.String(length=100), nullable=True),
        sa.Column('status', sa.Enum(*_PROJECT_STATUS_VALUES, name='project_status'), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_projects_organization_id'), 'projects', ['organization_id'], unique=False)
    op.create_index(op.f('ix_projects_name'), 'projects', ['name'], unique=False)
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)
    op.create_index('ix_projects_org_status', 'projects', ['organization_id', 'status'], unique=False)
    op.create_index('ix_projects_org_code', 'projects', ['organization_id', 'code'], unique=False)

    op.create_table(
        'project_sites',
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('site_id', sa.Uuid(), nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('created_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['site_id'], ['sites.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'site_id', name='uq_project_sites_project_site'),
    )
    op.create_index(op.f('ix_project_sites_organization_id'), 'project_sites', ['organization_id'], unique=False)
    op.create_index('ix_project_sites_org_project', 'project_sites', ['organization_id', 'project_id'], unique=False)
    op.create_index('ix_project_sites_org_site', 'project_sites', ['organization_id', 'site_id'], unique=False)


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index('ix_project_sites_org_site', table_name='project_sites')
    op.drop_index('ix_project_sites_org_project', table_name='project_sites')
    op.drop_index(op.f('ix_project_sites_organization_id'), table_name='project_sites')
    op.drop_table('project_sites')

    op.drop_index('ix_projects_org_code', table_name='projects')
    op.drop_index('ix_projects_org_status', table_name='projects')
    op.drop_index(op.f('ix_projects_status'), table_name='projects')
    op.drop_index(op.f('ix_projects_name'), table_name='projects')
    op.drop_index(op.f('ix_projects_organization_id'), table_name='projects')
    op.drop_table('projects')

    sa.Enum(name='project_status').drop(bind, checkfirst=True)
