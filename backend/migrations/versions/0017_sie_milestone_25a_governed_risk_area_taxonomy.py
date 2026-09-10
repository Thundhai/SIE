"""SIE Milestone 25A: Governed Risk-Area & Organization-Extensible Risk
Taxonomy v0.1

Revision ID: 0017
Revises: 0016
Create Date: 2026-09-05

Corrective/additive to Milestone 25 (migration 0016): replaces the closed
`RiskArea` Python/native-enum vocabulary with the existing, governed
`OntologyConcept` architecture (Milestone 15) as the one authoritative
risk-area taxonomy. See `app/models/risk_assessment.py`,
`app/models/ontology_concept.py`, and
`app/risk_assessment/risk_area_ontology_seed.py` for the full design
rationale. No existing table's *unrelated* data is touched; migration
0016 is not modified; `enterprise-risk-v1`
(`app/intelligence/risk_score.py`) remains untouched.

Two extensions, both additive:

  1. `ontology_concepts` gains `organization_id` (nullable -- `NULL` =
     GLOBAL, Milestone 15's original and still-default scope; set = an
     organization's own extension of the ontology, Milestone 25A) and
     `is_risk_area_eligible` (boolean, governed, explicit -- see that
     model's own docstring). The old 3-column unique constraint
     (`layer`, `parent_domain`, `concept_key`) is replaced with a
     4-column one that also includes `organization_id`.

  2. `risk_assessment_findings.risk_area` (a closed native enum,
     11 values) is replaced with `risk_area_concept_id` (a FK to
     `ontology_concepts.id`, `ondelete='RESTRICT'`) and
     `risk_area_ontology_version` (an integer snapshot of the concept's
     `ontology_version` at the moment the finding was created -- see
     `app/models/risk_assessment.py`'s own "historical integrity"
     docstring section).

**Existing-data migration (items 21-22) -- no data loss, no invented
mapping.** Before dropping the old `risk_area` column, this migration:

  a. Seeds (or, if `config/enterprise_ontology_concepts_v1.json` was
     already applied via `ontology_concept_artifact_service.py`, updates
     in place to flag `is_risk_area_eligible=True`) exactly the 11
     `OntologyConcept` rows `app/risk_assessment/risk_area_ontology_seed.py`
     declares -- one GLOBAL, `APPROVED` concept per original `RiskArea`
     member, deterministically. If an existing row at one of these
     scope keys is not `APPROVED`, this migration stops with a
     `RuntimeError` rather than silently reinterpreting an existing
     governance decision.
  b. Backfills every existing `risk_assessment_findings` row's new
     `risk_area_concept_id`/`risk_area_ontology_version` columns from its
     old `risk_area` enum value, via the same seed list's own
     `legacy_risk_area` mapping. Every one of the 11 possible enum values
     has a corresponding seeded concept, so no existing finding is ever
     left unmapped; a `risk_area` value with no known mapping (impossible
     today, since the column is itself a closed native enum with exactly
     these 11 values, but checked explicitly regardless) stops the
     migration with a `RuntimeError` rather than guessing (item 22).

Only after every existing row is backfilled do the new columns become
`NOT NULL` and the old `risk_area` column (and its native enum type) is
dropped.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.risk_assessment.risk_area_ontology_seed import (
    RISK_AREA_SEED_CONCEPTS,
    RISK_AREA_SEED_ONTOLOGY_VERSION,
)

# revision identifiers, used by Alembic.
revision: str = '0017'
down_revision: Union[str, None] = '0016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_LEGACY_RISK_AREA_VALUES = (
    'INCIDENT_SAFETY', 'VEHICLE_SAFETY', 'WORKING_AT_HEIGHT', 'PPE_COMPLIANCE', 'ELECTRICAL_SAFETY',
    'LIFTING_OPERATIONS', 'ENVIRONMENTAL', 'EQUIPMENT_SAFETY', 'PROCEDURE_VIOLATION', 'FIRE_SAFETY',
    'EMERGENCY_PREPAREDNESS',
)


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. ontology_concepts: organization scoping + risk-area eligibility ---------------
    op.add_column('ontology_concepts', sa.Column('organization_id', sa.Uuid(), nullable=True))
    op.add_column(
        'ontology_concepts',
        sa.Column('is_risk_area_eligible', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_foreign_key(
        'fk_ontology_concepts_organization_id', 'ontology_concepts', 'organizations',
        ['organization_id'], ['id'], ondelete='CASCADE',
    )
    op.create_index(op.f('ix_ontology_concepts_organization_id'), 'ontology_concepts', ['organization_id'], unique=False)
    op.create_index(
        op.f('ix_ontology_concepts_is_risk_area_eligible'), 'ontology_concepts', ['is_risk_area_eligible'], unique=False
    )
    op.drop_constraint('uq_ontology_concepts_scope', 'ontology_concepts', type_='unique')
    op.create_unique_constraint(
        'uq_ontology_concepts_scope', 'ontology_concepts', ['organization_id', 'layer', 'parent_domain', 'concept_key']
    )
    # The server_default above exists only so the ADD COLUMN itself is a
    # single, non-locking statement against any pre-existing rows; every
    # row this migration itself inserts below sets the value explicitly,
    # and no application code path ever relies on a database-level
    # default (mirrors this codebase's existing convention -- see e.g.
    # migration 0005's identical "drop the default once backfilled" note).
    op.alter_column('ontology_concepts', 'is_risk_area_eligible', server_default=None)

    # --- 2. Seed (or flag-in-place) the 11 governed risk-area concepts -------------------
    now = datetime.now(timezone.utc)
    concept_ids: dict[tuple, uuid.UUID] = {}
    for seed in RISK_AREA_SEED_CONCEPTS:
        existing = bind.execute(
            sa.text(
                "SELECT id, status FROM ontology_concepts WHERE organization_id IS NULL "
                "AND layer = :layer AND parent_domain IS NOT DISTINCT FROM :parent_domain "
                "AND concept_key = :concept_key"
            ),
            {"layer": seed.layer, "parent_domain": seed.parent_domain, "concept_key": seed.concept_key},
        ).mappings().first()

        scope_key = (seed.layer, seed.parent_domain, seed.concept_key)
        if existing is not None:
            if existing["status"] != "APPROVED":
                raise RuntimeError(
                    f"Migration 0017: an existing ontology concept at layer={seed.layer!r} "
                    f"parent_domain={seed.parent_domain!r} concept_key={seed.concept_key!r} "
                    f"(id={existing['id']}) is {existing['status']!r}, not APPROVED -- refusing to mark it "
                    "risk-area-eligible. Stopping rather than silently overriding an existing governance "
                    "decision; resolve manually through ontology governance before re-running this migration."
                )
            concept_ids[scope_key] = existing["id"]
            bind.execute(
                sa.text("UPDATE ontology_concepts SET is_risk_area_eligible = TRUE WHERE id = :id"),
                {"id": existing["id"]},
            )
        else:
            new_id = uuid.uuid4()
            concept_ids[scope_key] = new_id
            bind.execute(
                sa.text(
                    "INSERT INTO ontology_concepts "
                    "(id, organization_id, layer, parent_domain, concept_key, definition, justification, "
                    "status, ontology_version, is_risk_area_eligible, proposed_by_user_id, proposed_at, "
                    "reviewer_user_id, decided_at, created_at, updated_at) "
                    "VALUES (:id, NULL, :layer, :parent_domain, :concept_key, :definition, :justification, "
                    "'APPROVED', :ontology_version, TRUE, NULL, NULL, NULL, NULL, :now, :now)"
                ),
                {
                    "id": new_id, "layer": seed.layer, "parent_domain": seed.parent_domain,
                    "concept_key": seed.concept_key, "definition": seed.definition,
                    "justification": seed.justification, "ontology_version": RISK_AREA_SEED_ONTOLOGY_VERSION,
                    "now": now,
                },
            )

    # --- 3. risk_assessment_findings: new columns (nullable at first, to backfill) -------
    op.add_column('risk_assessment_findings', sa.Column('risk_area_concept_id', sa.Uuid(), nullable=True))
    op.add_column('risk_assessment_findings', sa.Column('risk_area_ontology_version', sa.Integer(), nullable=True))

    legacy_to_scope = {seed.legacy_risk_area: (seed.layer, seed.parent_domain, seed.concept_key) for seed in RISK_AREA_SEED_CONCEPTS}
    existing_findings = bind.execute(sa.text("SELECT id, risk_area FROM risk_assessment_findings")).mappings().all()
    for row in existing_findings:
        legacy_value = row["risk_area"]
        scope_key = legacy_to_scope.get(legacy_value)
        if scope_key is None:
            raise RuntimeError(
                f"Migration 0017: risk_assessment_findings.id={row['id']} has risk_area={legacy_value!r}, "
                "which has no corresponding entry in app/risk_assessment/risk_area_ontology_seed.py -- "
                "stopping rather than silently inventing a mapping (item 22)."
            )
        bind.execute(
            sa.text(
                "UPDATE risk_assessment_findings SET risk_area_concept_id = :concept_id, "
                "risk_area_ontology_version = :ontology_version WHERE id = :id"
            ),
            {"concept_id": concept_ids[scope_key], "ontology_version": RISK_AREA_SEED_ONTOLOGY_VERSION, "id": row["id"]},
        )

    # --- 4. Enforce NOT NULL now that every existing row is backfilled -------------------
    op.alter_column('risk_assessment_findings', 'risk_area_concept_id', nullable=False)
    op.alter_column('risk_assessment_findings', 'risk_area_ontology_version', nullable=False)

    # --- 5. FK + indexes for the new column; retire the old ones ------------------------
    op.create_foreign_key(
        'fk_risk_assessment_findings_risk_area_concept_id', 'risk_assessment_findings', 'ontology_concepts',
        ['risk_area_concept_id'], ['id'], ondelete='RESTRICT',
    )
    op.create_index(
        op.f('ix_risk_assessment_findings_risk_area_concept_id'), 'risk_assessment_findings',
        ['risk_area_concept_id'], unique=False,
    )
    op.drop_index('ix_risk_assessment_findings_org_risk_area', table_name='risk_assessment_findings')
    op.create_index(
        'ix_risk_assessment_findings_org_risk_area_concept', 'risk_assessment_findings',
        ['organization_id', 'risk_area_concept_id'], unique=False,
    )

    # --- 6. Drop the old column and its now-unused native enum type ---------------------
    op.drop_column('risk_assessment_findings', 'risk_area')
    sa.Enum(name='risk_area').drop(bind, checkfirst=True)


def downgrade() -> None:
    bind = op.get_bind()

    # --- Reverse of step 6: recreate the old risk_area enum column ----------------------
    risk_area_enum = sa.Enum(*_LEGACY_RISK_AREA_VALUES, name='risk_area')
    risk_area_enum.create(bind, checkfirst=True)
    op.add_column('risk_assessment_findings', sa.Column('risk_area', risk_area_enum, nullable=True))

    # Reverse-map each finding's risk_area_concept_id back to its legacy
    # risk_area value via the same seed list -- only ever meaningful for a
    # finding whose concept is one of the 11 originally-seeded GLOBAL
    # concepts; a finding created after upgrading to 0017 against some
    # other (e.g. organization-specific) concept has no legacy equivalent
    # to downgrade to, and this migration stops rather than guessing one,
    # exactly like upgrade()'s own "stop and report the mismatch" (item 22).
    scope_to_legacy = {(seed.layer, seed.parent_domain, seed.concept_key): seed.legacy_risk_area for seed in RISK_AREA_SEED_CONCEPTS}
    rows = bind.execute(
        sa.text(
            "SELECT f.id AS finding_id, c.layer AS layer, c.parent_domain AS parent_domain, "
            "c.concept_key AS concept_key, c.organization_id AS organization_id "
            "FROM risk_assessment_findings f JOIN ontology_concepts c ON c.id = f.risk_area_concept_id"
        )
    ).mappings().all()
    for row in rows:
        if row["organization_id"] is not None:
            raise RuntimeError(
                f"Migration 0017 downgrade: risk_assessment_findings.id={row['finding_id']} references an "
                "organization-specific ontology concept, which has no legacy RiskArea equivalent -- cannot "
                "downgrade past Milestone 25A while such a finding exists."
            )
        scope_key = (row["layer"], row["parent_domain"], row["concept_key"])
        legacy_value = scope_to_legacy.get(scope_key)
        if legacy_value is None:
            raise RuntimeError(
                f"Migration 0017 downgrade: risk_assessment_findings.id={row['finding_id']} references "
                f"ontology concept {scope_key!r}, which is not one of the 11 originally-seeded risk areas -- "
                "cannot downgrade past Milestone 25A while such a finding exists."
            )
        bind.execute(
            sa.text("UPDATE risk_assessment_findings SET risk_area = :risk_area WHERE id = :id"),
            {"risk_area": legacy_value, "id": row["finding_id"]},
        )

    op.alter_column('risk_assessment_findings', 'risk_area', nullable=False)

    # --- Reverse of step 5 ----------------------------------------------------------------
    op.drop_index('ix_risk_assessment_findings_org_risk_area_concept', table_name='risk_assessment_findings')
    op.create_index(
        'ix_risk_assessment_findings_org_risk_area', 'risk_assessment_findings', ['organization_id', 'risk_area'],
        unique=False,
    )
    op.drop_index(op.f('ix_risk_assessment_findings_risk_area_concept_id'), table_name='risk_assessment_findings')
    op.drop_constraint('fk_risk_assessment_findings_risk_area_concept_id', 'risk_assessment_findings', type_='foreignkey')

    # --- Reverse of steps 3-4 --------------------------------------------------------------
    op.drop_column('risk_assessment_findings', 'risk_area_ontology_version')
    op.drop_column('risk_assessment_findings', 'risk_area_concept_id')

    # --- Reverse of step 2: nothing to undo structurally -- the seeded concept rows are
    # simply left in place (harmless, and `ontology_concepts` itself is about to lose the
    # columns that make them risk-area-eligible/org-scoped anyway, immediately below).

    # --- Reverse of step 1 ----------------------------------------------------------------
    op.drop_constraint('uq_ontology_concepts_scope', 'ontology_concepts', type_='unique')
    op.create_unique_constraint(
        'uq_ontology_concepts_scope', 'ontology_concepts', ['layer', 'parent_domain', 'concept_key']
    )
    op.drop_index(op.f('ix_ontology_concepts_is_risk_area_eligible'), table_name='ontology_concepts')
    op.drop_index(op.f('ix_ontology_concepts_organization_id'), table_name='ontology_concepts')
    op.drop_constraint('fk_ontology_concepts_organization_id', 'ontology_concepts', type_='foreignkey')
    op.drop_column('ontology_concepts', 'is_risk_area_eligible')
    op.drop_column('ontology_concepts', 'organization_id')
