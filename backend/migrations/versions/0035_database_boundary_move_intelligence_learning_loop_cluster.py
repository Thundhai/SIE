"""Database boundary: move the intelligence/learning-loop cluster into commercial_core

Revision ID: 0035
Revises: 0034
Create Date: 2026-09-26

Moves the remaining Commercial-Core-owned tables from `public` to
`commercial_core`, via `ALTER TABLE ... SET SCHEMA` (no data copy/
delete, no row read or rewritten): the intelligence-decision/outcome/
learning-loop cluster, plus `terminology_mapping_decisions` and
`hse_expert_reviews`:

    intelligence_decisions, intelligence_outcomes,
    intelligence_outcome_verifications, intelligence_learning_candidates,
    intelligence_learning_candidate_governance_decisions,
    organizational_memories, organizational_memory_governance_decisions,
    terminology_mapping_decisions, hse_expert_reviews

**Correction to this milestone's own earlier draft classification.**
An initial pass over this repository alone found no live Public SIE
service or router touching `terminology_mapping_decisions`/
`hse_expert_reviews` after M43-IP-03 and provisionally called them
"orphaned, deletion candidates." Checking `Thundhai/SIE-Commercial-Core`
directly (not assumed) found both tables have real, active owners there
-- `app/services/{hse_review_service,terminology_reprocessing_service,
terminology_decision_artifact_service,terminology_calibration_service,
ontology_terminology_integration_service}.py` -- so both belong in this
same Commercial-Core-owned move, not a separate "possibly dead" cleanup.
See backend/docs/DATABASE_BOUNDARY.md's own note on this correction.

**Cross-schema foreign keys this migration deliberately preserves,
unweakened.** Every table in this list keeps its existing, real foreign
keys into `public`-owned tables exactly as they were --
`ON DELETE SET NULL`/`CASCADE`/`RESTRICT` semantics unchanged, per this
milestone's own non-negotiable rule against converting any of them to a
soft UUID-only reference at this stage:

    intelligence_decisions          -> sites, safety_actions, users, api_clients
    intelligence_outcomes           -> sites, safety_actions, users, api_clients
                                        (+ composite FK -> commercial_core.intelligence_decisions)
    intelligence_outcome_verifications -> users, api_clients
                                        (+ composite FK -> commercial_core.intelligence_outcomes)
    intelligence_learning_candidates -> users, api_clients
                                        (+ composite FKs -> commercial_core.intelligence_outcomes /
                                         commercial_core.intelligence_outcome_verifications)
    intelligence_learning_candidate_governance_decisions -> users, api_clients
                                        (+ composite FK -> commercial_core.intelligence_learning_candidates)
    organizational_memories         -> users, api_clients
                                        (+ composite FK -> commercial_core.intelligence_learning_candidates)
    organizational_memory_governance_decisions -> users, api_clients
                                        (+ composite FK -> commercial_core.organizational_memories)
    terminology_mapping_decisions   -> organizations, users
                                        (+ FK -> commercial_core.hse_expert_reviews, moved in this
                                         same migration)
    hse_expert_reviews              -> users (+ self-referential)

Every one of these -- both the ones into `public` and the composite
ones among tables moving together in this migration -- is unaffected by
`ALTER TABLE ... SET SCHEMA` (see migration `0032`'s own docstring for
why). This migration moves tables; it does not touch a single
`ForeignKeyConstraint` definition.

**Order.** Tables are moved in dependency order (a referenced table
before what composite-FK-references it) purely for this file's own
readability, matching migration `0034`'s identical convention -- not
because PostgreSQL requires it.

Every route Public SIE ever exposed over this cluster (`app/api/v1/
intelligence_decisions.py`, `intelligence_outcomes.py`,
`intelligence_learning_candidates.py`, `organizational_memory.py`)
already returns `HTTP 501` unconditionally, per M43-IP-03 -- this
migration changes where the tables physically live, not what any
endpoint does.
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0035'
down_revision: Union[str, None] = '0034'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TABLES = (
    "hse_expert_reviews",
    "terminology_mapping_decisions",
    "intelligence_decisions",
    "intelligence_outcomes",
    "intelligence_outcome_verifications",
    "intelligence_learning_candidates",
    "intelligence_learning_candidate_governance_decisions",
    "organizational_memories",
    "organizational_memory_governance_decisions",
)


def upgrade() -> None:
    for table in _TABLES:
        op.execute(f"ALTER TABLE {table} SET SCHEMA commercial_core")


def downgrade() -> None:
    for table in reversed(_TABLES):
        op.execute(f"ALTER TABLE commercial_core.{table} SET SCHEMA public")
