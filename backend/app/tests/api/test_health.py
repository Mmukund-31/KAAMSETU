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
    r = client.get("/api/v1/health/db")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "database": "ok", "migration_revision": "0001"}


def test_request_id_header_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_unknown_route_uses_error_envelope(client):
    r = client.get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"


def test_oversized_request_rejected_with_413(client):
    r = client.post("/api/v1/auth/login", content=b"x", headers={"Content-Length": str(50 * 1024 * 1024)})
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "payload_too_large"
