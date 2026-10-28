"""SIE-2: the tenant assertion signer (app/integrations/tenant_assertion.py)
and its use by `HttpCommercialCoreClient` and the routers.

Every key here is generated per test run; none is a real deployment key.
Tokens are checked the way Commercial Core's verifiers check them:
signature against the public half, exact header fields, and the
contract's own claims model.
"""

from __future__ import annotations

import base64
import json
import uuid
from datetime import datetime, timezone

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, NoEncryption, PrivateFormat, PublicFormat
from sie_contract import (
    TENANT_ASSERTION_HEADER,
    ActorType,
    TenantAssertionClaims,
    TenantCapability,
)

from app.api.deps_context import RequestContext
from app.integrations.commercial_core import (
    CommercialCoreAuthenticationError,
    CommercialCoreTenantAssertionRejectedError,
    CommercialCoreTenantNotEntitledError,
    HttpCommercialCoreClient,
    build_commercial_core_client,
)
from app.integrations.tenant_assertion import (
    TenantActor,
    TenantAssertionConfigurationError,
    TenantAssertionSigner,
    build_tenant_assertion_signer,
    tenant_actor_from_context,
)
from app.services.permissions import Permission
from tests.conftest import dev_auth_headers
from tests.intelligence_test_helpers import make_authorized_user, make_org

ISSUER = "https://sie.test/tenant-assertion"
KID = "sie-test-1"
ORG = uuid.UUID("6f1c2d4e-1a2b-4c3d-8e9f-0a1b2c3d4e5f")
USER = uuid.UUID("3b2a1c0d-9e8f-4d7c-a6b5-c4d3e2f1a0b9")
NOW = 1_800_000_000


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


@pytest.fixture
def key() -> Ed25519PrivateKey:
    return Ed25519PrivateKey.generate()


def _private_jwk(key: Ed25519PrivateKey, **override) -> str:
    jwk = {
        "kty": "OKP",
        "crv": "Ed25519",
        "x": _b64(key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)),
        "d": _b64(key.private_bytes(Encoding.Raw, PrivateFormat.Raw, NoEncryption())),
    }
    jwk.update(override)
    return json.dumps(jwk)


def _signer(key, **kwargs) -> TenantAssertionSigner:
    return TenantAssertionSigner(issuer=ISSUER, key_id=KID, private_key=key, **kwargs)


HUMAN_READ = TenantActor(actor_id=USER, actor_type=ActorType.HUMAN, permission=Permission.INTELLIGENCE_READ)


def _verify(token: str, key: Ed25519PrivateKey) -> tuple[dict, TenantAssertionClaims]:
    header = jwt.get_unverified_header(token)
    payload = jwt.decode(
        token,
        key.public_key(),
        algorithms=["EdDSA"],
        audience="sie-commercial-core",
        issuer=ISSUER,
        options={"verify_exp": False, "verify_iat": False},
    )
    return header, TenantAssertionClaims.model_validate(payload)


# --- Signing -----------------------------------------------------------------


def test_a_signed_assertion_verifies_with_the_public_key_and_matches_the_contract(key):
    token = _signer(key).sign(
        organization_id=ORG, actor=HUMAN_READ, capability=TenantCapability.ATTENTION_READ, request_id="req-0001", now=NOW
    )
    header, claims = _verify(token, key)

    assert header == {"alg": "EdDSA", "typ": "sie-tenant+jwt", "kid": KID}
    assert (claims.iss, claims.aud, claims.org, claims.sub, claims.act) == (
        ISSUER,
        "sie-commercial-core",
        ORG,
        USER,
        ActorType.HUMAN,
    )
    assert (claims.perm, claims.cap, claims.rid, claims.ver) == (
        "intelligence:read",
        TenantCapability.ATTENTION_READ,
        "req-0001",
        1,
    )
    assert (claims.iat, claims.exp) == (NOW, NOW + 60)
    assert claims.jti.version == 4


def test_every_assertion_has_its_own_jti(key):
    signer = _signer(key)
    sign = lambda: signer.sign(organization_id=ORG, actor=HUMAN_READ, capability=TenantCapability.ANALYTICS_READ)  # noqa: E731
    assert _verify(sign(), key)[1].jti != _verify(sign(), key)[1].jti


@pytest.mark.parametrize("request_id", [None, "", "has space", "x" * 129, "bad/slash"])
def test_a_request_id_commercial_core_would_not_keep_is_left_out(key, request_id):
    token = _signer(key).sign(
        organization_id=ORG, actor=HUMAN_READ, capability=TenantCapability.ATTENTION_READ, request_id=request_id
    )
    assert "rid" not in jwt.decode(token, options={"verify_signature": False})


