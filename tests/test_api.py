import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from tests.conftest import FakeGenerator, make_payload


@pytest.fixture
def client():
    with TestClient(create_app(Settings(), FakeGenerator())) as c:
        yield c


def test_health(client):
    assert client.get("/healthz").json() == {"status": "ok"}


def test_index_is_served_for_get_and_head(client):
    assert "Celebration" in client.get("/").text
    assert client.head("/").status_code == 200


def test_plan_is_complete_and_never_calls_the_model():
    fake = FakeGenerator()
    with TestClient(create_app(Settings(), fake)) as c:
        body = c.post("/api/plan", json=make_payload()).json()
    assert {
        "budget",
        "timeline",
        "vendors",
        "warnings",
        "decisions",
        "ideas",
        "summary",
    } <= body.keys()
    assert not fake.calls


def test_ideas_endpoint_uses_the_model(client):
    body = client.post("/api/ideas", json=make_payload()).json()
    assert body["ai_generated"] is True and body["ideas"][0]["title"] == "Lantern walk"
    assert body["mode"] == "full"


def test_ideas_fall_back_without_a_model():
    with TestClient(create_app(Settings())) as c:  # no key configured -> null generator
        body = c.post("/api/ideas", json=make_payload()).json()
    assert body["ai_generated"] is False and body["ideas"] and "not available" in body["notice"]


@pytest.mark.parametrize("path", ["/api/plan", "/api/ideas"])
def test_validation_errors_do_not_echo_input(client, path):
    response = client.post(path, json=make_payload(guest_count=0, location="x" * 90))
    assert response.status_code == 422
    assert {"guest_count", "location"} <= {e["field"] for e in response.json()["errors"]}
    assert "xxxxxxxx" not in response.text


def test_security_headers_present(client):
    response = client.post("/api/plan", json=make_payload())
    headers = response.headers
    assert "default-src 'self'" in headers["content-security-policy"]
    assert "script-src 'self'" in headers["content-security-policy"]
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert "max-age" in headers["strict-transport-security"]
    assert headers["cache-control"] == "no-store"


def test_oversized_body_rejected(client):
    response = client.post("/api/plan", json=make_payload(), headers={"content-length": "999999"})
    assert response.status_code == 413


def test_rate_limit_returns_429_with_retry_after():
    app = create_app(Settings(rate_limit_requests=2, rate_limit_window_s=60), FakeGenerator())
    with TestClient(app) as c:
        codes = [c.post("/api/plan", json=make_payload()).status_code for _ in range(3)]
        last = c.post("/api/plan", json=make_payload())
    assert codes == [200, 200, 429] and int(last.headers["retry-after"]) > 0


def test_spoofed_forwarded_header_cannot_dodge_the_limit():
    app = create_app(Settings(rate_limit_requests=1), FakeGenerator())
    with TestClient(app) as c:
        first = c.post("/api/plan", json=make_payload(), headers={"x-forwarded-for": "1.1.1.1"})
        second = c.post("/api/plan", json=make_payload(), headers={"x-forwarded-for": "2.2.2.2"})
    assert (first.status_code, second.status_code) == (200, 429)


def test_trusted_proxy_separates_real_clients():
    app = create_app(Settings(rate_limit_requests=1, trusted_proxy_hops=1), FakeGenerator())
    with TestClient(app) as c:
        a = c.post("/api/plan", json=make_payload(), headers={"x-forwarded-for": "1.1.1.1"})
        b = c.post("/api/plan", json=make_payload(), headers={"x-forwarded-for": "2.2.2.2"})
    assert (a.status_code, b.status_code) == (200, 200)


def test_docs_endpoints_are_disabled(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_large_json_responses_are_compressed(client):
    response = client.post("/api/plan", json=make_payload(), headers={"accept-encoding": "gzip"})
    assert response.headers.get("content-encoding") == "gzip"
