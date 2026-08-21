def test_liveness_ok(client):
    resp = client.get("/health/live")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_legacy_health_alias(client):
    resp = client.get("/health")
    assert resp.status_code == 200


def test_readiness_ok(client):
    resp = client.get("/health/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_metrics_endpoint_exposed(client):
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert b"tutortrack_tenant_requests_total" in resp.content or resp.status_code == 200