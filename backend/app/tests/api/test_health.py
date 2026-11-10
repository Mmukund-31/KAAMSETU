def test_liveness(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_versioned_health_reports_gnani_presence_not_key(client):
    r = client.get("/api/v1/health")
    body = r.json()
    assert r.status_code == 200
    assert isinstance(body["gnani_configured"], bool)
    assert "key" not in " ".join(body.keys()).lower()


def test_db_health_reports_migration_revision(client):
    from alembic.script import ScriptDirectory

    from app.tests.conftest import alembic_config

    head = ScriptDirectory.from_config(alembic_config("unused")).get_current_head()
    r = client.get("/api/v1/health/db")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok", "migration_revision": head}


def test_request_id_header_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_openapi_schema_and_docs_render(client):
    """Guards /docs: a bad `responses=` declaration once made schema generation fail with a 500."""
    r = client.get("/openapi.json")
    assert r.status_code == 200
    paths = set(r.json()["paths"])
    expected = {"/api/v1/auth/login", "/api/v1/auth/register", "/api/v1/auth/me", "/api/v1/health",
                "/api/v1/health/db", "/api/v1/voice/transcribe", "/api/v1/voice/synthesize",
                "/api/v1/voice/process-report", "/api/v1/voice/process-text", "/api/v1/voice/follow-up",
                "/api/v1/voice/evaluate-draft"}
    assert expected <= paths, expected - paths
    assert client.get("/docs").status_code == 200


def test_oversized_request_rejected_with_413(client):
    r = client.post("/api/v1/auth/login", content=b"x", headers={"Content-Length": str(50 * 1024 * 1024)})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
