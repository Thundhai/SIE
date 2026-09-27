"""Database boundary: move the predictive-modeling cluster into commercial_core

Revision ID: 0034
Revises: 0033
Create Date: 2026-09-26

Moves the seven self-contained predictive-modeling tables -- the
"predictions cluster" per backend/docs/DATABASE_BOUNDARY.md -- from
`public` to `commercial_core`, via `ALTER TABLE ... SET SCHEMA` (no data
copy/delete, no row read or rewritten):

    dataset_versions, feature_snapshots, model_registry_entries,
    model_approvals, model_review_flags, predictions, prediction_outcomes

**Why this cluster moves cleanly, with no cross-boundary FK to repoint.**
Every foreign key among these seven tables points at another table in
this exact list (`model_approvals`/`model_review_flags`/`predictions` ->
`model_registry_entries`; `predictions` -> `feature_snapshots`;
`prediction_outcomes` -> `predictions`; `model_registry_entries` ->
`dataset_versions`) -- confirmed by the Database Boundary Separation
milestone's own repository-wide foreign-key audit (see that document's
own "Cross-Boundary Coupling" section). None references, or is
referenced by, any table that stays in `public`. `ALTER TABLE ... SET
SCHEMA` never invalidates an existing FK either direction (see migration
`0032`'s own docstring) -- every one of the intra-cluster constraints
already created by migrations `0007`-`0009` keeps enforcing exactly as
before, automatically, the moment this migration commits.

**Why order matters within this migration.** `ALTER TABLE` does not
require moving referenced tables before referencing ones -- schema
membership and FK validity are independent -- but this migration still
moves `dataset_versions`/`model_registry_entries` (the two tables other
tables in this same list reference) before the tables that reference
them, purely for this file's own readability as a record of the
cluster's internal shape, not because PostgreSQL requires that order.

Every route Public SIE ever exposed over this cluster (`app/api/v1/
predictions.py`, `app/api/v1/model_governance.py`) already returns
`HTTP 501` unconditionally, per M43-IP-03 -- this migration changes
where the tables physically live, not what any endpoint does.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0034'
down_revision: Union[str, None] = '0033'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "dataset_versions",
    "model_registry_entries",
    "feature_snapshots",
    "model_approvals",
    "model_review_flags",
    "predictions",
    "prediction_outcomes",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} SET SCHEMA commercial_core")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"ALTER TABLE commercial_core.{table} SET SCHEMA public")
