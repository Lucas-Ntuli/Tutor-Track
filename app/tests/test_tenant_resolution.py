def test_unknown_tenant_returns_404(unknown_tenant_client):
    resp = unknown_tenant_client.get("/students")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Unknown tenant"


def test_missing_tenant_header_returns_404():
    from fastapi.testclient import TestClient
    from main import app

    resp = TestClient(app).get("/students")
    assert resp.status_code == 404


def test_request_id_header_present_on_every_response(client):
    resp = client.get("/health/live")
    assert "x-request-id" in resp.headers

    # Caller-supplied request IDs are echoed back, not replaced -
    # important so a client's own trace ID survives round-trip.
    resp2 = client.get("/health/live", headers={"x-request-id": "abc-123"})
    assert resp2.headers["x-request-id"] == "abc-123"