"""OpenAPI documentation accuracy — Intelligence Platform Integration &
Enterprise API v0.1, item 27."""

import json

from app.main import app
from app.services.permissions import Permission


def test_openapi_schema_is_generated_and_json_serializable():
    schema = app.openapi()
    json.dumps(schema)  # must not raise -- a real OpenAPI consumer requirement


def test_openapi_declares_both_real_authentication_mechanisms():
    schema = app.openapi()
    schemes = schema["components"]["securitySchemes"]
    assert schemes["MachineClientBearer"]["type"] == "http"
    assert schemes["MachineClientBearer"]["scheme"] == "bearer"
    assert schemes["DevModeHumanHeader"]["name"] == "X-SIE-Dev-User-Id"


def test_openapi_scope_vocabulary_matches_the_real_permission_enum_exactly():
    schema = app.openapi()
    declared = set(schema["components"]["x-sie-scopes"])
    real = {p.value for p in Permission}
    assert declared == real


def test_openapi_every_tag_used_by_a_route_has_a_description():
    schema = app.openapi()
    described_tags = {t["name"] for t in schema["tags"]}
    used_tags = set()
    for path_item in schema["paths"].values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                used_tags.update(operation.get("tags", []))
    missing = used_tags - described_tags
    assert missing == set(), f"routes use undocumented tags: {missing}"


def test_no_prediction_or_governance_request_documents_a_client_supplied_outcome_field():
    """Item 49's own rule ("a client must never be able to supply a
    label, feature value, risk score, or approval decision outcome")
    should be visible in the schema itself, not just enforced in code —
    scoped to the predictive/governance request schemas item 49 is
    actually about (a generic field named e.g. `status` is legitimate
    elsewhere, such as registering a DataSource's own operational
    status).

    M43-IP-03: `app/api/v1/predictions.py` and
    `app/api/v1/model_governance.py` were replaced with thin 501 stubs
    whose handlers take no typed request body -- their private
    computation was extracted to Commercial Core, so most of these
    schemas no longer exist in the OpenAPI document at all (nothing left
    to check a forbidden field against). Checks only the schemas that
    are still actually declared, rather than assuming all five always
    exist. See docs/M43_IP_03_PUBLIC_EXTRACTION.md."""
    schema = app.openapi()
    forbidden_field_names = {"label", "risk_score", "probability", "approved", "is_approved", "calibration_validated"}
    predictive_request_schemas = {
        "PredictionRequest",
        "TrainModelRequest",
        "ApproveModelRequest",
        "RejectModelRequest",
        "ValidateDatasetRequest",
    }
    declared_schemas = schema["components"].get("schemas", {})
    checked_any = False
    for schema_name in predictive_request_schemas:
        definition = declared_schemas.get(schema_name)
        if definition is None:
            continue
        checked_any = True
        properties = set(definition.get("properties", {}).keys())
        overlap = properties & forbidden_field_names
        assert not overlap, f"{schema_name} exposes a client-writable field it must never have: {overlap}"
    # Not asserting `checked_any` -- zero schemas present is the expected,
    # correct state post-M43-IP-03 (see docstring above).


def test_declared_paths_match_the_actual_registered_routes():
    """Never document an endpoint that doesn't actually exist (item 27's
    own instruction) -- and never silently register a route this schema
    doesn't know about either. FastAPI's own doc-UI routes (`/docs`,
    `/redoc`, `/openapi.json`, the oauth2 redirect) are real registered
    routes but never appear as OpenAPI *paths* of their own -- excluded
    here for exactly that reason, not because they're undocumented API."""
    schema_paths = set(app.openapi()["paths"].keys())
    from starlette.routing import Route

    fastapi_doc_ui_paths = {"/docs", "/docs/oauth2-redirect", "/redoc", "/openapi.json"}
    actual_paths = {route.path for route in app.routes if isinstance(route, Route)} - fastapi_doc_ui_paths
    assert schema_paths == actual_paths
