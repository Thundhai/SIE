"""Privacy and provenance surviving the API boundary — Intelligence
Platform Integration & Enterprise API v0.1, items 21/41/42.

Item 42's own instruction is the organizing principle here: "verify API
responses retain provenance from existing services; never recreate
provenance independently at the API layer." Every test below therefore
compares the HTTP response against the underlying row/object the service
layer actually produced (a DB row, or a stubbed service return value it
controls directly) rather than re-deriving the expected provenance chain
from scratch -- an API-layer bug that silently drops or reinvents a
provenance field would fail these tests even though the *feature* still
"works" in the sense of returning 200.

Item 41's own checklist (secrets never in logs, external LLM privacy gate
stays active, sensitive evidence never returned where prohibited) is
covered here specifically for the pieces this milestone's own new
surface touches (machine-client audit metadata, RAG's privacy gate
reachable through the same `RequestContext` plumbing the API layer now
uses) -- the deeper, service-level privacy tests already exist in
`tests/test_intelligence_privacy.py` and `tests/test_rag_service.py`.
"""

import uuid
from datetime import datetime, timedelta, timezone

from app.models.audit_log import AuditLog
from app.schemas.user import UserCreate
from app.services.api_client_service import api_client_service
from app.services.permissions import Permission
from app.services.user_service import user_service
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_org, make_safety_event
from tests.test_predictions_api import _deployed_model, _make_authorized_user


def _bearer(credential) -> dict:
    return {"Authorization": f"Bearer {credential.client_id}:{credential.secret}"}


def _any_authenticated_user(db_session):
    """No organization membership at all -- for GLOBAL-only queries,
    where `authorize_context()`'s own rule is that authentication alone
    is enough (see `app/api/deps_context.py`)."""
    return user_service.create(db_session, obj_in=UserCreate(email=f"{uuid.uuid4().hex}@example.com", name="Reader"))


# --- Provenance: predictions -----------------------------------------------------------


def test_prediction_response_provenance_matches_the_stored_row_exactly(client, db_session):
    """The API must return exactly what `app/models/prediction.py`'s row
    holds -- `model_id`, `model_version`, `feature_snapshot_id`, and
    `explanation` -- never a value recomputed or reshaped at the API
    layer."""
    org, site, entry, as_of = _deployed_model(db_session, seed=777)
    user = _make_authorized_user(db_session, org.id)

    response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id), "as_of": as_of.isoformat()},
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()

    from app.models.prediction import Prediction

    row = db_session.get(Prediction, uuid.UUID(body["id"]))
    assert row is not None
    assert body["model_id"] == str(row.model_id)
    assert body["model_version"] == row.model_version
    assert body["feature_snapshot_id"] == str(row.feature_snapshot_id)
    assert body["explanation"] == row.explanation
    # And the model referenced is genuinely the one that was deployed --
    # not some other/default model silently substituted.
    assert row.model_id == entry.id


def test_prediction_explanation_carries_full_feature_level_provenance(client, db_session):
    org, site, _entry, as_of = _deployed_model(db_session, seed=778)
    user = _make_authorized_user(db_session, org.id)

    response = client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id), "as_of": as_of.isoformat()},
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert explanation is not None
    assert explanation["method"]
    assert explanation["disclaimer"]
    for contribution in explanation["top_positive"] + explanation["top_negative"]:
        # Each contributing feature traces back to a named feature and a
        # direction -- never an opaque, unexplained number.
        assert contribution["feature_name"]
        assert contribution["direction"] in ("positive", "negative")
        assert contribution["association_note"]