def test_a_capability_the_permission_does_not_grant_is_never_signed(key):
    with pytest.raises(ValueError, match="cap is not granted by perm"):
        _signer(key).sign(organization_id=ORG, actor=HUMAN_READ, capability=TenantCapability.DECISIONS_WRITE)


def test_the_lifetime_is_configurable_but_never_over_the_contract_limit(key):
    token = _signer(key, lifetime_seconds=30).sign(
        organization_id=ORG, actor=HUMAN_READ, capability=TenantCapability.ATTENTION_READ, now=NOW
    )
    assert _verify(token, key)[1].exp == NOW + 30
    for bad in (0, 61):
        with pytest.raises(TenantAssertionConfigurationError, match="1-60"):
            _signer(key, lifetime_seconds=bad)


def test_actors_come_from_the_request_context():
    client_uuid = uuid.uuid4()
    human = tenant_actor_from_context(RequestContext(kind="human", user_id=USER), Permission.KNOWLEDGE_READ)
    machine = tenant_actor_from_context(
        RequestContext(kind="machine", api_client_id=client_uuid, client_id="ci-bot", machine_organization_id=ORG),
        Permission.INTELLIGENCE_DECISION_WRITE,
    )
    assert human == TenantActor(USER, ActorType.HUMAN, Permission.KNOWLEDGE_READ)
    assert machine == TenantActor(client_uuid, ActorType.MACHINE, Permission.INTELLIGENCE_DECISION_WRITE)
    with pytest.raises(ValueError):
        tenant_actor_from_context(RequestContext(kind="human"), Permission.KNOWLEDGE_READ)


# --- Configuration -------------------------------------------------------------


def _unset(monkeypatch):
    for name in ("SIGNING_KEY", "KEY_ID", "ISSUER"):
        monkeypatch.setattr(f"app.core.config.settings.COMMERCIAL_CORE_TENANT_ASSERTION_{name}", None)


def test_signing_is_off_until_configured(monkeypatch):
    _unset(monkeypatch)
    assert build_tenant_assertion_signer() is None


def test_signing_reads_its_settings(monkeypatch, key):
    _unset(monkeypatch)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_TENANT_ASSERTION_SIGNING_KEY", _private_jwk(key))
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_TENANT_ASSERTION_KEY_ID", KID)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_TENANT_ASSERTION_ISSUER", ISSUER)
    signer = build_tenant_assertion_signer()
    token = signer.sign(organization_id=ORG, actor=HUMAN_READ, capability=TenantCapability.ATTENTION_READ)
    _verify(token, key)


@pytest.mark.parametrize("missing", ["signing_key", "key_id", "issuer"])
def test_partial_configuration_fails_loud_without_echoing_the_key(monkeypatch, key, missing):
    _unset(monkeypatch)
    jwk = _private_jwk(key)
    kwargs = {"signing_key": jwk, "key_id": KID, "issuer": ISSUER}
    kwargs[missing] = ""
    with pytest.raises(TenantAssertionConfigurationError, match=missing.upper()) as raised:
        build_tenant_assertion_signer(**kwargs)
    assert json.loads(jwk)["d"] not in str(raised.value)


@pytest.mark.parametrize(
    "value",
    [
        "not json",
        '["OKP"]',
        "PEM",
        "wrong_curve",
        "public_only",
        "short_d",
    ],
)
def test_a_malformed_signing_key_is_refused(key, value):
    jwk = json.loads(_private_jwk(key))
    variants = {
        "PEM": "-----BEGIN PRIVATE KEY-----",
        "wrong_curve": json.dumps({**jwk, "crv": "X25519"}),
        "public_only": json.dumps({k: v for k, v in jwk.items() if k != "d"}),
        "short_d": json.dumps({**jwk, "d": _b64(b"x" * 16)}),
    }
    with pytest.raises(TenantAssertionConfigurationError, match="Ed25519 private JWK") as raised:
        build_tenant_assertion_signer(signing_key=variants.get(value, value), key_id=KID, issuer=ISSUER)
    assert jwk["d"] not in str(raised.value)


def test_a_key_whose_x_is_not_its_own_public_half_is_refused(key):
    other = Ed25519PrivateKey.generate()
    mismatched = _private_jwk(key, x=_b64(other.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)))
    with pytest.raises(TenantAssertionConfigurationError, match="does not match"):
        build_tenant_assertion_signer(signing_key=mismatched, key_id=KID, issuer=ISSUER)


