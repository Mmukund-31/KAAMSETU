"""Security review checks (Phase 8): every route is authenticated, supervisor routes refuse technicians,
security headers are present, and production hides the API map.

The route list is read from the app itself, so a new route that forgets its auth dependency fails here.
"""

import re
import uuid

import pytest
from fastapi.routing import APIRoute

from app.config import Settings
from app.main import create_app
from app.models.enums import UserRole

PUBLIC = {
    ("GET", "/health"),
    ("GET", "/api/v1/health"),
    ("GET", "/api/v1/health/db"),
    ("POST", "/api/v1/auth/login"),
}

# Routes that only supervisors and managers may use. A technician must get 403 before any lookup happens.
SUPERVISOR_ONLY = {
    ("POST", "/api/v1/auth/register"),
    ("GET", "/api/v1/users"),
    ("POST", "/api/v1/equipment"),
    ("POST", "/api/v1/checklists/templates"),
    ("POST", "/api/v1/checklists/templates/{template_id}/deactivate"),
    ("POST", "/api/v1/handovers/{handover_id}/review"),
    ("GET", "/api/v1/dashboard/overview"),
    ("GET", "/api/v1/dashboard/work-order-trends"),
    ("GET", "/api/v1/dashboard/equipment-issues"),
    ("GET", "/api/v1/dashboard/technician-workload"),
    ("GET", "/api/v1/audit-logs"),
}


def _routes():
    """Every route: the OpenAPI schema (all API routes) plus the routes outside it, such as /health."""
    app = create_app()
    for path, operations in app.openapi()["paths"].items():
        for method in operations:
            yield method.upper(), path
    for route in app.routes:
        if isinstance(route, APIRoute) and not route.include_in_schema:
            for method in route.methods - {"HEAD", "OPTIONS"}:
                yield method, route.path


def _concrete(path: str) -> str:
    return re.sub(r"\{[^}]+\}", str(uuid.uuid4()), path)


ALL_ROUTES = sorted(set(_routes()))


def test_the_route_inventory_is_what_we_reviewed():
    # 44 operations on 38 API paths (PATCH /auth/me added in Phase 8), plus the unversioned /health probe. A new route makes this fail on purpose:
    # decide whether it is public or supervisor-only, then update the lists above and this count.
    assert len(ALL_ROUTES) == 45, ALL_ROUTES
    assert PUBLIC <= set(ALL_ROUTES)
    assert SUPERVISOR_ONLY <= set(ALL_ROUTES)


@pytest.mark.parametrize("method, path", [r for r in ALL_ROUTES if r not in PUBLIC])
def test_every_non_public_route_requires_a_token(client, method, path):
    response = client.request(method, _concrete(path), json={})
    assert response.status_code == 401, f"{method} {path} -> {response.status_code}"
    assert response.json()["error"]["code"] in {"not_authenticated", "invalid_token"}


@pytest.mark.parametrize("method, path", sorted(SUPERVISOR_ONLY))
def test_supervisor_routes_refuse_technicians(client, make_user, auth_headers, method, path):
    tech = make_user(UserRole.TECHNICIAN)
    response = client.request(method, _concrete(path), json={}, headers=auth_headers(tech))
    assert response.status_code == 403, f"{method} {path} -> {response.status_code}"


def test_a_forged_token_is_refused(client, make_user):
    import jwt

    user = make_user(UserRole.MANAGER)
    forged = jwt.encode({"sub": str(user.id), "role": "manager", "type": "access", "exp": 9999999999},
                        "not-the-server-secret", algorithm="HS256")
    response = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {forged}"})
    assert response.status_code == 401


def test_unsigned_alg_none_token_is_refused(client, make_user):
    import base64
    import json

    user = make_user(UserRole.MANAGER)

    def part(data):
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b"=").decode()

    token = f"{part({'alg': 'none', 'typ': 'JWT'})}.{part({'sub': str(user.id), 'type': 'access', 'exp': 9999999999})}."
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 401


def test_security_headers_on_api_responses(client):
    response = client.get("/api/v1/health")
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"
    assert response.headers["Referrer-Policy"] == "no-referrer"
    assert response.headers["Cache-Control"] == "no-store"


def test_errors_do_not_leak_internals(client):
    response = client.get(f"/api/v1/work-orders/{uuid.uuid4()}", headers={"Authorization": "Bearer x.y.z"})
    body = response.text.lower()
    assert "traceback" not in body and "sqlalchemy" not in body and "select " not in body


def test_production_hides_the_api_map(monkeypatch):
    from fastapi.testclient import TestClient

    import app.main as main

    monkeypatch.setattr(main, "get_settings", lambda: Settings(app_env="production", jwt_secret_key="x" * 40,
                                                               database_url="postgresql+pg8000://u:p@localhost/db"))
    client = TestClient(main.create_app())
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_production_refuses_wildcard_cors():
    with pytest.raises(ValueError, match="CORS_ORIGINS"):
        Settings(app_env="production", jwt_secret_key="x" * 40, cors_origins="*")