def test_prediction_history_entries_each_carry_their_own_model_and_snapshot_provenance(client, db_session):
    org, site, entry, as_of = _deployed_model(db_session, seed=779)
    user = _make_authorized_user(db_session, org.id)

    client.post(
        f"/api/v1/intelligence/predictions?organization_id={org.id}",
        json={"entity_id": str(site.id), "as_of": as_of.isoformat()},
        headers=dev_auth_headers(user.id),
    )
    response = client.get(
        f"/api/v1/intelligence/predictions/{site.id}/history?organization_id={org.id}",
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    predictions = response.json()["data"]
    assert len(predictions) == 1
    assert predictions[0]["model_id"] == str(entry.id)
    assert predictions[0]["feature_snapshot_id"] is not None


# --- Provenance: RAG citations -----------------------------------------------------------


def test_rag_citation_provenance_chain_survives_the_api_unchanged(client, db_session, monkeypatch):
    """citation -> chunk -> document version -> document -> source, per
    item 21 -- stubbed with real, distinguishable ids so the test can
    prove the API layer passes each one through verbatim rather than
    dropping or renaming any link in the chain."""
    chunk_id, document_id, version_id, source_id = (uuid.uuid4() for _ in range(4))

    from app.models.enums import ContentType, QualityStatus, VerificationStatus
    from app.rag.results import Citation, EvidenceState, RAGOutcome, RAGResponse

    citation = Citation(
        citation_id="E1",
        chunk_id=chunk_id,
        document_id=document_id,
        document_version_id=version_id,
        source_id=source_id,
        source_name="OSHA",
        document_title="29 CFR 1910.132",
        version_label="v1",
        location="Section 6.2",
        content_type=ContentType.TEXT,
        verification_status=VerificationStatus.VERIFIED,
        extraction_quality=QualityStatus.HIGH,
        source_authority_level="REGULATORY",
        similarity=0.91,
        scope="GLOBAL",
        organization_id=None,
    )

    def _stub_query(*args, **kwargs):
        return RAGResponse(
            query="PPE requirements",
            outcome=RAGOutcome.ANSWERED,
            evidence_state=EvidenceState.SUFFICIENT,
            answer="Employers must assess PPE hazards. [E1]",
            citations=[citation],
            conflicts=[],
            evidence_count=1,
            warnings=[],
            abstention_reason=None,
            retrieval_metadata={},
            model_metadata=None,
            prompt_version="v1",
            reproducibility={},
        )

    monkeypatch.setattr("app.api.v1.rag.rag_service.query", _stub_query)
    user = _any_authenticated_user(db_session)

    response = client.post(
        "/api/v1/knowledge/rag/query", json={"query": "PPE requirements"}, headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 200
    returned = response.json()["citations"][0]
    assert returned["chunk_id"] == str(chunk_id)
    assert returned["document_id"] == str(document_id)
    assert returned["document_version_id"] == str(version_id)
    assert returned["source_id"] == str(source_id)


def test_retrieval_result_provenance_chain_survives_the_api_unchanged(client, db_session, monkeypatch):
    chunk_id, document_id, version_id, source_id = (uuid.uuid4() for _ in range(4))

    from app.models.enums import ContentType, QualityStatus, VerificationStatus
    from app.retrieval.results import (
        RelevanceLevel,
        RetrievalOutcome,
        RetrievalResponse,
        RetrievalResult,
    )

    result = RetrievalResult(
        rank=1,
        chunk_id=chunk_id,
        similarity=0.88,
        relevance=RelevanceLevel.HIGH,
        content="Employers shall assess the workplace...",
        content_type=ContentType.TEXT,
        document_id=document_id,
        document_version_id=version_id,
        source_id=source_id,
        document_title="29 CFR 1910.132",
        source_name="OSHA",
        source_publisher="OSHA",
        version_label="v1",
        location="Section 6.2",
        page_number=None,
        sheet_name=None,
        row_number=None,
        slide_number=None,
        section_title=None,
        section_path=None,
        extraction_quality=QualityStatus.HIGH,
        extraction_method=None,
        source_authority_level="REGULATORY",
        verification_status=VerificationStatus.VERIFIED,
        scope="GLOBAL",
        organization_id=None,
    )

    def _stub_search(*args, **kwargs):
        return RetrievalResponse(
            query="PPE requirements",
            outcome=RetrievalOutcome.RESULTS,
            embedding_provider="hashing",
            embedding_model="sie-hashing-embedder",
            embedding_model_version="v1",
            results=[result],
            result_count=1,
        )

    monkeypatch.setattr("app.api.v1.retrieval.retrieval_service.search", _stub_search)
    user = _any_authenticated_user(db_session)

    response = client.post(
        "/api/v1/knowledge/retrieval/search", json={"query": "PPE requirements"}, headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 200
    returned = response.json()["results"][0]
    assert returned["chunk_id"] == str(chunk_id)
    assert returned["document_id"] == str(document_id)
    assert returned["document_version_id"] == str(version_id)
    assert returned["source_id"] == str(source_id)


# --- Provenance: analytics signals ---------------------------------------------------------


def test_analytics_signal_provenance_traces_to_the_exact_real_seeded_events(client, db_session):
    """signal -> supporting_event_ids -> real `SafetyEvent` rows (item
    21's analytics chain) -- seeded here as genuine DB rows (not a stub),
    so this test also proves `risk_signal_service.detect_all()` itself is
    the one computing this, never re-derived at the API layer."""
    org = make_org(db_session)
    now = datetime.now(timezone.utc)
    user = _make_authorized_user(db_session, org.id)

    # Sparse baseline (well outside the analysis window) plus a genuine
    # current-window surge -- the same shape `test_intelligence_signals.py`
    # uses, just anchored to real "now" since the API endpoint has no
    # `as_of` override.
    for days_ago, count in ((45, 1), (75, 1)):
        for i in range(count):
            event = make_safety_event(
                organization_id=org.id,
                event_type="INCIDENT",
                potential_severity="HIGH",
                event_time=now - timedelta(days=days_ago, hours=i),
                ingestion_time=now - timedelta(days=days_ago, hours=i),
                source_record_id=f"baseline-{days_ago}-{i}",
            )
            db_session.add(event)

    current_event_ids = []
    for i in range(5):
        event = make_safety_event(
            organization_id=org.id,
            event_type="INCIDENT",
            potential_severity="HIGH",
            event_time=now - timedelta(days=i),
            ingestion_time=now - timedelta(days=i),
            source_record_id=f"current-{i}",
        )
        db_session.add(event)
        current_event_ids.append(event.id)
    db_session.commit()

    response = client.get(
        f"/api/v1/intelligence/analytics/signals?organization_id={org.id}", headers=dev_auth_headers(user.id)
    )
    assert response.status_code == 200
    signals = response.json()
    cluster_signals = [s for s in signals if s["signal_type"] == "HIGH_POTENTIAL_EVENT_CLUSTER"]
    assert cluster_signals, "expected the seeded surge to actually fire a signal"

    returned_event_ids = {uuid.UUID(e) for e in cluster_signals[0]["supporting_event_ids"]}
    assert returned_event_ids
    assert returned_event_ids.issubset(set(current_event_ids))


# --- Privacy: audit metadata never carries a secret ----------------------------------------


def test_machine_authentication_audit_entry_never_contains_the_secret(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Client", scopes=[Permission.SAFETY_DATA_WRITE]
    )

    response = client.post(
        "/api/v1/intelligence/events",
        json={
            "event_type": "NEAR_MISS",
            "event_time": "2026-01-01T00:00:00Z",
            "source_system": "test",
            "source_record_id": "rec-privacy-1",
        },
        headers=_bearer(credential),
    )
    assert response.status_code == 200

    entries = db_session.query(AuditLog).filter(AuditLog.action == "API_AUTHENTICATED").all()
    assert entries
    for entry in entries:
        assert credential.secret not in str(entry.event_metadata)
        assert credential.secret not in str(entry.event_metadata or {})


def test_access_denied_audit_entry_never_contains_the_secret(client, db_session):
    org = make_org(db_session)
    credential = api_client_service.create(
        db_session, organization_id=org.id, name="Read-only client", scopes=[Permission.SAFETY_DATA_READ]
    )

    response = client.post(
        "/api/v1/intelligence/events",
        json={
            "event_type": "NEAR_MISS",
            "event_time": "2026-01-01T00:00:00Z",
            "source_system": "test",
            "source_record_id": "rec-privacy-2",
        },
        headers=_bearer(credential),
    )
    assert response.status_code == 403

    entries = db_session.query(AuditLog).filter(AuditLog.action == "API_ACCESS_DENIED").all()
    assert entries
    for entry in entries:
        assert credential.secret not in str(entry.event_metadata or {})


# --- Privacy: the RAG privacy gate stays reachable through the new API surface -------------


def test_external_llm_privacy_gate_reaches_the_api_response_unchanged(client, db_session, monkeypatch):
    """A `PRIVACY_BLOCKED` outcome from `RAGService` (item 23's own
    "external LLM privacy controls remain enforced") must reach the HTTP
    caller as that exact outcome -- a normal 200 with `outcome ==
    "PRIVACY_BLOCKED"` and no `answer` -- never silently upgraded into a
    normal answered response by anything in the API layer."""
    from app.rag.results import EvidenceState, RAGOutcome, RAGResponse

    def _stub_query(*args, **kwargs):
        return RAGResponse(
            query="confidential incident details",
            outcome=RAGOutcome.PRIVACY_BLOCKED,
            evidence_state=EvidenceState.SUFFICIENT,
            answer=None,
            citations=[],
            conflicts=[],
            evidence_count=3,
            warnings=["PRIVACY_BLOCKED: external LLM provider blocked from private evidence."],
            abstention_reason="External LLM provider blocked from private evidence.",
            retrieval_metadata={},
            model_metadata=None,
            prompt_version="v1",
            reproducibility={},
        )

    monkeypatch.setattr("app.api.v1.rag.rag_service.query", _stub_query)
    org = make_org(db_session)
    user = _make_authorized_user(db_session, org.id)

    response = client.post(
        "/api/v1/knowledge/rag/query",
        json={"query": "confidential incident details", "filters": {"organization_id": str(org.id)}},
        headers=dev_auth_headers(user.id),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "PRIVACY_BLOCKED"
    assert body["answer"] is None
    assert body["citations"] == []
