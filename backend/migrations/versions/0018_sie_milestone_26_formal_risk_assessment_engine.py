"""SIE Milestone 26: Formal Enterprise Risk Assessment Engine v0.2

Revision ID: 0018
Revises: 0017
Create Date: 2026-09-05

Additive/corrective extensions to the Milestone 25/25A Risk Assessment
domain, plus one new table. See `app/models/risk_assessment.py`,
`app/models/risk_assessment_history.py`, and
`app/models/risk_assessment_enums.py` for the full design rationale. No
existing table's *unrelated* data is touched; `enterprise-risk-v1`
(`app/intelligence/risk_score.py`) remains untouched.

  1. `risk_assessments` gains `reference` (nullable) and
     `assessment_type` (a new, governed, NOT NULL native enum --
     existing rows are backfilled to `'BASELINE'` before the column is
     made NOT NULL, since no existing row could have declared a type
     that didn't yet exist).
  2. `risk_assessment_status` (the existing native enum) gains one new
     value, `'ARCHIVED'` -- added via `ALTER TYPE ... ADD VALUE`, safe
     inside this migration's own transaction on PostgreSQL 12+ since no
     row is ever set to that value within this same migration.
  3. `risk_assessment_findings` gains `linked_action_id` (nullable FK to
     `safety_actions.id`, `ondelete='SET NULL'`) and
     `inherent_risk_methodology_version`/`residual_risk_methodology_version`
     (nullable, backfilled to `'risk-assessment-v1'` for every existing
     row that already carries the corresponding rating -- never
     backfilled for an unrated row, which stays `NULL` exactly like a
     freshly-created one would).
  4. A new table, `risk_assessment_history` -- purely additive, created
     via `op.create_table()` (auto-creates nothing enum-typed; every
     column here is a plain string, mirroring `safety_action_history`'s
     own convention).

**Downgrade of the `ARCHIVED` enum value.** PostgreSQL has no `ALTER
TYPE ... DROP VALUE`. Downgrading therefore rebuilds
`risk_assessment_status` without it via the standard rename-old/create-
new/cast/drop-old sequence -- refusing (via an explicit `RuntimeError`,
never a silent cast failure) if any `risk_assessments` row is currently
`ARCHIVED`, since that status has no meaning in the schema being
downgraded to.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0018'
down_revision: Union[str, None] = '0017'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ASSESSMENT_TYPE_VALUES = ('BASELINE', 'PERIODIC', 'INCIDENT_TRIGGERED', 'CHANGE_TRIGGERED', 'TARGETED')
_RISK_ASSESSMENT_CALCULATION_VERSION = 'risk-assessment-v1'


def upgrade() -> None:
    bind = op.get_bind()

    # --- 1. risk_assessments: reference + assessment_type ---------------------------------
    op.add_column('risk_assessments', sa.Column('reference', sa.String(length=100), nullable=True))

    assessment_type_enum = sa.Enum(*_ASSESSMENT_TYPE_VALUES, name='risk_assessment_type')
    assessment_type_enum.create(bind, checkfirst=True)
    op.add_column('risk_assessments', sa.Column('assessment_type', assessment_type_enum, nullable=True))
    bind.execute(sa.text("UPDATE risk_assessments SET assessment_type = 'BASELINE' WHERE assessment_type IS NULL"))
    op.alter_column('risk_assessments', 'assessment_type', nullable=False)

    # --- 2. risk_assessment_status: add ARCHIVED -------------------------------------------
    op.execute("ALTER TYPE risk_assessment_status ADD VALUE IF NOT EXISTS 'ARCHIVED'")

    # --- 3. risk_assessment_findings: linked_action_id + methodology-version snapshots -----
    op.add_column('risk_assessment_findings', sa.Column('linked_action_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_risk_assessment_findings_linked_action_id', 'risk_assessment_findings', 'safety_actions',
        ['linked_action_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        op.f('ix_risk_assessment_findings_linked_action_id'), 'risk_assessment_findings', ['linked_action_id'],
        unique=False,
    )

    op.add_column(
        'risk_assessment_findings', sa.Column('inherent_risk_methodology_version', sa.String(length=50), nullable=True)
    )
    op.add_column(
        'risk_assessment_findings', sa.Column('residual_risk_methodology_version', sa.String(length=50), nullable=True)
    )
    bind.execute(
        sa.text(
            "UPDATE risk_assessment_findings SET inherent_risk_methodology_version = :version "
            "WHERE inherent_risk_score IS NOT NULL"
        ),
        {"version": _RISK_ASSESSMENT_CALCULATION_VERSION},
    )
    bind.execute(
        sa.text(
            "UPDATE risk_assessment_findings SET residual_risk_methodology_version = :version "
            "WHERE residual_risk_score IS NOT NULL"
        ),
        {"version": _RISK_ASSESSMENT_CALCULATION_VERSION},
    )

    # --- 4. risk_assessment_history (new table) --------------------------------------------
    op.create_table(
        'risk_assessment_history',
        sa.Column('assessment_id', sa.Uuid(), nullable=False),
        sa.Column('finding_id', sa.Uuid(), nullable=True),
        sa.Column('change_type', sa.String(length=50), nullable=False),
        sa.Column('from_status', sa.String(length=30), nullable=True),
        sa.Column('to_status', sa.String(length=30), nullable=True),
        sa.Column('changed_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('changed_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('request_id', sa.String(length=64), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['assessment_id'], ['risk_assessments.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['changed_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['finding_id'], ['risk_assessment_findings.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_risk_assessment_history_assessment', 'risk_assessment_history', ['assessment_id'], unique=False)
    op.create_index('ix_risk_assessment_history_finding', 'risk_assessment_history', ['finding_id'], unique=False)
    op.create_index(
        op.f('ix_risk_assessment_history_organization_id'), 'risk_assessment_history', ['organization_id'], unique=False
    )


def downgrade() -> None:
    bind = op.get_bind()

    # --- Reverse of step 4 ------------------------------------------------------------------
    op.drop_index(op.f('ix_risk_assessment_history_organization_id'), table_name='risk_assessment_history')
    op.drop_index('ix_risk_assessment_history_finding', table_name='risk_assessment_history')
    op.drop_index('ix_risk_assessment_history_assessment', table_name='risk_assessment_history')
    op.drop_table('risk_assessment_history')

    # --- Reverse of step 3 -------------------------------------------------------------------
    op.drop_column('risk_assessment_findings', 'residual_risk_methodology_version')
    op.drop_column('risk_assessment_findings', 'inherent_risk_methodology_version')
    op.drop_index(op.f('ix_risk_assessment_findings_linked_action_id'), table_name='risk_assessment_findings')
    op.drop_constraint('fk_risk_assessment_findings_linked_action_id', 'risk_assessment_findings', type_='foreignkey')
    op.drop_column('risk_assessment_findings', 'linked_action_id')

    # --- Reverse of step 2: rebuild risk_assessment_status without ARCHIVED -----------------
    archived_count = bind.execute(sa.text("SELECT count(*) FROM risk_assessments WHERE status = 'ARCHIVED'")).scalar_one()
    if archived_count:
        raise RuntimeError(
            f"Migration 0018 downgrade: {archived_count} risk_assessments row(s) have status='ARCHIVED', which "
            "does not exist prior to this migration -- cannot downgrade while such data exists."
        )
    op.execute("ALTER TYPE risk_assessment_status RENAME TO risk_assessment_status_old")
    op.execute("CREATE TYPE risk_assessment_status AS ENUM ('DRAFT', 'IN_REVIEW', 'APPROVED', 'SUPERSEDED')")
    op.execute(
        "ALTER TABLE risk_assessments ALTER COLUMN status TYPE risk_assessment_status "
        "USING status::text::risk_assessment_status"
    )
    op.execute("DROP TYPE risk_assessment_status_old")

    # --- Reverse of step 1 -------------------------------------------------------------------
    op.drop_column('risk_assessments', 'assessment_type')
    sa.Enum(name='risk_assessment_type').drop(bind, checkfirst=True)
    op.drop_column('risk_assessments', 'reference')
