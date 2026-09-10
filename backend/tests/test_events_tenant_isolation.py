"""Events API tenant isolation — SIE Enterprise Read API & Browser
Integration Foundation v0.1's primary acceptance criterion (§5, §17,
§25). Walks the milestone's own explicit required-test checklist:

  * Org A user retrieves Org A's own events -- succeeds.
  * Org A user attempts to retrieve an Org B event by id -- 404 (never a
    distinguishing 403 that would confirm the id exists elsewhere).
  * Org A user filters the event list using Org B's organization_id --
    denied before any query runs (zero rows ever leak).
  * Machine client authenticated for Org A attempts to reach Org B's
    events -- denied.

Mirrors `tests/test_cross_tenant_enterprise_api.py`'s existing shape and
helpers.
"""

import uuid
from datetime import datetime, timezone

from app.models.safety_event import SafetyEvent
from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member

_EVENTS_URL = "/api/v1/events"


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _make_event(db_session, *, organization_id, **overrides) -> SafetyEvent:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=organization_id,
        site_id=None,
        event_type="INCIDENT",
        event_subtype=None,
        event_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        status="OPEN",
        description="event",
        attributes={},
        source_system="test-system",
        source_record_id=str(uuid.uuid4()),
        source_content_hash="hash",
        normalization_version="normalize-v1",
        schema_version="schema-v1",
        ingestion_batch_id=uuid.uuid4(),
        data_quality_status="VALID",
    )
    defaults.update(overrides)
    event = SafetyEvent(**defaults)
    db_session.add(event)
    db_session.commit()
    return event


def _two_organizations_with_events(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    member_a = make_org_member(db_session, org_a.id)
    member_b = make_org_member(db_session, org_b.id)
    event_a = _make_event(db_session, organization_id=org_a.id, source_record_id="A-1")
    event_b = _make_event(db_session, organization_id=org_b.id, source_record_id="B-1")
    return org_a, member_a, event_a, org_b, member_b, event_b


def test_org_a_can_retrieve_its_own_events(client, db_session):
    org_a, member_a, event_a, org_b, member_b, event_b = _two_organizations_with_events(db_session)

    list_response = client.get(f"{_EVENTS_URL}?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id))
    detail_response = client.get(
        f"{_EVENTS_URL}/{event_a.id}?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id)
    )

    assert list_response.status_code == 200
    body = list_response.json()
    assert body["total"] == 1
    assert body["items"][0]["id"] == str(event_a.id)
    assert detail_response.status_code == 200
    assert detail_response.json()["id"] == str(event_a.id)


def test_org_a_cannot_retrieve_org_bs_event_by_id(client, db_session):
    org_a, member_a, event_a, org_b, member_b, event_b = _two_organizations_with_events(db_session)

    response = client.get(
        f"{_EVENTS_URL}/{event_b.id}?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id)
    )

    assert response.status_code == 404


def test_org_bs_event_id_is_indistinguishable_from_a_nonexistent_id(client, db_session):
    """The cross-tenant 404 and the nonexistent-id 404 must be identical
    -- never a 403 that would itself disclose the id exists elsewhere."""
    org_a, member_a, event_a, org_b, member_b, event_b = _two_organizations_with_events(db_session)

    cross_tenant = client.get(
        f"{_EVENTS_URL}/{event_b.id}?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id)
    )
    nonexistent = client.get(
        f"{_EVENTS_URL}/{uuid.uuid4()}?organization_id={org_a.id}", headers=dev_auth_headers(member_a.id)
    )

    assert cross_tenant.status_code == nonexistent.status_code == 404
    assert cross_tenant.json()["detail"] == nonexistent.json()["detail"]


def test_org_a_filtering_by_org_bs_organization_id_leaks_zero_rows(client, db_session):
    """member_a has no membership in org_b at all, so the request is
    denied outright -- authorization runs before any query against
    org_b's events, so nothing about org_b's data is ever touched."""
    org_a, member_a, event_a, org_b, member_b, event_b = _two_organizations_with_events(db_session)

    response = client.get(f"{_EVENTS_URL}?organization_id={org_b.id}", headers=dev_auth_headers(member_a.id))

    assert response.status_code == 403


def test_org_b_cannot_reach_org_a_either(client, db_session):
    """The isolation is symmetric, not a one-directional accident."""
    org_a, member_a, event_a, org_b, member_b, event_b = _two_organizations_with_events(db_session)

    list_response = client.get(f"{_EVENTS_URL}?organization_id={org_a.id}", headers=dev_auth_headers(member_b.id))
    detail_response = client.get(
        f"{_EVENTS_URL}/{event_a.id}?organization_id={org_b.id}", headers=dev_auth_headers(member_b.id)
    )

    assert list_response.status_code == 403
    assert detail_response.status_code == 404


def test_machine_client_for_org_a_cannot_list_org_bs_events(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential_a = api_client_service.create(
        db_session, organization_id=org_a.id, name="A", scopes=[Permission.SAFETY_DATA_READ]
    )
    _make_event(db_session, organization_id=org_b.id)

    response = client.get(f"{_EVENTS_URL}?organization_id={org_b.id}", headers=_bearer(credential_a))

    assert response.status_code == 403


def test_machine_client_for_org_a_cannot_retrieve_org_bs_event_by_id(client, db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    credential_a = api_client_service.create(
        db_session, organization_id=org_a.id, name="A", scopes=[Permission.SAFETY_DATA_READ]
    )
    event_b = _make_event(db_session, organization_id=org_b.id)

    response = client.get(f"{_EVENTS_URL}/{event_b.id}?organization_id={org_b.id}", headers=_bearer(credential_a))

    assert response.status_code == 403


def test_machine_client_for_org_a_can_list_its_own_organizations_events(client, db_session):
    org_a = make_org(db_session, "Org A")
    credential_a = api_client_service.create(
        db_session, organization_id=org_a.id, name="A", scopes=[Permission.SAFETY_DATA_READ]
    )
    _make_event(db_session, organization_id=org_a.id)

    response = client.get(f"{_EVENTS_URL}?organization_id={org_a.id}", headers=_bearer(credential_a))

    assert response.status_code == 200
    assert response.json()["total"] == 1