def test_the_http_client_built_from_settings_signs_once_configured(monkeypatch, key):
    _unset(monkeypatch)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_BASE_URL", "https://cc.example")
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_CLIENT_ID", "public-sie")
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_CLIENT_SECRET", "dummy")
    assert build_commercial_core_client()._tenant_assertion_signer is None
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_TENANT_ASSERTION_SIGNING_KEY", _private_jwk(key))
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_TENANT_ASSERTION_KEY_ID", KID)
    monkeypatch.setattr("app.core.config.settings.COMMERCIAL_CORE_TENANT_ASSERTION_ISSUER", ISSUER)
    assert isinstance(build_commercial_core_client()._tenant_assertion_signer, TenantAssertionSigner)


# --- The client ------------------------------------------------------------------

_DECISION = {
    "scope": "organization",
    "site_id": None,
    "as_of": datetime(2026, 10, 1, tzinfo=timezone.utc),
    "window_days": 30,
    "attention_reference": "ref",
    "decision_type": "ACKNOWLEDGED",
    "rationale": "r",
    "linked_action_id": None,
}

# (method, kwargs, permission it is called under, capability it must assert)
_CALLS = [
    ("get_attention", {"scope": "organization", "site_id": None, "as_of": None, "window_days": None}, Permission.INTELLIGENCE_READ, TenantCapability.ATTENTION_READ),
    ("get_analytics_summary", {"site_id": None, "as_of": None, "window_days": None}, Permission.INTELLIGENCE_READ, TenantCapability.ANALYTICS_READ),
    ("get_analytics_trends", {"metric": "event_count", "site_id": None, "as_of": None, "window_days": None}, Permission.INTELLIGENCE_READ, TenantCapability.ANALYTICS_READ),
    ("get_analytics_signals", {"site_id": None, "as_of": None, "window_days": None}, Permission.INTELLIGENCE_READ, TenantCapability.ANALYTICS_READ),
    ("get_enterprise_intelligence", {"scope": "organization", "site_id": None, "as_of": None, "window_days": None}, Permission.INTELLIGENCE_READ, TenantCapability.ENTERPRISE_INTELLIGENCE_READ),
    ("create_decision", {**_DECISION, "actor_type": ActorType.HUMAN, "actor_id": USER}, Permission.INTELLIGENCE_DECISION_WRITE, TenantCapability.DECISIONS_WRITE),
    ("get_decision", {"decision_id": uuid.uuid4()}, Permission.INTELLIGENCE_READ, TenantCapability.DECISIONS_READ),
    ("list_decisions", {"site_id": None, "attention_reference": None, "decision_type": None, "linked_action_id": None, "page": 1, "page_size": 20}, Permission.INTELLIGENCE_READ, TenantCapability.DECISIONS_READ),
    ("query_rag", {"query": "What applies?", "top_k": None}, Permission.KNOWLEDGE_READ, TenantCapability.RAG_QUERY),
]


def _client(signer=None) -> HttpCommercialCoreClient:
    return HttpCommercialCoreClient(
        base_url="https://cc.example",
        client_id="public-sie",
        client_secret="dummy",
        timeout_seconds=5.0,
        tenant_assertion_signer=signer,
    )


