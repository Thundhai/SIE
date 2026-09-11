"""SIE Milestone 43A: Organizational Standards & Governance Foundation —
service-level tests for `app/services/governing_standard_service.py`.
Mirrors `tests/test_organizational_memory_service.py`'s own established
shape: direct calls against `db_session`, no HTTP layer. HTTP-layer
coverage (authorization, tenant isolation over the wire, idempotency,
response contract) lives in `tests/test_governing_standard_api.py`.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi import HTTPException

from app.models.enums import ScopeType, VerificationStatus
from app.models.governing_standard import GoverningStandard
from app.models.governing_standard_enums import GoverningStandardType, OrganizationGoverningStandardStatus
from app.models.knowledge_source import KnowledgeSource
from app.services.governing_standard_service import (
    create_organization_standard,
    list_active_governing_standards,
    list_available_governing_standards,
    list_selection_history,
    resolve_current_selection,
    resolve_governing_standard_reference,
    retire_governing_standard,
    seed_global_catalogue,
    select_governing_standard,
    selection_mutation_transaction,
    standard_mutation_transaction,
)
from tests.intelligence_test_helpers import make_org


def _make_global_standard(db_session, *, name="ISO 45001", regions=None, industry_sectors=None, is_active=True):
    standard = GoverningStandard(
        scope_type=ScopeType.GLOBAL,
        organization_id=None,
        name=name,
        short_description="Occupational health and safety management systems.",
        issuing_organization="ISO",
        standard_type=GoverningStandardType.INTERNATIONAL_STANDARD,
        regions=regions or [],
        industry_sectors=industry_sectors or [],
        verification_status=VerificationStatus.VERIFIED,
        is_active=is_active,
    )
    db_session.add(standard)
    db_session.commit()
    return standard


def _make_org_standard(db_session, organization_id, *, name="ABC Energy HSE Standard 2026"):
    standard = GoverningStandard(
        scope_type=ScopeType.ORGANIZATION,
        organization_id=organization_id,
        name=name,
        short_description="ABC Energy's own internal HSE standard.",
        issuing_organization="ABC Energy",
        standard_type=GoverningStandardType.ORGANIZATION_SPECIFIC,
        regions=[],
        industry_sectors=[],
        verification_status=VerificationStatus.PENDING,
        is_active=True,
    )
    db_session.add(standard)
    db_session.commit()
    return standard


# --- Catalogue: create/read, active/inactive, regional/industry metadata --------------------


def test_creates_a_global_and_an_organization_standard(db_session):
    org = make_org(db_session)
    _make_global_standard(db_session)
    org_standard = _make_org_standard(db_session, org.id)

    assert org_standard.scope_type == ScopeType.ORGANIZATION
    assert org_standard.organization_id == org.id


def test_available_standards_include_global_and_this_organizations_own_but_not_another_organizations(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    _make_global_standard(db_session, name="ISO 45001")
    a_standard = _make_org_standard(db_session, org_a.id, name="Org A Standard")
    _make_org_standard(db_session, org_b.id, name="Org B Standard")

    available = list_available_governing_standards(db_session, organization_id=org_a.id)
    names = {s.name for s in available}
    assert "ISO 45001" in names
    assert "Org A Standard" in names
    assert "Org B Standard" not in names
    assert a_standard.id in {s.id for s in available}


def test_inactive_standards_are_excluded_by_default_but_reachable_explicitly(db_session):
    org = make_org(db_session)
    _make_global_standard(db_session, name="Active Standard", is_active=True)
    _make_global_standard(db_session, name="Retired Standard", is_active=False)

    default_view = list_available_governing_standards(db_session, organization_id=org.id)
    assert {s.name for s in default_view} == {"Active Standard"}

    all_view = list_available_governing_standards(db_session, organization_id=org.id, is_active=None)
    assert {s.name for s in all_view} == {"Active Standard", "Retired Standard"}


def test_regional_and_industry_metadata_filter_the_catalogue_honestly(db_session):
    org = make_org(db_session)
    _make_global_standard(db_session, name="US-only", regions=["US"], industry_sectors=["OIL_GAS"])
    _make_global_standard(db_session, name="Global reach", regions=["US", "EU", "APAC"], industry_sectors=["MINING"])
    _make_global_standard(db_session, name="No region stated", regions=[], industry_sectors=[])

    by_region = list_available_governing_standards(db_session, organization_id=org.id, region="EU")
    assert {s.name for s in by_region} == {"Global reach"}

    by_industry = list_available_governing_standards(db_session, organization_id=org.id, industry="OIL_GAS")
    assert {s.name for s in by_industry} == {"US-only"}

    # An honestly empty regions/industry_sectors list never matches any
    # filter -- it is never treated as "applies everywhere" (spec §15
    # Rule 2).
    assert "No region stated" not in {s.name for s in by_region}
    assert "No region stated" not in {s.name for s in by_industry}


def test_resolve_governing_standard_reference_rejects_another_organizations_own_standard(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    b_standard = _make_org_standard(db_session, org_b.id, name="Org B Standard")

    with pytest.raises(HTTPException) as exc_info:
        resolve_governing_standard_reference(db_session, organization_id=org_a.id, standard_id=b_standard.id)
    assert exc_info.value.status_code == 404


def test_resolve_governing_standard_reference_accepts_a_global_standard_for_any_organization(db_session):
    org = make_org(db_session)
    global_standard = _make_global_standard(db_session)

    resolved = resolve_governing_standard_reference(db_session, organization_id=org.id, standard_id=global_standard.id)
    assert resolved.id == global_standard.id


# --- Organization-specific standard <-> KnowledgeSource relationship ------------------------


def test_create_organization_standard_links_to_an_organizations_own_knowledge_source(db_session):
    org = make_org(db_session)
    source = KnowledgeSource(
        scope_type=ScopeType.ORGANIZATION,
        organization_id=org.id,
        publisher="ABC Energy",
        name="ABC Energy HSE Standard 2026 — source document",
        source_type="internal_procedure",
    )
    db_session.add(source)
    db_session.commit()

    with standard_mutation_transaction(db_session):
        standard = create_organization_standard(
            db_session,
            organization_id=org.id,
            name="ABC Energy HSE Standard 2026",
            short_description="ABC Energy's own internal HSE standard.",
            issuing_organization="ABC Energy",
            standard_type=GoverningStandardType.ORGANIZATION_SPECIFIC,
            regions=[],
            industry_sectors=[],
            version="2026",
            publication_date=None,
            effective_date=None,
            knowledge_source_id=source.id,
            created_by_user_id=None,
            created_by_api_client_id=None,
            request_id=None,
        )

    assert standard.scope_type == ScopeType.ORGANIZATION
    assert standard.organization_id == org.id
    assert standard.knowledge_source_id == source.id


def test_create_organization_standard_rejects_another_organizations_knowledge_source(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    b_source = KnowledgeSource(
        scope_type=ScopeType.ORGANIZATION,
        organization_id=org_b.id,
        publisher="Org B",
        name="Org B's own procedure",
        source_type="internal_procedure",
    )
    db_session.add(b_source)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_organization_standard(
            db_session,
            organization_id=org_a.id,
            name="Org A Standard",
            short_description="desc",
            issuing_organization="Org A",
            standard_type=GoverningStandardType.ORGANIZATION_SPECIFIC,
            regions=[],
            industry_sectors=[],
            version=None,
            publication_date=None,
            effective_date=None,
            knowledge_source_id=b_source.id,
            created_by_user_id=None,
            created_by_api_client_id=None,
            request_id=None,
        )
    assert exc_info.value.status_code == 422


def test_create_organization_standard_rejects_a_global_knowledge_source(db_session):
    org = make_org(db_session)
    global_source = KnowledgeSource(
        scope_type=ScopeType.GLOBAL, organization_id=None, publisher="OSHA", name="29 CFR 1910", source_type="regulation"
    )
    db_session.add(global_source)
    db_session.commit()

    with pytest.raises(HTTPException) as exc_info:
        create_organization_standard(
            db_session,
            organization_id=org.id,
            name="Org Standard",
            short_description="desc",
            issuing_organization="Org",
            standard_type=GoverningStandardType.ORGANIZATION_SPECIFIC,
            regions=[],
            industry_sectors=[],
            version=None,
            publication_date=None,
            effective_date=None,
            knowledge_source_id=global_source.id,
            created_by_user_id=None,
            created_by_api_client_id=None,
            request_id=None,
        )
    assert exc_info.value.status_code == 422


# --- Organization selection: select, multiple, duplicate prevention, tenant scoping ----------


def test_organization_can_select_a_standard(db_session):
    org = make_org(db_session)
    standard = _make_global_standard(db_session)

    with selection_mutation_transaction(db_session):
        selection, created = select_governing_standard(
            db_session,
            organization_id=org.id,
            standard_id=standard.id,
            effective_date=None,
            rationale="Adopted per contractual requirement.",
            configured_by_user_id=None,
            configured_by_api_client_id=None,
            request_id=None,
        )

    assert created is True
    assert selection.status == OrganizationGoverningStandardStatus.SELECTED
    assert selection.organization_id == org.id
    assert selection.standard_id == standard.id


def test_organization_can_select_multiple_standards(db_session):
    org = make_org(db_session)
    iso = _make_global_standard(db_session, name="ISO 45001")
    osha = _make_global_standard(db_session, name="OSHA 1910")

    with selection_mutation_transaction(db_session):
        select_governing_standard(
            db_session, organization_id=org.id, standard_id=iso.id, effective_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )
    with selection_mutation_transaction(db_session):
        select_governing_standard(
            db_session, organization_id=org.id, standard_id=osha.id, effective_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )

    active = list_active_governing_standards(db_session, organization_id=org.id)
    assert {s.name for s, _ in active} == {"ISO 45001", "OSHA 1910"}


def test_duplicate_selection_is_prevented_returns_existing_event_not_a_new_one(db_session):
    org = make_org(db_session)
    standard = _make_global_standard(db_session)

    with selection_mutation_transaction(db_session):
        first, first_created = select_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, effective_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )
    with selection_mutation_transaction(db_session):
        second, second_created = select_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, effective_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )

    assert first_created is True
    assert second_created is False
    assert second.id == first.id

    history, total = list_selection_history(db_session, organization_id=org.id)
    assert total == 1


def test_selection_is_organization_scoped(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    standard = _make_global_standard(db_session)

    with selection_mutation_transaction(db_session):
        select_governing_standard(
            db_session, organization_id=org_a.id, standard_id=standard.id, effective_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )

    assert len(list_active_governing_standards(db_session, organization_id=org_a.id)) == 1
    assert len(list_active_governing_standards(db_session, organization_id=org_b.id)) == 0
    assert resolve_current_selection(db_session, organization_id=org_b.id, standard_id=standard.id) is None


def test_retiring_a_standard_removes_it_from_the_active_set_but_keeps_history(db_session):
    org = make_org(db_session)
    standard = _make_global_standard(db_session)

    with selection_mutation_transaction(db_session):
        select_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, effective_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )
    with selection_mutation_transaction(db_session):
        retirement = retire_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, retirement_date=None,
            rationale="No longer applicable.", configured_by_user_id=None, configured_by_api_client_id=None,
            request_id=None,
        )

    assert retirement.status == OrganizationGoverningStandardStatus.RETIRED
    assert list_active_governing_standards(db_session, organization_id=org.id) == []

    history, total = list_selection_history(db_session, organization_id=org.id)
    assert total == 2  # SELECTED then RETIRED -- both preserved, append-only


def test_retiring_a_never_selected_standard_is_rejected(db_session):
    org = make_org(db_session)
    standard = _make_global_standard(db_session)

    with pytest.raises(HTTPException) as exc_info:
        retire_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, retirement_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )
    assert exc_info.value.status_code == 422


def test_retiring_an_already_retired_standard_is_rejected(db_session):
    org = make_org(db_session)
    standard = _make_global_standard(db_session)
    with selection_mutation_transaction(db_session):
        select_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, effective_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )
    with selection_mutation_transaction(db_session):
        retire_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, retirement_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )

    with pytest.raises(HTTPException) as exc_info:
        retire_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, retirement_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )
    assert exc_info.value.status_code == 422


def test_re_selecting_a_retired_standard_creates_a_new_event_not_a_duplicate_error(db_session):
    org = make_org(db_session)
    standard = _make_global_standard(db_session)
    with selection_mutation_transaction(db_session):
        select_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, effective_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )
    with selection_mutation_transaction(db_session):
        retire_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, retirement_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )
    with selection_mutation_transaction(db_session):
        reselected, created = select_governing_standard(
            db_session, organization_id=org.id, standard_id=standard.id, effective_date=None, rationale="Re-adopted.",
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )

    assert created is True
    assert reselected.status == OrganizationGoverningStandardStatus.SELECTED

    history, total = list_selection_history(db_session, organization_id=org.id)
    assert total == 3  # SELECTED, RETIRED, SELECTED again


def test_selecting_another_organizations_own_standard_is_rejected(db_session):
    org_a = make_org(db_session, "Org A")
    org_b = make_org(db_session, "Org B")
    b_standard = _make_org_standard(db_session, org_b.id)

    with pytest.raises(HTTPException) as exc_info:
        select_governing_standard(
            db_session, organization_id=org_a.id, standard_id=b_standard.id, effective_date=None, rationale=None,
            configured_by_user_id=None, configured_by_api_client_id=None, request_id=None,
        )
    assert exc_info.value.status_code == 404


# --- No-standard state -----------------------------------------------------------------------


def test_an_organization_with_no_selected_standards_is_a_valid_empty_state(db_session):
    org = make_org(db_session)
    assert list_active_governing_standards(db_session, organization_id=org.id) == []
    history, total = list_selection_history(db_session, organization_id=org.id)
    assert history == []
    assert total == 0


# --- seed_global_catalogue idempotency ---------------------------------------------------------


def test_seed_global_catalogue_is_idempotent_by_name(db_session):
    entries = [
        {
            "name": "ISO 45001",
            "short_description": "Occupational health and safety management systems.",
            "issuing_organization": "ISO",
            "standard_type": "INTERNATIONAL_STANDARD",
        }
    ]
    first = seed_global_catalogue(db_session, entries)
    db_session.commit()
    second = seed_global_catalogue(db_session, entries)
    db_session.commit()

    assert len(first) == 1
    assert len(second) == 0  # already exists by name -- no duplicate created

    org = make_org(db_session)
    available = list_available_governing_standards(db_session, organization_id=org.id)
    assert len([s for s in available if s.name == "ISO 45001"]) == 1
