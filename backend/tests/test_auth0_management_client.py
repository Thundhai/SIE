"""app/integrations/auth0_management.py against a simulated Auth0
(httpx.MockTransport). No network."""

import json
import re

import httpx
import pytest

from app.integrations.auth0_management import (
    Auth0ManagementClient,
    Auth0ManagementError,
    random_initial_password,
)

DOMAIN = "tenant.example.auth0.com"
CONNECTION = "Username-Password-Authentication"


class FakeAuth0Server:
    def __init__(self):
        self.requests: list[httpx.Request] = []
        self.token_calls = 0
        self.users_by_email: list = []
        self.create_status = 201
        self.fail_with: int | None = None

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_with:
            return httpx.Response(self.fail_with)
        path = request.url.path
        if path == "/oauth/token":
            self.token_calls += 1
            return httpx.Response(200, json={"access_token": f"mgmt-token-{self.token_calls}", "expires_in": 86400})
        assert request.headers.get("Authorization", "").startswith("Bearer mgmt-token-") or path.startswith("/dbconnections")
        if path == "/api/v2/users-by-email":
            return httpx.Response(200, json=self.users_by_email)
        if path == "/api/v2/users" and request.method == "POST":
            if self.create_status == 409:
                return httpx.Response(409, json={"message": "The user already exists."})
            payload = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "user_id": "auth0|created",
                    "email": payload["email"],
                    "email_verified": False,
                    "app_metadata": payload["app_metadata"],
                },
            )
        if path.startswith("/api/v2/users/"):
            if path.endswith("missing"):
                return httpx.Response(404)
            return httpx.Response(200, json={"user_id": "auth0|abc", "email": "A@Example.com", "email_verified": True})
        if path == "/dbconnections/change_password":
            return httpx.Response(200, text="We've just sent you an email to reset your password.")
        return httpx.Response(500)


@pytest.fixture
def server():
    return FakeAuth0Server()


@pytest.fixture
def client(server):
    return Auth0ManagementClient(
        domain=DOMAIN,
        client_id="m2m-id",
        client_secret="m2m-secret",
        connection=CONNECTION,
        password_email_client_id="spa-id",
        http=httpx.Client(transport=httpx.MockTransport(server)),
    )


def test_the_management_token_is_fetched_once_and_reused(client, server):
    client.get_user("auth0|abc")
    client.get_user("auth0|abc")

    assert server.token_calls == 1
    token_request = json.loads(server.requests[0].content)
    assert token_request["grant_type"] == "client_credentials"
    assert token_request["audience"] == f"https://{DOMAIN}/api/v2/"


def test_find_by_email_only_returns_the_database_connection_user(client, server):
    server.users_by_email = [
        {"user_id": "google-oauth2|1", "email": "a@example.com", "email_verified": True,
         "identities": [{"connection": "google-oauth2"}]},
        {"user_id": "auth0|2", "email": "a@example.com", "email_verified": False,
         "identities": [{"connection": CONNECTION}], "app_metadata": {"sie_provisioned": True}},
    ]

    user = client.find_user_by_email(" A@Example.com ")

    assert user.user_id == "auth0|2"
    assert user.email_verified is False and user.sie_provisioned is True
    lookup = next(r for r in server.requests if r.url.path == "/api/v2/users-by-email")
    assert lookup.url.params["email"] == "a@example.com"


def test_find_by_email_ignores_other_connections_entirely(client, server):
    server.users_by_email = [
        {"user_id": "google-oauth2|1", "email": "a@example.com", "email_verified": True,
         "identities": [{"connection": "google-oauth2"}]},
    ]

    assert client.find_user_by_email("a@example.com") is None


def test_create_user_tags_the_account_and_never_verifies_the_email(client, server):
    user = client.create_user("New@Example.com", "New Person")

    assert user.user_id == "auth0|created" and user.sie_provisioned is True
    create = next(r for r in server.requests if r.url.path == "/api/v2/users")
    payload = json.loads(create.content)
    assert payload["connection"] == CONNECTION
    assert payload["email"] == "new@example.com"
    assert payload["email_verified"] is False and payload["verify_email"] is False
    assert payload["app_metadata"] == {"sie_provisioned": True}
    assert len(payload["password"]) == 40


def test_create_user_conflict_falls_back_to_the_existing_account(client, server):
    server.create_status = 409
    server.users_by_email = [
        {"user_id": "auth0|raced", "email": "new@example.com", "email_verified": False,
         "identities": [{"connection": CONNECTION}], "app_metadata": {"sie_provisioned": True}},
    ]

    assert client.create_user("new@example.com", None).user_id == "auth0|raced"


def test_get_user_returns_none_for_a_missing_account_and_normalizes_the_email(client):
    assert client.get_user("auth0|missing") is None
    assert client.get_user("auth0|abc").email == "a@example.com"


def test_set_password_email_uses_the_spa_client_and_the_database_connection(client, server):
    client.send_set_password_email("Person@Example.com")

    request = next(r for r in server.requests if r.url.path == "/dbconnections/change_password")
    assert json.loads(request.content) == {
        "client_id": "spa-id",
        "email": "person@example.com",
        "connection": CONNECTION,
    }
    assert "Authorization" not in request.headers


def test_every_failure_is_an_auth0_management_error_without_secrets(client, server):
    server.fail_with = 500
    with pytest.raises(Auth0ManagementError) as caught:
        client.find_user_by_email("a@example.com")
    assert "m2m-secret" not in str(caught.value) and "a@example.com" not in str(caught.value)


def test_network_errors_become_auth0_management_errors():
    def boom(request):
        raise httpx.ConnectError("refused")

    broken = Auth0ManagementClient(
        domain=DOMAIN,
        client_id="id",
        client_secret="secret",
        connection=CONNECTION,
        password_email_client_id="spa",
        http=httpx.Client(transport=httpx.MockTransport(boom)),
    )
    with pytest.raises(Auth0ManagementError, match="ConnectError"):
        broken.get_user("auth0|abc")


def test_initial_passwords_meet_auth0s_strictest_policy():
    for _ in range(200):
        password = random_initial_password()
        assert len(password) == 40
        assert re.search(r"[a-z]", password) and re.search(r"[A-Z]", password) and re.search(r"\d", password)
        assert re.search(r"[!@#$%^&*\-_=+]", password)
        assert not re.search(r"(.)\1\1", password)
    assert random_initial_password() != random_initial_password()


def test_error_messages_never_carry_a_user_id(client, server):
    client.get_user("auth0|abc")  # token cached, so the failure below is the user lookup itself
    server.fail_with = 503
    with pytest.raises(Auth0ManagementError) as caught:
        client.get_user("auth0|secret-subject")
    assert "/api/v2/users/{id}" in str(caught.value)
    assert "secret-subject" not in str(caught.value)
