import uuid
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.models import AuditLog, User, UserRole
from app.tests.conftest import TEST_PASSWORD

LOGIN = "/api/v1/auth/login"
ME = "/api/v1/auth/me"
REGISTER = "/api/v1/auth/register"


def new_user_body(role: str = "technician", **overrides):
    body = {"name": "New Person", "email": f"new-{uuid.uuid4().hex[:8]}@test.local", "password": "Secret123",
            "role": role, "preferred_language": "hi"}
    body.update(overrides)
    return body


# ── login ────────────────────────────────────────────────────────────────

def test_login_success_returns_token_and_user(client, make_user):
    user = make_user(UserRole.SUPERVISOR)
    r = client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    assert r.status_code == 200
    body = r.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"].count(".") == 2
    assert body["user"]["email"] == user.email
    assert body["user"]["role"] == "supervisor"
    assert "password_hash" not in body["user"]


def test_login_email_is_case_insensitive(client, make_user):
    user = make_user()
    r = client.post(LOGIN, json={"email": user.email.upper(), "password": TEST_PASSWORD})
    assert r.status_code == 200


def test_login_wrong_password(client, make_user):
    user = make_user()
    r = client.post(LOGIN, json={"email": user.email, "password": "WrongPass999"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_email_gives_identical_error(client, make_user):
    user = make_user()
    wrong_pw = client.post(LOGIN, json={"email": user.email, "password": "WrongPass999"}).json()
    unknown = client.post(LOGIN, json={"email": "nobody@test.local", "password": "WrongPass999"}).json()
    assert unknown == wrong_pw


def test_login_disabled_account(client, make_user):
    user = make_user(active=False)
    r = client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "account_disabled"


def test_validation_error_never_echoes_password(client):
    r = client.post(LOGIN, json={"email": "not-an-email", "password": "SuperSecretValue1"})
    assert r.status_code == 422
    assert "SuperSecretValue1" not in r.text
    assert r.json()["error"]["code"] == "validation_error"


def test_login_rate_limited(client, make_user, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "rate_limit_enabled", True)
    monkeypatch.setattr(settings, "rate_limit_login_per_minute", 3)
    limiter.reset()
    user = make_user()
    codes = [client.post(LOGIN, json={"email": user.email, "password": "WrongPass999"}).status_code for _ in range(4)]
    assert codes == [401, 401, 401, 429]
    last = client.post(LOGIN, json={"email": user.email, "password": TEST_PASSWORD})
    assert last.status_code == 429
    assert int(last.headers["Retry-After"]) >= 1


# ── me / token handling ──────────────────────────────────────────────────

def test_me_returns_current_user(client, make_user, auth_headers):
    user = make_user(UserRole.MANAGER)
    r = client.get(ME, headers=auth_headers(user))
    assert r.status_code == 200
    assert r.json()["id"] == str(user.id)
    assert r.json()["site"]["name"] == "Test Plant"


def test_me_without_token(client):
    r = client.get(ME)
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"
    assert r.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.parametrize("token", ["garbage", "a.b.c", ""])
def test_me_with_invalid_token(client, token):
    r = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_me_with_expired_token(client, make_user):
    user = make_user()
    token, _ = create_access_token(user.id, user.role.value, expires_delta=timedelta(seconds=-5))
    r = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "token_expired"


def test_token_signed_with_other_secret_rejected(client, make_user):
    import jwt

    user = make_user()
    forged = jwt.encode({"sub": str(user.id), "role": "manager", "type": "access", "iat": 0, "exp": 9999999999},
                        "attacker-controlled-secret-of-sufficient-length", algorithm="HS256")
    assert client.get(ME, headers={"Authorization": f"Bearer {forged}"}).status_code == 401


def test_token_for_nonexistent_user_rejected(client):
    token, _ = create_access_token(uuid.uuid4(), "manager")
    r = client.get(ME, headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_role_comes_from_database_not_token(client, make_user, auth_headers):
    """A technician holding a token that claims 'manager' must still be treated as a technician."""
    tech = make_user(UserRole.TECHNICIAN)
    token, _ = create_access_token(tech.id, "manager")
    r = client.post(REGISTER, json=new_user_body(), headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_deactivated_user_token_stops_working(client, db, make_user, auth_headers):
    user = make_user()
    headers = auth_headers(user)
    assert client.get(ME, headers=headers).status_code == 200
    user.is_active = False
    db.flush()
    assert client.get(ME, headers=headers).status_code == 401


# ── register / RBAC ──────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["technician", "supervisor", "manager"])
def test_manager_can_create_any_role(client, make_user, auth_headers, role):
    manager = make_user(UserRole.MANAGER)
    r = client.post(REGISTER, json=new_user_body(role), headers=auth_headers(manager))
    assert r.status_code == 201, r.text
    assert r.json()["role"] == role
    assert r.json()["site_id"] == str(manager.site_id)


def test_supervisor_can_create_technician(client, make_user, auth_headers):
    sup = make_user(UserRole.SUPERVISOR)
    r = client.post(REGISTER, json=new_user_body("technician"), headers=auth_headers(sup))
    assert r.status_code == 201


@pytest.mark.parametrize("role", ["supervisor", "manager"])
def test_supervisor_cannot_create_higher_roles(client, make_user, auth_headers, role):
    sup = make_user(UserRole.SUPERVISOR)
    r = client.post(REGISTER, json=new_user_body(role), headers=auth_headers(sup))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "role_not_permitted"


def test_supervisor_cannot_create_user_at_other_site(client, db, make_user, auth_headers):
    from app.models import Site

    other = Site(name="Other Plant")
    db.add(other)
    db.flush()
    sup = make_user(UserRole.SUPERVISOR)
    r = client.post(REGISTER, json=new_user_body(site_id=str(other.id)), headers=auth_headers(sup))
    assert r.status_code == 403


def test_technician_cannot_register_anyone(client, make_user, auth_headers):
    tech = make_user(UserRole.TECHNICIAN)
    r = client.post(REGISTER, json=new_user_body(), headers=auth_headers(tech))
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_role"


def test_register_requires_authentication(client):
    assert client.post(REGISTER, json=new_user_body()).status_code == 401


def test_register_duplicate_email(client, make_user, auth_headers):
    manager = make_user(UserRole.MANAGER)
    existing = make_user()
    r = client.post(REGISTER, json=new_user_body(email=existing.email.upper()), headers=auth_headers(manager))
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


@pytest.mark.parametrize("password", ["short1", "allletters", "12345678"])
def test_register_rejects_weak_password(client, make_user, auth_headers, password):
    manager = make_user(UserRole.MANAGER)
    r = client.post(REGISTER, json=new_user_body(password=password), headers=auth_headers(manager))
    assert r.status_code == 422
    assert password not in r.text


def test_register_unknown_site(client, make_user, auth_headers):
    manager = make_user(UserRole.MANAGER)
    r = client.post(REGISTER, json=new_user_body(site_id=str(uuid.uuid4())), headers=auth_headers(manager))
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "unknown_site"


def test_register_writes_audit_log_and_stores_hash(client, db, make_user, auth_headers):
    manager = make_user(UserRole.MANAGER)
    body = new_user_body()
    r = client.post(REGISTER, json=body, headers=auth_headers(manager))
    new_id = uuid.UUID(r.json()["id"])

    stored = db.get(User, new_id)
    assert stored.password_hash.startswith("$argon2id$")
    assert body["password"] not in stored.password_hash

    entry = db.scalar(select(AuditLog).where(AuditLog.entity_id == new_id))
    assert entry.action == "user.create"
    assert entry.actor_id == manager.id
    assert "password" not in str(entry.new_value).lower()


def test_new_user_can_log_in(client, make_user, auth_headers):
    manager = make_user(UserRole.MANAGER)
    body = new_user_body()
    client.post(REGISTER, json=body, headers=auth_headers(manager))
    r = client.post(LOGIN, json={"email": body["email"], "password": body["password"]})
    assert r.status_code == 200
    assert r.json()["user"]["preferred_language"] == "hi"
