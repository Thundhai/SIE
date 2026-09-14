"""SIE Milestone 43A pre-merge audit correction (Finding 1) — concurrency
tests for `app/services/governing_standard_service.py::_lock_standard_
selection()`.

**PostgreSQL-integration tests — see tests/postgres_support.py.** The
race this guards against (two concurrent first-time selection/retirement
requests for the same `(organization_id, standard_id)` pair both reading
"no current selection" under READ COMMITTED before either commits,
producing two redundant events) is structurally impossible to reproduce
against the SQLite `db_session` fixture every other test in this suite
uses -- a single-threaded, single-connection in-memory database has no
independent concurrent transaction to race against in the first place.
These tests run genuine Python threads, each with its own session bound
to its own real PostgreSQL connection, mirroring `test_migrations.py`'s
own "this class of defect can only be caught for real" precedent.
Skipped automatically (not failed) when no real PostgreSQL server is
reachable.
"""

from __future__ import annotations

import threading

from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from app.models.enums import ScopeType, VerificationStatus
from app.models.governing_standard import GoverningStandard
from app.models.governing_standard_enums import GoverningStandardType, OrganizationGoverningStandardStatus
from app.services.governing_standard_service import (
    list_selection_history,
    retire_governing_standard,
    select_governing_standard,
    selection_mutation_transaction,
)
from tests.intelligence_test_helpers import make_org
from tests.postgres_support import requires_postgres


def _make_global_standard(session: Session, *, name: str = "ISO 45001 (concurrency test)") -> GoverningStandard:
    standard = GoverningStandard(
        scope_type=ScopeType.GLOBAL,
        organization_id=None,
        name=name,
        short_description="Occupational health and safety management systems.",
        issuing_organization="ISO",
        standard_type=GoverningStandardType.INTERNATIONAL_STANDARD,
        regions=[],
        industry_sectors=[],
        verification_status=VerificationStatus.VERIFIED,
        is_active=True,
    )
    session.add(standard)
    session.commit()
    return standard


def _new_session(engine) -> Session:
    """A genuinely independent Session -- its own connection checked out
    from the shared engine's pool, its own transaction -- never the
    fixture's own `pg_session`, which every thread here must NOT share
    (sharing one Session across threads would serialize by accident,
    proving nothing about the real fix)."""
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)()


@requires_postgres
def test_concurrent_first_time_selection_creates_only_one_current_event(pg_session):
    """The core audit-finding regression test: two threads attempt to
    select the *same*, never-before-selected standard for the *same*
    organization at the same time. Without `_lock_standard_selection()`,
    both can observe `resolve_current_selection() is None` before either
    commits and both insert a `SELECTED` row. With it, the second
    thread's lock acquisition blocks until the first commits, then
    correctly observes the first's row and returns it unchanged."""
    engine = pg_session.get_bind()
    org = make_org(pg_session, name="Concurrency Org A")
    standard = _make_global_standard(pg_session)
    organization_id, standard_id = org.id, standard.id

    barrier = threading.Barrier(2)
    results: dict[str, tuple] = {}
    errors: list[tuple[str, Exception]] = []

    def _attempt(label: str) -> None:
        session = _new_session(engine)
        try:
            barrier.wait(timeout=10)  # start both threads' critical section as close together as possible
            with selection_mutation_transaction(session):
                row, created = select_governing_standard(
                    session,
                    organization_id=organization_id,
                    standard_id=standard_id,
                    effective_date=None,
                    rationale=f"selected by thread {label}",
                    configured_by_user_id=None,
                    configured_by_api_client_id=None,
                    request_id=None,
                )
            results[label] = (row.id, created)
        except Exception as exc:  # noqa: BLE001 -- captured for the assertion below, never swallowed
            errors.append((label, exc))
        finally:
            session.close()

    threads = [threading.Thread(target=_attempt, args=(label,)) for label in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not errors, f"unexpected errors from concurrent first-time selection: {errors}"
    assert set(results) == {"A", "B"}, f"one or both threads never completed: {results}"

    # The lock forces full serialization of the check-then-insert:
    # exactly one thread actually created a new SELECTED event, and the
    # other observed that same event and returned it unchanged -- never
    # two different row ids, regardless of scheduling.
    row_ids = {row_id for row_id, _created in results.values()}
    created_flags = sorted(created for _row_id, created in results.values())
    assert len(row_ids) == 1, f"expected both threads to agree on one current row, got {results}"
    assert created_flags == [False, True], f"expected exactly one thread to create the event, got {results}"

    # And the append-only history itself carries exactly one SELECTED
    # event for this pair -- not two redundant rows silently sitting in
    # the audit trail.
    history, _total = list_selection_history(pg_session, organization_id=organization_id)
    selected_events = [
        h for h in history if h.standard_id == standard_id and h.status == OrganizationGoverningStandardStatus.SELECTED
    ]
    assert len(selected_events) == 1, f"expected exactly one SELECTED event in history, got {len(selected_events)}"


@requires_postgres
def test_concurrent_retire_attempts_do_not_duplicate_the_retirement_event(pg_session):
    """Same lock, same mechanism, the other write path: two threads race
    to retire the *same already-selected* standard at the same time.
    Exactly one succeeds and creates the RETIRED event; the other,
    serialized behind it, correctly observes the standard is no longer
    SELECTED and raises the existing 422 ("nothing to retire") -- never
    a second, redundant RETIRED event."""
    engine = pg_session.get_bind()
    org = make_org(pg_session, name="Concurrency Org B")
    standard = _make_global_standard(pg_session, name="OSHA 1910 (concurrency test)")
    organization_id, standard_id = org.id, standard.id

    with selection_mutation_transaction(pg_session):
        select_governing_standard(
            pg_session,
            organization_id=organization_id,
            standard_id=standard_id,
            effective_date=None,
            rationale="initial selection",
            configured_by_user_id=None,
            configured_by_api_client_id=None,
            request_id=None,
        )

    barrier = threading.Barrier(2)
    results: dict[str, object] = {}

    def _attempt(label: str) -> None:
        session = _new_session(engine)
        try:
            barrier.wait(timeout=10)
            with selection_mutation_transaction(session):
                row = retire_governing_standard(
                    session,
                    organization_id=organization_id,
                    standard_id=standard_id,
                    retirement_date=None,
                    rationale=f"retired by thread {label}",
                    configured_by_user_id=None,
                    configured_by_api_client_id=None,
                    request_id=None,
                )
            results[label] = ("retired", row.id)
        except HTTPException as exc:
            results[label] = ("rejected", exc.status_code)
        finally:
            session.close()

    threads = [threading.Thread(target=_attempt, args=(label,)) for label in ("A", "B")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert set(results) == {"A", "B"}, f"one or both threads never completed: {results}"
    outcomes = sorted(results.values())
    retired_outcomes = [o for o in outcomes if o[0] == "retired"]
    rejected_outcomes = [o for o in outcomes if o[0] == "rejected"]
    assert len(retired_outcomes) == 1, f"expected exactly one thread to retire the standard, got {results}"
    assert len(rejected_outcomes) == 1, f"expected exactly one thread to be correctly rejected, got {results}"
    assert rejected_outcomes[0][1] == 422

    history, _total = list_selection_history(pg_session, organization_id=organization_id)
    retired_events = [
        h for h in history if h.standard_id == standard_id and h.status == OrganizationGoverningStandardStatus.RETIRED
    ]
    assert len(retired_events) == 1, f"expected exactly one RETIRED event in history, got {len(retired_events)}"
