"""Human-facing Events read API — SIE Enterprise Read API & Browser
Integration Foundation v0.1. HTTP-level tests against the ordinary
SQLite `client` fixture, mirroring `tests/test_predictions_api.py`'s own
shape. Tenant isolation gets its own dedicated file
(`tests/test_events_tenant_isolation.py`) since it is this milestone's
primary acceptance criterion.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.data_source import DataSource
from app.models.safety_event import SafetyEvent
from app.services.permissions import OrganizationRole
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_org_member, make_site

_EVENTS_URL = "/api/v1/events"


def _make_event(db_session, *, organization_id, site_id=None, **overrides) -> SafetyEvent:
    defaults = dict(
        id=uuid.uuid4(),
        organization_id=organization_id,
        site_id=site_id,
        event_type="INCIDENT",
        event_subtype=None,
        event_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        ingestion_time=datetime(2026, 6, 1, tzinfo=timezone.utc),
        status="OPEN",
        severity=None,
        description="A test event.",
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


# --- List: basic, empty, pagination -----------------------------------------------------


def test_list_events_requires_authentication(client, db_session):
    org = make_org(db_session)
    response = client.get(f"{_EVENTS_URL}?organization_id={org.id}")
    assert response.status_code == 401


def test_list_events_returns_empty_for_an_organization_with_no_events(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id, role=OrganizationRole.VIEWER)

    response = client.get(f"{_EVENTS_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id))

    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 25}


def test_list_events_returns_real_events_for_the_caller_organization(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    user = make_org_member(db_session, org.id)
    event = _make_event(db_session, organization_id=org.id, site_id=site.id, event_type="NEAR_MISS")

    response = client.get(f"{_EVENTS_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id))

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == str(event.id)
    assert item["event_type"] == "NEAR_MISS"
    assert item["site_id"] == str(site.id)
    assert item["site_name"] == site.name
    # No description/attributes/provenance in the summary shape.
    assert "description" not in item
    assert "attributes" not in item


def test_list_events_pagination(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    base_time = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(5):
        _make_event(db_session, organization_id=org.id, event_time=base_time + timedelta(days=i))

    page_1 = client.get(
        f"{_EVENTS_URL}?organization_id={org.id}&page=1&page_size=2", headers=dev_auth_headers(user.id)
    ).json()
    page_2 = client.get(
        f"{_EVENTS_URL}?organization_id={org.id}&page=2&page_size=2", headers=dev_auth_headers(user.id)
    ).json()
    page_3 = client.get(
        f"{_EVENTS_URL}?organization_id={org.id}&page=3&page_size=2", headers=dev_auth_headers(user.id)
    ).json()

    assert page_1["total"] == page_2["total"] == page_3["total"] == 5
    assert len(page_1["items"]) == 2
    assert len(page_2["items"]) == 2
    assert len(page_3["items"]) == 1
    ids_seen = {item["id"] for page in (page_1, page_2, page_3) for item in page["items"]}
    assert len(ids_seen) == 5  # no duplicates, no gaps across pages


def test_list_events_past_the_last_page_returns_an_empty_list_not_an_error(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    _make_event(db_session, organization_id=org.id)

    response = client.get(
        f"{_EVENTS_URL}?organization_id={org.id}&page=99&page_size=10", headers=dev_auth_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["items"] == []
    assert body["total"] == 1


def test_list_events_sort_is_deterministic_across_repeated_requests(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    same_time = datetime(2026, 3, 1, tzinfo=timezone.utc)
    for _ in range(4):
        _make_event(db_session, organization_id=org.id, event_time=same_time)

    first = client.get(f"{_EVENTS_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id)).json()
    second = client.get(f"{_EVENTS_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id)).json()

    assert [i["id"] for i in first["items"]] == [i["id"] for i in second["items"]]


# --- List: filters and search -----------------------------------------------------------


def test_list_events_filters_by_event_type(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    _make_event(db_session, organization_id=org.id, event_type="INCIDENT")
    _make_event(db_session, organization_id=org.id, event_type="NEAR_MISS")

    response = client.get(
        f"{_EVENTS_URL}?organization_id={org.id}&event_type=NEAR_MISS", headers=dev_auth_headers(user.id)
    )

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["event_type"] == "NEAR_MISS"


def test_list_events_filters_by_site(client, db_session):
    org = make_org(db_session)
    site_a = make_site(db_session, org.id, "Site A")
    site_b = make_site(db_session, org.id, "Site B")
    user = make_org_member(db_session, org.id)
    _make_event(db_session, organization_id=org.id, site_id=site_a.id)
    _make_event(db_session, organization_id=org.id, site_id=site_b.id)

    response = client.get(
        f"{_EVENTS_URL}?organization_id={org.id}&site_id={site_a.id}", headers=dev_auth_headers(user.id)
    )

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["site_id"] == str(site_a.id)


def test_list_events_filters_by_status(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    _make_event(db_session, organization_id=org.id, status="OPEN")
    _make_event(db_session, organization_id=org.id, status="CLOSED")

    response = client.get(f"{_EVENTS_URL}?organization_id={org.id}&status=CLOSED", headers=dev_auth_headers(user.id))

    body = response.json()
    assert body["total"] == 1
    assert body["items"][0]["status"] == "CLOSED"


def test_list_events_filters_by_date_range(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    _make_event(db_session, organization_id=org.id, event_time=datetime(2026, 1, 1, tzinfo=timezone.utc))
    _make_event(db_session, organization_id=org.id, event_time=datetime(2026, 6, 1, tzinfo=timezone.utc))
    _make_event(db_session, organization_id=org.id, event_time=datetime(2026, 12, 1, tzinfo=timezone.utc))

    response = client.get(
        f"{_EVENTS_URL}?organization_id={org.id}"
        "&event_time_from=2026-02-01T00:00:00Z&event_time_to=2026-07-01T00:00:00Z",
        headers=dev_auth_headers(user.id),
    )

    body = response.json()
    assert body["total"] == 1


def test_list_events_search_matches_description(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    _make_event(db_session, organization_id=org.id, description="Forklift near miss in Bay 3")
    _make_event(db_session, organization_id=org.id, description="Unrelated event")

    response = client.get(f"{_EVENTS_URL}?organization_id={org.id}&search=forklift", headers=dev_auth_headers(user.id))

    body = response.json()
    assert body["total"] == 1


def test_list_events_search_matches_source_record_id(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    _make_event(db_session, organization_id=org.id, source_record_id="REF-12345")
    _make_event(db_session, organization_id=org.id, source_record_id="OTHER-999")

    response = client.get(f"{_EVENTS_URL}?organization_id={org.id}&search=REF-123", headers=dev_auth_headers(user.id))

    body = response.json()
    assert body["total"] == 1


def test_list_events_search_with_no_matches_returns_empty(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    _make_event(db_session, organization_id=org.id, description="Something else entirely")

    response = client.get(
        f"{_EVENTS_URL}?organization_id={org.id}&search=nonexistentterm", headers=dev_auth_headers(user.id)
    )

    assert response.json()["total"] == 0


# --- List: invalid params ----------------------------------------------------------------


def test_list_events_requires_organization_id(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    response = client.get(_EVENTS_URL, headers=dev_auth_headers(user.id))
    assert response.status_code == 422


def test_list_events_rejects_a_malformed_organization_id(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    response = client.get(f"{_EVENTS_URL}?organization_id=not-a-uuid", headers=dev_auth_headers(user.id))
    assert response.status_code == 422


def test_list_events_rejects_page_less_than_one(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    response = client.get(f"{_EVENTS_URL}?organization_id={org.id}&page=0", headers=dev_auth_headers(user.id))
    assert response.status_code == 422


def test_list_events_rejects_a_page_size_over_the_max(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    response = client.get(f"{_EVENTS_URL}?organization_id={org.id}&page_size=9999", headers=dev_auth_headers(user.id))
    assert response.status_code == 422


def test_list_events_denies_a_user_with_no_membership_in_the_organization(client, db_session):
    org = make_org(db_session)
    other_org = make_org(db_session, "Other Org")
    user = make_org_member(db_session, other_org.id)

    response = client.get(f"{_EVENTS_URL}?organization_id={org.id}", headers=dev_auth_headers(user.id))

    assert response.status_code == 403


# --- Detail ---------------------------------------------------------------------------


def test_get_event_returns_core_info_and_provenance(client, db_session):
    org = make_org(db_session)
    site = make_site(db_session, org.id)
    user = make_org_member(db_session, org.id)
    data_source = DataSource(organization_id=org.id, name="SafetyCloud", source_type="api")
    db_session.add(data_source)
    db_session.commit()
    event = _make_event(
        db_session,
        organization_id=org.id,
        site_id=site.id,
        ingestion_source_id=data_source.id,
        correlation_id="corr-1",
    )

    response = client.get(
        f"{_EVENTS_URL}/{event.id}?organization_id={org.id}", headers=dev_auth_headers(user.id)
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(event.id)
    assert body["organization_id"] == str(org.id)
    assert body["site_name"] == site.name
    assert body["description"] == event.description
    provenance = body["provenance"]
    assert provenance["organization_id"] == str(org.id)
    assert provenance["data_source_name"] == "SafetyCloud"
    assert provenance["ingestion_batch_id"] == str(event.ingestion_batch_id)
    assert provenance["correlation_id"] == "corr-1"
    # No evidence/knowledge fields fabricated onto the response.
    assert "evidence" not in body
    assert "knowledge" not in body
    assert "related_records" not in body


def test_get_event_without_a_data_source_leaves_data_source_name_null(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)
    event = _make_event(db_session, organization_id=org.id)

    response = client.get(
        f"{_EVENTS_URL}/{event.id}?organization_id={org.id}", headers=dev_auth_headers(user.id)
    )

    assert response.status_code == 200
    assert response.json()["provenance"]["data_source_name"] is None


def test_get_event_404s_for_a_nonexistent_event_id(client, db_session):
    org = make_org(db_session)
    user = make_org_member(db_session, org.id)

    response = client.get(
        f"{_EVENTS_URL}/{uuid.uuid4()}?organization_id={org.id}", headers=dev_auth_headers(user.id)
    )

    assert response.status_code == 404


def test_get_event_requires_authentication(client, db_session):
    org = make_org(db_session)
    event_id = uuid.uuid4()
    response = client.get(f"{_EVENTS_URL}/{event_id}?organization_id={org.id}")
    assert response.status_code == 401
