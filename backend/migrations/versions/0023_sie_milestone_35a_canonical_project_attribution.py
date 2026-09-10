"""SIE Milestone 35A: Canonical Project Attribution Correction

Revision ID: 0023
Revises: 0022
Create Date: 2026-09-08

Corrects SIE Milestone 35's own assumption that a `SafetyEvent`'s
project could be recovered from `site_id -> ProjectSite` alone -- an
assumption that breaks the moment a site hosts more than one project
(exactly what M35 itself explicitly allows). Two independent fixes:

1. **Canonical attribution.** `safety_events` gains one new, nullable
   column, `attributed_project_id` (FK -> `projects.id`, `ON DELETE
   SET NULL`) -- a governed, explicit reference, distinct from the
   pre-existing free-text `project` column (never touched, never
   backfilled from it, never inferred from `ProjectSite`). Every
   existing row gets `NULL` (unattributed -- the same valid state it
   was already in); no backfill, no reinterpretation. See
   `app/models/safety_event.py`'s own docstring.

2. **Tenant-integrity hardening.** `sites` and `projects` each gain a
   `UNIQUE(id, organization_id)` constraint, and `project_sites`'
   `project_id`/`site_id` foreign keys are replaced with composite ones
   -- `(project_id, organization_id) -> projects(id, organization_id)`
   and `(site_id, organization_id) -> sites(id, organization_id)` --
   so PostgreSQL itself now rejects a `project_sites` row whose
   `organization_id` does not match both referenced rows', not merely
   the one application write path that already checked this. See
   `app/models/project_site.py`'s own docstring for why the identical
   technique is not used for `safety_events.attributed_project_id`
   (an `ON DELETE SET NULL` column, incompatible with a composite FK
   when `organization_id` is `NOT NULL`).

Purely additive/hardening: no existing row's data is altered, no
existing table is dropped, no existing behavior changes for any caller
that does not use the new column. `project_sites`' *effective*
constraint (which (project_id, site_id, organization_id) triples are
representable) is unchanged -- the fix only removes representable
states that were already invalid (a row whose organization_id doesn't
match its referenced project/site), which no valid existing row can be.

Downgrade reverses both changes in FK-dependency-safe order: drops the
`safety_events` column/index/FK first, then drops `project_sites`'
composite FKs and restores its original single-column ones, then drops
the two new `UNIQUE(id, organization_id)` constraints.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0023'
down_revision: Union[str, None] = '0022'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _single_column_fk_name(bind, table_name: str, column_name: str) -> str:
    """Looks up the real, live name of the one single-column foreign
    key on `table_name.column_name` -- introspected rather than
    hardcoded, so this migration does not depend on guessing Postgres's
    own default constraint-naming convention (see migration 0021/0022's
    own precedent for using `op.get_bind()` for exactly this kind of
    live-schema-dependent operation)."""
    inspector = sa.inspect(bind)
    for fk in inspector.get_foreign_keys(table_name):
        if fk["constrained_columns"] == [column_name]:
            return fk["name"]
    raise RuntimeError(f"no single-column foreign key found on {table_name}.{column_name}")


def upgrade() -> None:
    bind = op.get_bind()

    # --- 2. Tenant-integrity hardening (done first: safety_events' new
    # FK below references `projects`, which is untouched by this part,
    # but keeping the two fixes in their documented order) -----------------
    op.create_unique_constraint("uq_sites_id_organization_id", "sites", ["id", "organization_id"])
    op.create_unique_constraint("uq_projects_id_organization_id", "projects", ["id", "organization_id"])

    project_fk_name = _single_column_fk_name(bind, "project_sites", "project_id")
    op.drop_constraint(project_fk_name, "project_sites", type_="foreignkey")
    op.create_foreign_key(
        "fk_project_sites_project_id_organization_id",
        "project_sites",
        "projects",
        ["project_id", "organization_id"],
        ["id", "organization_id"],
        ondelete="CASCADE",
    )

    site_fk_name = _single_column_fk_name(bind, "project_sites", "site_id")
    op.drop_constraint(site_fk_name, "project_sites", type_="foreignkey")
    op.create_foreign_key(
        "fk_project_sites_site_id_organization_id",
        "project_sites",
        "sites",
        ["site_id", "organization_id"],
        ["id", "organization_id"],
        ondelete="CASCADE",
    )

    # --- 1. Canonical project attribution on SafetyEvent -------------------
    op.add_column("safety_events", sa.Column("attributed_project_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_safety_events_attributed_project_id"), "safety_events", ["attributed_project_id"], unique=False
    )
    op.create_foreign_key(
        "fk_safety_events_attributed_project_id_projects",
        "safety_events",
        "projects",
        ["attributed_project_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    # --- 1. Canonical project attribution on SafetyEvent (reversed) --------
    op.drop_constraint("fk_safety_events_attributed_project_id_projects", "safety_events", type_="foreignkey")
    op.drop_index(op.f("ix_safety_events_attributed_project_id"), table_name="safety_events")
    op.drop_column("safety_events", "attributed_project_id")

    # --- 2. Tenant-integrity hardening (reversed) ---------------------------
    op.drop_constraint("fk_project_sites_site_id_organization_id", "project_sites", type_="foreignkey")
    op.create_foreign_key(
        None, "project_sites", "sites", ["site_id"], ["id"], ondelete="CASCADE"
    )

    op.drop_constraint("fk_project_sites_project_id_organization_id", "project_sites", type_="foreignkey")
    op.create_foreign_key(
        None, "project_sites", "projects", ["project_id"], ["id"], ondelete="CASCADE"
    )

    op.drop_constraint("uq_projects_id_organization_id", "projects", type_="unique")
    op.drop_constraint("uq_sites_id_organization_id", "sites", type_="unique")
