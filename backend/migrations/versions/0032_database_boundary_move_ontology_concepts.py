"""Database boundary: move ontology_concepts into commercial_core schema

Revision ID: 0032
Revises: 0031
Create Date: 2026-09-26

Moves the `ontology_concepts` table from `public` to `commercial_core`
via `ALTER TABLE ... SET SCHEMA` -- a metadata-only operation. No row is
read, copied, or rewritten; every id, timestamp, status, ontology
version, and governance field is preserved exactly, along with the
table's own indexes and its unique constraint.

**Ownership, per backend/docs/DATABASE_BOUNDARY.md.** `ontology_concepts`
is Commercial-Core-owned governance-controlled reference data: its
propose/approve/reject/deprecate lifecycle (`ontology_governance_service.py`)
lives exclusively in `Thundhai/SIE-Commercial-Core`, not here -- M43-IP-03
already removed that service from Public SIE. Public SIE keeps exactly
one read dependency on it (`app/risk_assessment/risk_area_resolution.py`,
restricted to `APPROVED` + `is_risk_area_eligible` rows) and one
FK-enforced write-time check (`RiskAssessmentFinding.risk_area_concept_id`,
`ON DELETE RESTRICT`).

**Why the FK survives this move unchanged, with no separate "repoint"
migration.** `commercial_core` is a schema in the *same* PostgreSQL
database as `public` in this milestone -- schema separation, not
database separation (see backend/docs/DATABASE_BOUNDARY.md's own
"Later" section for the deliberately-deferred full-separation state).
`ALTER TABLE ... SET SCHEMA` only reassigns the table's schema; it does
not drop, invalidate, or require recreating any foreign key that another
table (`risk_assessment_findings.risk_area_concept_id`, here) already
has referencing it -- PostgreSQL resolves an existing FK constraint by
the referenced table's object identity, not by re-resolving its
schema-qualified name, so the constraint keeps enforcing `ON DELETE
RESTRICT` exactly as before, automatically, the moment this migration
commits. Nothing in `app/models/risk_assessment.py`'s own DDL needs a
migration-level change for an already-upgraded database; only its
Python `ForeignKey(...)` string is updated (this milestone's model
changes) so a *fresh* install's `Base.metadata`-driven tooling and
Alembic's own autogenerate stay consistent with where the table actually
lives after this migration runs.

**Fresh install vs. upgrade convergence.** Migration 0014 still creates
`ontology_concepts` in `public` and migration 0017 still seeds its 11
GLOBAL rows there, unmodified -- neither historical migration is edited.
This migration runs after both, on every install (fresh or upgrade
alike), and simply relocates whatever the table already contains at that
point in the chain -- a fresh install and an already-upgraded database
converge on the identical final state.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0032'
down_revision: Union[str, None] = '0031'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TABLE ontology_concepts SET SCHEMA commercial_core")


def downgrade() -> None:
    op.execute("ALTER TABLE commercial_core.ontology_concepts SET SCHEMA public")
