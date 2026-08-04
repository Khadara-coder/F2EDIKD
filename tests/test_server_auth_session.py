from __future__ import annotations

import pytest

pytest.importorskip("fastapi", reason="fastapi not installed")

from fastapi.testclient import TestClient

import server
import src.file2edi.store as store_mod


class FakeStore:
    def __init__(self, users: dict[str, dict]):
        self.users = users
        self.invalidated: list[str] = []
        self.created_users: list[dict] = []
        self.password_changes: list[tuple[str, str]] = []

    def get_session_user(self, session_id: str):
        return self.users.get(session_id)

    def verify_credentials(self, username: str, password: str):
        return None

    def create_user(self, **kwargs):
        if kwargs["username"] == "existing-admin":
            raise ValueError("duplicate username")
        user = {
            "userId": "usr-created",
            "username": kwargs["username"],
            "displayName": kwargs["display_name"],
            "email": kwargs.get("email", ""),
            "sapId": kwargs.get("sap_id", ""),
            "role": kwargs.get("role", "adv"),
        }
        self.created_users.append(user)
        return user

    def create_session(self, user_id: str, ip: str | None = None):
        return f"session-for-{user_id}"

    def list_users(self):
        return [
            {
                "userId": "usr-existing",
                "username": "existing-admin",
                "displayName": "Existing Admin",
                "email": "",
                "sapId": "",
                "role": "admin",
            }
        ]

    def change_password(self, user_id: str, password: str) -> None:
        self.password_changes.append((user_id, password))

    def update_user(self, user_id: str, **kwargs):
        return None

    def invalidate_session(self, session_id: str) -> None:
        self.invalidated.append(session_id)


@pytest.fixture()
def client(monkeypatch: pytest.MonkeyPatch):
    async def _noop_init_postgres_db():
        return None

    monkeypatch.setattr(server, "_init_postgres_db", _noop_init_postgres_db)
    with TestClient(server.app, raise_server_exceptions=False) as tc:
        yield tc


def test_api_me_uses_postgres_session_role(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    fake_store = FakeStore({
        "admin-session": {
            "username": "admin",
            "displayName": "Admin Test",
            "role": "admin",
        }
    })
    monkeypatch.setattr(store_mod, "get_store", lambda: fake_store)

    response = client.get("/api/me", cookies={"f2edi_session": "admin-session"})

    assert response.status_code == 200
    assert response.json() == {
        "actor": "admin",
        "username": "admin",
        "displayName": "Admin Test",
        "role": "admin",
        "authenticated": True,
    }


def test_api_me_rejects_stale_postgres_session(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    fake_store = FakeStore({})
    monkeypatch.setattr(store_mod, "get_store", lambda: fake_store)

    response = client.get("/api/me", cookies={"f2edi_session": "expired-session"})

    assert response.status_code == 200
    assert response.json() == {
        "actor": "",
        "username": "",
        "displayName": "",
        "role": "adv",
        "authenticated": False,
    }


def test_logout_invalidates_postgres_session(monkeypatch: pytest.MonkeyPatch, client: TestClient):
    fake_store = FakeStore({})
    monkeypatch.setattr(store_mod, "get_store", lambda: fake_store)

    response = client.post("/api/auth/logout", cookies={"f2edi_session": "admin-session"})

    assert response.status_code == 200
    assert fake_store.invalidated == ["admin-session"]
    assert "f2edi_session=" in response.headers.get("set-cookie", "")


def test_configured_admin_profile_login_works_without_global_shared_fallback(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    fake_store = FakeStore({})
    monkeypatch.setattr(store_mod, "get_store", lambda: fake_store)
    monkeypatch.setattr(server, "ENABLE_PROFILE_LOGIN", True)
    monkeypatch.setattr(server, "_ALLOW_SHARED_PASSWORD_LOGIN", False)
    monkeypatch.setenv("APP_ADMIN_USERS", "dik1dy@bosch.com,dik1dy,khadara")
    monkeypatch.delenv("APP_PROFILE_LOGIN_PASSWORD", raising=False)

    response = client.post(
        "/api/auth/login",
        json={"actor": "khadara", "password": "admin123", "role": "adv"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["actor"] == "khadara"
    assert body["role"] == "admin"
    assert fake_store.created_users[0]["username"] == "khadara"
    assert fake_store.created_users[0]["role"] == "admin"
    assert "f2edi_session=" in response.headers.get("set-cookie", "")


def test_configured_admin_profile_login_resets_existing_postgres_user_password(
    monkeypatch: pytest.MonkeyPatch,
    client: TestClient,
):
    fake_store = FakeStore({})
    monkeypatch.setattr(store_mod, "get_store", lambda: fake_store)
    monkeypatch.setattr(server, "ENABLE_PROFILE_LOGIN", True)
    monkeypatch.setattr(server, "_ALLOW_SHARED_PASSWORD_LOGIN", False)
    monkeypatch.setenv("APP_ADMIN_USERS", "existing-admin")
    monkeypatch.delenv("APP_PROFILE_LOGIN_PASSWORD", raising=False)

    response = client.post(
        "/api/auth/login",
        json={"actor": "existing-admin", "password": "admin123", "role": "adv"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["actor"] == "existing-admin"
    assert body["role"] == "admin"
    assert fake_store.password_changes == [("usr-existing", "admin123")]
