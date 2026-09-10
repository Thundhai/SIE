"""SIE Milestone 29: Enterprise Risk Assessment Evidence & Control
Effectiveness Foundation v0.1

Revision ID: 0020
Revises: 0019
Create Date: 2026-09-07

Purely additive, exactly like every other risk-assessment-domain
migration in this series:

1. Two native enum types gain new, additive values (`ALTER TYPE ... ADD
   VALUE IF NOT EXISTS`, the same mechanism migration 0018 already used
   for `RiskAssessmentStatus.ARCHIVED`): `risk_control_type` gains
   `OTHER`, `risk_control_status` gains `PARTIALLY_IMPLEMENTED` and
   `NOT_VERIFIED`. No existing value's meaning changes.
2. `risk_assessment_controls` gains three new, nullable columns --
   `effectiveness_rationale`, `assessed_at`, `assessed_by_user_id` -- all
   `NULL` on every pre-existing row (an effectiveness value set before
   this milestone carries no rationale/attribution, which is the honest
   state -- see `app/models/risk_assessment.py`'s own note).
3. A new table, `risk_assessment_control_evidence`, links a control to
   an existing `risk_assessment_finding_evidence` row -- never a second,
   duplicated evidence-payload table.
4. `risk_assessment_history` gains one new, nullable `control_id` column
   (`ON DELETE SET NULL`) so control lifecycle/effectiveness events are
   traceable the same way finding events already are.

No existing table, column, row, or type value is altered or removed.
`linked_action_id`/`RiskAssessmentFindingAction`/every Milestone 25-28
table and column are completely untouched. Downgrade guards against data
loss: it refuses (raising `RuntimeError`, mirroring migration 0018's own
`ARCHIVED` downgrade guard) if any `risk_assessment_controls` row
currently holds `control_type='OTHER'` or
`status IN ('PARTIALLY_IMPLEMENTED', 'NOT_VERIFIED')`, since a native
Postgres enum value cannot be selectively dropped -- only rebuilt via a
full type swap.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0020'
down_revision: Union[str, None] = '0019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Step 1: additive enum values --------------------------------------------------------
    op.execute("ALTER TYPE risk_control_type ADD VALUE IF NOT EXISTS 'OTHER'")
    op.execute("ALTER TYPE risk_control_status ADD VALUE IF NOT EXISTS 'PARTIALLY_IMPLEMENTED'")
    op.execute("ALTER TYPE risk_control_status ADD VALUE IF NOT EXISTS 'NOT_VERIFIED'")

    # --- Step 2: risk_assessment_controls gains effectiveness assessment attribution ---------
    op.add_column('risk_assessment_controls', sa.Column('effectiveness_rationale', sa.Text(), nullable=True))
    op.add_column(
        'risk_assessment_controls', sa.Column('assessed_at', sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column('risk_assessment_controls', sa.Column('assessed_by_user_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_risk_assessment_controls_assessed_by_user_id', 'risk_assessment_controls', 'users',
        ['assessed_by_user_id'], ['id'], ondelete='SET NULL',
    )

    # --- Step 3: risk_assessment_control_evidence (new link table) --------------------------
    op.create_table(
        'risk_assessment_control_evidence',
        sa.Column('control_id', sa.Uuid(), nullable=False),
        sa.Column('finding_evidence_id', sa.Uuid(), nullable=False),
        sa.Column('created_by_user_id', sa.Uuid(), nullable=True),
        sa.Column('created_by_api_client_id', sa.Uuid(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('id', sa.Uuid(), nullable=False),
        sa.Column('organization_id', sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(['control_id'], ['risk_assessment_controls.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_api_client_id'], ['api_clients.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['finding_evidence_id'], ['risk_assessment_finding_evidence.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['organization_id'], ['organizations.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'control_id', 'finding_evidence_id', name='uq_risk_assessment_control_evidence_control_evidence'
        ),
    )
    op.create_index(
        'ix_risk_assessment_control_evidence_control', 'risk_assessment_control_evidence', ['control_id'],
        unique=False,
    )
    op.create_index(
        'ix_risk_assessment_control_evidence_finding_evidence', 'risk_assessment_control_evidence',
        ['finding_evidence_id'], unique=False,
    )
    op.create_index(
        op.f('ix_risk_assessment_control_evidence_organization_id'), 'risk_assessment_control_evidence',
        ['organization_id'], unique=False,
    )

    # --- Step 4: risk_assessment_history gains control_id ------------------------------------
    op.add_column('risk_assessment_history', sa.Column('control_id', sa.Uuid(), nullable=True))
    op.create_foreign_key(
        'fk_risk_assessment_history_control_id', 'risk_assessment_history', 'risk_assessment_controls',
        ['control_id'], ['id'], ondelete='SET NULL',
    )
    op.create_index(
        'ix_risk_assessment_history_control', 'risk_assessment_history', ['control_id'], unique=False
    )


def downgrade() -> None:
    bind = op.get_bind()

    # --- Reverse of step 4 ---------------------------------------------------------------------
    op.drop_index('ix_risk_assessment_history_control', table_name='risk_assessment_history')
    op.drop_constraint('fk_risk_assessment_history_control_id', 'risk_assessment_history', type_='foreignkey')
    op.drop_column('risk_assessment_history', 'control_id')

    # --- Reverse of step 3 ---------------------------------------------------------------------
    op.drop_index(
        op.f('ix_risk_assessment_control_evidence_organization_id'), table_name='risk_assessment_control_evidence'
    )
    op.drop_index(
        'ix_risk_assessment_control_evidence_finding_evidence', table_name='risk_assessment_control_evidence'
    )
    op.drop_index('ix_risk_assessment_control_evidence_control', table_name='risk_assessment_control_evidence')
    op.drop_table('risk_assessment_control_evidence')

    # --- Reverse of step 2 ---------------------------------------------------------------------
    op.drop_constraint(
        'fk_risk_assessment_controls_assessed_by_user_id', 'risk_assessment_controls', type_='foreignkey'
    )
    op.drop_column('risk_assessment_controls', 'assessed_by_user_id')
    op.drop_column('risk_assessment_controls', 'assessed_at')
    op.drop_column('risk_assessment_controls', 'effectiveness_rationale')

    # --- Reverse of step 1: rebuild the two enum types without this migration's new values ----
    bad_status_count = bind.execute(
        sa.text(
            "SELECT count(*) FROM risk_assessment_controls "
            "WHERE status IN ('PARTIALLY_IMPLEMENTED', 'NOT_VERIFIED')"
        )
    ).scalar_one()
    if bad_status_count:
        raise RuntimeError(
            f"Migration 0020 downgrade: {bad_status_count} risk_assessment_controls row(s) have "
            "status IN ('PARTIALLY_IMPLEMENTED', 'NOT_VERIFIED'), which do not exist prior to this "
            "migration -- cannot downgrade while such data exists."
        )
    bad_type_count = bind.execute(
        sa.text("SELECT count(*) FROM risk_assessment_controls WHERE control_type = 'OTHER'")
    ).scalar_one()
    if bad_type_count:
        raise RuntimeError(
            f"Migration 0020 downgrade: {bad_type_count} risk_assessment_controls row(s) have "
            "control_type='OTHER', which does not exist prior to this migration -- cannot downgrade "
            "while such data exists."
        )

    op.execute("ALTER TYPE risk_control_status RENAME TO risk_control_status_old")
    op.execute("CREATE TYPE risk_control_status AS ENUM ('PROPOSED', 'IN_PLACE', 'NOT_IMPLEMENTED')")
    op.execute(
        "ALTER TABLE risk_assessment_controls ALTER COLUMN status TYPE risk_control_status "
        "USING status::text::risk_control_status"
    )
    op.execute("DROP TYPE risk_control_status_old")

    op.execute("ALTER TYPE risk_control_type RENAME TO risk_control_type_old")
    op.execute("CREATE TYPE risk_control_type AS ENUM ('ELIMINATION', 'SUBSTITUTION', 'ENGINEERING', 'ADMINISTRATIVE', 'PPE')")
    op.execute(
        "ALTER TABLE risk_assessment_controls ALTER COLUMN control_type TYPE risk_control_type "
        "USING control_type::text::risk_control_type"
    )
    op.execute("DROP TYPE risk_control_type_old")
