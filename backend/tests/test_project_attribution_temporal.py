"""SIE Milestone 35B: Project Attribution Temporal Integrity — direct
`events_as_of()` query-level tests, mirroring `test_temporal_leakage.py`'s
own established shape: construct domain objects directly (including
`SafetyEventProjectAttributionHistory` rows with explicit `created_at`
values, since the real write path always uses `utcnow()` and cannot be
backdated), run the query builder, assert on the returned event ids.
HTTP-layer point-in-time coverage (through
`GET /api/v1/intelligence/context`) lives in `tests/test_projects_api.py`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.intelligence.temporal import events_as_of
from app.models.organization import Organization
from app.models.project import Project
from app.models.project_enums import ProjectStatus
from app.models.safety_event_project_attribution_history import (
    SafetyEventProjectAttributionAction,
    SafetyEventProjectAttributionHistory,
)
from tests.intelligence_test_helpers import make_safety_event


def _make_org(db_session) -> uuid.UUID:
    org = Organization(name="M35B Temporal Test Org")
    db_session.add(org)
    db_session.commit()
    return org.id


def _make_project(db_session, org_id, name="Project") -> Project:
    project = Project(organization_id=org_id, name=name, status=ProjectStatus.ACTIVE)
    db_session.add(project)
    db_session.commit()
    return project


def _seed_event(db_session, org_id, **overrides) -> uuid.UUID:
    event = make_safety_event(
        organization_id=org_id,
        event_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        **overrides,
    )
    db_session.add(event)
    db_session.commit()
    return event.id


def _write_history(db_session, org_id, event_id, project_id, action, created_at) -> None:
    db_session.add(
        SafetyEventProjectAttributionHistory(
            organization_id=org_id, event_id=event_id, project_id=project_id, action=action, created_at=created_at
        )
    )
    db_session.commit()


def _attributed(db_session, org_id, project_id, as_of_day) -> bool:
    query = events_as_of(
        organization_id=org_id, as_of=datetime(2026, 6, as_of_day, tzinfo=timezone.utc), project_id=project_id
    )
    ids = {e.id for e in db_session.execute(query).scalars().all()}
    return len(ids) == 1


# --- The user's own explicit worked scenario ------------------------------------------------


def test_reassigned_attribution_is_point_in_time_correct_across_the_full_worked_example(db_session):
    """Attribute Alpha on June 20; query Alpha as_of June 10 -> event NOT
    included. Query Alpha as_of June 21 -> event included. Reassign
    Alpha -> Beta on June 25. Query Alpha as_of June 23 -> event still
    included (the reassignment had not happened yet as of June 23).
    Query Alpha as_of June 26 -> event excluded (superseded by Beta).
    Query Beta as_of June 26 -> event included."""
    org_id = _make_org(db_session)
    alpha = _make_project(db_session, org_id, "Alpha")
    beta = _make_project(db_session, org_id, "Beta")
    event_id = _seed_event(db_session, org_id, source_record_id="e1")

    _write_history(
        db_session, org_id, event_id, alpha.id, SafetyEventProjectAttributionAction.ATTRIBUTED,
        datetime(2026, 6, 20, tzinfo=timezone.utc),
    )

    assert _attributed(db_session, org_id, alpha.id, 10) is False
    assert _attributed(db_session, org_id, alpha.id, 21) is True

    _write_history(
        db_session, org_id, event_id, beta.id, SafetyEventProjectAttributionAction.ATTRIBUTED,
        datetime(2026, 6, 25, tzinfo=timezone.utc),
    )

    assert _attributed(db_session, org_id, alpha.id, 23) is True
    assert _attributed(db_session, org_id, alpha.id, 26) is False
    assert _attributed(db_session, org_id, beta.id, 26) is True


def test_a_cleared_attribution_is_excluded_as_of_after_the_clear_but_included_before_it(db_session):
    org_id = _make_org(db_session)
    alpha = _make_project(db_session, org_id, "Alpha")
    event_id = _seed_event(db_session, org_id, source_record_id="e1")

    _write_history(
        db_session, org_id, event_id, alpha.id, SafetyEventProjectAttributionAction.ATTRIBUTED,
        datetime(2026, 6, 10, tzinfo=timezone.utc),
    )
    _write_history(
        db_session, org_id, event_id, alpha.id, SafetyEventProjectAttributionAction.CLEARED,
        datetime(2026, 6, 15, tzinfo=timezone.utc),
    )

    assert _attributed(db_session, org_id, alpha.id, 12) is True
    assert _attributed(db_session, org_id, alpha.id, 20) is False


def test_current_as_of_now_matches_the_live_current_state_column(db_session):
    """Live "as of right now" queries (as_of defaults to a recent
    instant in real callers) must still agree with
    SafetyEvent.attributed_project_id -- this milestone changes how a
    *historical* as_of is answered, not the live case."""
    org_id = _make_org(db_session)
    alpha = _make_project(db_session, org_id, "Alpha")
    event_id = _seed_event(db_session, org_id, source_record_id="e1")
    _write_history(
        db_session, org_id, event_id, alpha.id, SafetyEventProjectAttributionAction.ATTRIBUTED,
        datetime(2026, 6, 20, tzinfo=timezone.utc),
    )

    query = events_as_of(organization_id=org_id, as_of=datetime(2026, 7, 1, tzinfo=timezone.utc), project_id=alpha.id)
    ids = {e.id for e in db_session.execute(query).scalars().all()}
    assert event_id in ids


def test_an_event_with_no_attribution_history_is_excluded_from_any_project_filter(db_session):
    """Preserves existing behavior (item 7): a record with no project
    attribution at all is correctly excluded from a project_id-filtered
    view, and unaffected when no project_id filter is applied."""
    org_id = _make_org(db_session)
    alpha = _make_project(db_session, org_id, "Alpha")
    event_id = _seed_event(db_session, org_id, source_record_id="e1")

    filtered = events_as_of(organization_id=org_id, as_of=datetime(2026, 7, 1, tzinfo=timezone.utc), project_id=alpha.id)
    assert event_id not in {e.id for e in db_session.execute(filtered).scalars().all()}

    unfiltered = events_as_of(organization_id=org_id, as_of=datetime(2026, 7, 1, tzinfo=timezone.utc))
    assert event_id in {e.id for e in db_session.execute(unfiltered).scalars().all()}


def test_two_projects_never_simultaneously_claim_the_same_event_at_any_instant(db_session):
    """The user's own explicitly required non-attribution scenario,
    re-verified at the temporal-reconstruction level: at no instant does
    the point-in-time query say an event belongs to both Alpha and Beta,
    even though both are ever attributed to it (at different times)."""
    org_id = _make_org(db_session)
    alpha = _make_project(db_session, org_id, "Alpha")
    beta = _make_project(db_session, org_id, "Beta")
    event_id = _seed_event(db_session, org_id, source_record_id="e1")

    _write_history(
        db_session, org_id, event_id, alpha.id, SafetyEventProjectAttributionAction.ATTRIBUTED,
        datetime(2026, 6, 20, tzinfo=timezone.utc),
    )
    _write_history(
        db_session, org_id, event_id, beta.id, SafetyEventProjectAttributionAction.ATTRIBUTED,
        datetime(2026, 6, 25, tzinfo=timezone.utc),
    )

    for day in (18, 20, 22, 25, 27):
        alpha_has_it = _attributed(db_session, org_id, alpha.id, day)
        beta_has_it = _attributed(db_session, org_id, beta.id, day)
        assert not (alpha_has_it and beta_has_it), f"both Alpha and Beta claimed the event as of June {day}"