def _answer(monkeypatch, status: int, body: dict, sent: list):
    def post(url, *, json, headers, timeout):
        sent.append(headers)
        return httpx.Response(status, json=body, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", post)


_UNAVAILABLE = {"error_code": "DEPENDENCY_UNAVAILABLE", "message": "down", "retryable": True}


@pytest.mark.parametrize("method,kwargs,permission,capability", _CALLS, ids=[c[0] for c in _CALLS])
def test_every_call_asserts_exactly_its_own_capability(monkeypatch, key, method, kwargs, permission, capability):
    sent: list = []
    _answer(monkeypatch, 503, _UNAVAILABLE, sent)
    actor = TenantActor(USER, ActorType.HUMAN, permission)
    with pytest.raises(Exception):
        getattr(_client(_signer(key)), method)(organization_id=ORG, request_id="req-7", tenant_actor=actor, **kwargs)

    _, claims = _verify(sent[0][TENANT_ASSERTION_HEADER], key)
    assert (claims.org, claims.sub, claims.perm, claims.cap, claims.rid) == (
        ORG,
        USER,
        permission.value,
        capability,
        "req-7",
    )
    assert sent[0]["X-Organization-Id"] == str(ORG)  # the legacy header still goes too


@pytest.mark.parametrize("method,kwargs,permission,capability", _CALLS, ids=[c[0] for c in _CALLS])
def test_without_a_signer_no_assertion_is_sent(monkeypatch, method, kwargs, permission, capability):
    sent: list = []
    _answer(monkeypatch, 503, _UNAVAILABLE, sent)
    with pytest.raises(Exception):
        getattr(_client(), method)(
            organization_id=ORG, request_id=None, tenant_actor=TenantActor(USER, ActorType.HUMAN, permission), **kwargs
        )
    assert TENANT_ASSERTION_HEADER not in sent[0]


@pytest.mark.parametrize("method", ["get_attention", "get_analytics_summary"])
def test_a_rejected_assertion_and_a_missing_entitlement_are_typed(monkeypatch, key, method):
    kwargs = dict(next(c[1] for c in _CALLS if c[0] == method))
    actor = TenantActor(USER, ActorType.HUMAN, Permission.INTELLIGENCE_READ)
    call = lambda: getattr(_client(_signer(key)), method)(organization_id=ORG, request_id=None, tenant_actor=actor, **kwargs)  # noqa: E731

    _answer(monkeypatch, 401, {"error_code": "TENANT_ASSERTION_INVALID", "message": "Tenant assertion rejected.", "retryable": False}, [])
    with pytest.raises(CommercialCoreTenantAssertionRejectedError) as raised:
        call()
    assert isinstance(raised.value, CommercialCoreAuthenticationError)

    _answer(monkeypatch, 403, {"error_code": "TENANT_NOT_ENTITLED", "message": "Not enabled for this organization.", "retryable": False}, [])
    with pytest.raises(CommercialCoreTenantNotEntitledError):
        call()


# --- The routers -------------------------------------------------------------------


class _NotEntitledClient:
    def __init__(self):
        self.actors: list = []

    def _refuse(self, **kwargs):
        self.actors.append(kwargs.get("tenant_actor"))
        raise CommercialCoreTenantNotEntitledError("Commercial Core is not enabled for this organization.")

    get_attention = get_analytics_summary = get_enterprise_intelligence = list_decisions = query_rag = _refuse


@pytest.mark.parametrize(
    "path,body,permission",
    [
        ("/api/v1/intelligence/attention?organization_id={org}", None, Permission.INTELLIGENCE_READ),
        ("/api/v1/intelligence/analytics/summary?organization_id={org}", None, Permission.INTELLIGENCE_READ),
        ("/api/v1/intelligence/decisions?organization_id={org}", None, Permission.INTELLIGENCE_READ),
        ("/api/v1/knowledge/rag/query", "rag", Permission.KNOWLEDGE_READ),
    ],
)
def test_routers_send_the_actor_and_answer_403_when_not_entitled(client, db_session, monkeypatch, path, body, permission):
    org = make_org(db_session, "Entitlement Org")
    user = make_authorized_user(db_session, org.id)
    fake = _NotEntitledClient()
    for module in ("intelligence", "intelligence_decisions", "rag"):
        monkeypatch.setattr(f"app.api.v1.{module}.get_commercial_core_client", lambda: fake)
    url = path.format(org=org.id)
    if body == "rag":
        response = client.post(url, json={"query": "What applies?", "filters": {"organization_id": str(org.id)}}, headers=dev_auth_headers(user.id))
    else:
        response = client.get(url, headers=dev_auth_headers(user.id))

    assert response.status_code == 403, response.text
    assert response.json()["error"]["details"] == {"reason": "TENANT_NOT_ENTITLED"}
    assert fake.actors == [TenantActor(user.id, ActorType.HUMAN, permission)]


def test_the_key_generator_pairs_with_the_signer():
    """The generator's output loads in the signer, and the public map is
    exactly the shape Commercial Core's verifiers accept: {kty, crv, x}."""
    from scripts.generate_tenant_assertion_key import generate

    private_jwk, public_map = generate("sie-test-gen")
    signer = build_tenant_assertion_signer(signing_key=private_jwk, key_id="sie-test-gen", issuer=ISSUER)
    token = signer.sign(organization_id=ORG, actor=HUMAN_READ, capability=TenantCapability.ATTENTION_READ)

    (kid, public_jwk), = json.loads(public_map).items()
    assert kid == "sie-test-gen" and set(public_jwk) == {"kty", "crv", "x"}
    raw = base64.urlsafe_b64decode(public_jwk["x"] + "=" * (-len(public_jwk["x"]) % 4))
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

    jwt.decode(token, Ed25519PublicKey.from_public_bytes(raw), algorithms=["EdDSA"], audience="sie-commercial-core")
