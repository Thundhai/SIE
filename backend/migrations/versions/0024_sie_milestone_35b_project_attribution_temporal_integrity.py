"""SIE Milestone 35B: Project Attribution Temporal Integrity

Revision ID: 0024
Revises: 0023
Create Date: 2026-09-08

Corrects SIE Milestone 35A's own remaining gap: `events_as_of(project_id=...)`
filtered on `SafetyEvent.attributed_project_id` -- a single current-state
column -- which is correct for "as of right now" but silently wrong for
any historical `as_of` once an event is ever re-attributed or cleared
(a June 20 Alpha attribution reassigned to Beta on June 25 would
incorrectly read as "always Beta," including for an `as_of` before the
reassignment). See `app/models/safety_event_project_attribution_history.py`'s
own docstring for the full rationale, the two options considered and
rejected (a single `project_attributed_at` timestamp -- insufficient,
as the milestone's own worked example shows; explicitly prohibiting
project-filtered historical intelligence -- rejected as unnecessarily
regressive given where this system is going), and exactly why Option B
(a small, append-only attribution history table) was chosen instead.

Adds one new table, `safety_event_project_attribution_history` --
purely additive: no existing table, column, row, or type is altered or
removed. `SafetyEvent.attributed_project_id` is unchanged and remains
the fast, current-state answer every non-temporal read already uses;
this table is the one place point-in-time reconstruction happens (see
`app/intelligence/temporal.py::events_as_of()`).

**Backfill (best-effort, not exact).** Every existing `safety_events`
row with `attributed_project_id IS NOT NULL` (necessarily written by
SIE Milestone 35A's own code, before this history table existed) gets
one synthesized `ATTRIBUTED` history row, so it does not silently
vanish from every project-filtered query the moment this migration
lands (with no history row at all, the point-in-time reconstruction
query in `events_as_of()` would correctly, but wrongly for this case,
conclude "never attributed"). The synthesized row's `created_at` uses
that `safety_events` row's own `updated_at` -- the closest available
signal to "when the attribution was set" (`attribute_event_to_project()`
mutates the row, and `TimestampMixin.updated_at` has `onupdate=utcnow`),
though not exact if the row was touched by something else afterward.
This branch runs only against whatever M35A-era data already exists in
this development branch; there is no real production data behind it.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0024'
down_revision: Union[str, None] = '0023'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'safety_event_project_attribution_history',
        sa.Column('event_id', sa.Uuid(), nullable=False),
        sa.Column('project_id', sa.Uuid(), nullable=False),
        sa.Column('action', sa.String(length=20), nullable=False),
        sa.Column('changed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('changed_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['event_id'], ['safety_events.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['changed_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_safety_event_project_attribution_history_organization_id'),
        'safety_event_project_attribution_history', ['organization_id'], unique=False,
    )
    op.create_index(
        op.f('ix_safety_event_project_attribution_history_event_id'),
        'safety_event_project_attribution_history', ['event_id'], unique=False,
    )
    op.create_index(
        'ix_safety_event_project_attribution_history_event_created',
        'safety_event_project_attribution_history', ['event_id', 'created_at'], unique=False,
    )

    # Backfill -- see module docstring's "Backfill" section. Uses the
    # table's own id generator via a server-side default is not
    # available for a plain Uuid column, so a per-dialect random UUID
    # expression is used: Postgres's gen_random_uuid() (pgcrypto is
    # already relied on elsewhere in this schema for uuid defaults) and
    # SQLite's lower(hex(randomblob(16))) reformatted into a UUID
    # string -- SQLite is used only by local/CI-less test runs, never a
    # real deployment target for this migration.
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
            INSERT INTO safety_event_project_attribution_history
                (id, organization_id, event_id, project_id, action, created_at)
            SELECT {uuid_expr}, organization_id, id, attributed_project_id, 'ATTRIBUTED', updated_at
            FROM safety_events
            WHERE attributed_project_id IS NOT NULL
            """
        )
    )


def downgrade() -> None:
    op.drop_index(
        'ix_safety_event_project_attribution_history_event_created',
        table_name='safety_event_project_attribution_history',
    )
    op.drop_index(
        op.f('ix_safety_event_project_attribution_history_event_id'),
        table_name='safety_event_project_attribution_history',
    )
    op.drop_index(
        op.f('ix_safety_event_project_attribution_history_organization_id'),
        table_name='safety_event_project_attribution_history',
    )
    op.drop_table('safety_event_project_attribution_history')
