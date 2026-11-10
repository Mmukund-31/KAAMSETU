"""PATCH /auth/me: a user changes their own preferred language (Phase 8)."""

from app.models import AuditLog
from app.models.enums import UserRole


def test_user_changes_own_language_and_it_is_audited(client, db, make_user, auth_headers):
    tech = make_user(UserRole.TECHNICIAN)
    response = client.patch("/api/v1/auth/me", json={"preferred_language": "te"}, headers=auth_headers(tech))
    assert response.status_code == 200
    assert response.json()["preferred_language"] == "te"
    assert client.get("/api/v1/auth/me", headers=auth_headers(tech)).json()["preferred_language"] == "te"
    rows = db.query(AuditLog).filter(AuditLog.entity_id == tech.id, AuditLog.action == "user.update").all()
    assert [(r.previous_value, r.new_value) for r in rows] == [({"preferred_language": "en"}, {"preferred_language": "te"})]


def test_same_language_is_a_no_op(client, db, make_user, auth_headers):
    tech = make_user(UserRole.TECHNICIAN)
    assert client.patch("/api/v1/auth/me", json={"preferred_language": "en"}, headers=auth_headers(tech)).status_code == 200
    assert db.query(AuditLog).filter(AuditLog.entity_id == tech.id).count() == 0


def test_only_the_language_can_be_changed(client, make_user, auth_headers):
    tech = make_user(UserRole.TECHNICIAN)
    response = client.patch("/api/v1/auth/me", json={"preferred_language": "hi", "role": "manager"}, headers=auth_headers(tech))
    assert response.status_code == 200
    assert response.json()["role"] == "technician"  # extra fields are ignored, never applied


def test_unknown_language_is_rejected(client, make_user, auth_headers):
    tech = make_user(UserRole.TECHNICIAN)
    assert client.patch("/api/v1/auth/me", json={"preferred_language": "fr"}, headers=auth_headers(tech)).status_code == 422
