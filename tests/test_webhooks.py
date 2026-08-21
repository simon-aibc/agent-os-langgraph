import hashlib
import hmac
import json
import socket
from unittest.mock import MagicMock

from agent_os.events import build_lifecycle_payload
from agent_os.webhooks import (
    PinnedIPHTTPSConnection,
    WebhookEventSink,
    is_safe_webhook_url,
)


def _public_dns(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 443))]


def _private_dns(*_args, **_kwargs):
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 443))]


def test_is_safe_webhook_url_validation(monkeypatch):
    assert not is_safe_webhook_url("ftp://example.com/webhook")[0]
    assert not is_safe_webhook_url("https://user:password@example.com/webhook")[0]
    assert not is_safe_webhook_url("http://127.0.0.1:8000/webhook")[0]
    assert not is_safe_webhook_url("http://localhost:8000/webhook")[0]
    assert not is_safe_webhook_url("http://10.0.0.1/webhook")[0]
    assert is_safe_webhook_url(
        "http://127.0.0.1:8000/webhook", allowed_internal_hosts=["127.0.0.1"]
    )[0]
    monkeypatch.setattr("agent_os.webhooks.socket.getaddrinfo", _public_dns)
    assert is_safe_webhook_url("https://example.com/webhook")[0]


def test_webhook_payload_strict_privacy_invariants():
    payload = build_lifecycle_payload(
        "run.created",
        run_id="run-123",
        workspace_id="ws-canonical-456",
        status="queued",
        actor_id="user:alice",
        actor_kind="human",
        actor_display="Alice",
        on_behalf_of="team-core",
        thread_id="thread-789",
    )
    assert payload["actor"]["id"] == "user:alice"
    assert payload["references"]["thread_id"] == "thread-789"
    for forbidden in ["task", "prompt", "plan", "tool", "arguments", "output", "secret", "token"]:
        assert forbidden not in str(payload)


def test_webhook_delivery_hmac_signature_and_headers(monkeypatch):
    received_requests = []

    class FakeResponse:
        status = 200

        def read(self):
            return b'{"status":"ok"}'

        def getheader(self, _name, _default=None):
            return None

    class FakeHTTPSConnection:
        def __init__(self, pinned_ip, original_host, port, timeout, context=None):
            self.pinned_ip = pinned_ip
            self.original_host = original_host
            self.port = port
            self.timeout = timeout

        def request(self, method, path, body=None, headers=None):
            received_requests.append({
                "method": method,
                "path": path,
                "body": body,
                "headers": headers or {},
                "pinned_ip": self.pinned_ip,
                "original_host": self.original_host,
            })

        def getresponse(self):
            return FakeResponse()

        def close(self):
            pass

    monkeypatch.setattr("agent_os.webhooks.socket.getaddrinfo", _public_dns)
    monkeypatch.setattr("agent_os.webhooks.PinnedIPHTTPSConnection", FakeHTTPSConnection)

    secret = "super-secret-webhook-key"
    sink = WebhookEventSink(url="https://example.com/webhook", secret=secret)
    event = build_lifecycle_payload(
        "run.completed", run_id="run-test-1", workspace_id="ws-test", status="completed"
    )

    assert sink._send_with_retry(event)
    assert len(received_requests) == 1

    req = received_requests[0]
    headers = {key.lower(): value for key, value in req["headers"].items()}
    body = req["body"]
    timestamp = headers["x-agentos-timestamp"]
    expected = "sha256=" + hmac.new(
        secret.encode(), f"{timestamp}.".encode() + body, hashlib.sha256
    ).hexdigest()

    assert headers["x-agentos-signature"] == expected
    assert json.loads(body)["run_id"] == "run-test-1"
    assert req["pinned_ip"] == "93.184.216.34"
    assert req["original_host"] == "example.com"


def test_webhook_dns_rebinding_simulation_blocks_connection(monkeypatch):
    """Simulate DNS returning private IP at connection time: connection must be blocked."""
    dns_calls = 0

    def rebinding_dns(host, port, *args, **kwargs):
        nonlocal dns_calls
        dns_calls += 1
        # At connection time, DNS returns private IP (127.0.0.1)
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", port))]

    monkeypatch.setattr("agent_os.webhooks.socket.getaddrinfo", rebinding_dns)
    sink = WebhookEventSink(url="https://rebind-attack.com/webhook", secret="secret")
    event = build_lifecycle_payload("run.created", run_id="run-1", workspace_id="ws", status="queued")

    # Delivery must be blocked and fail soft
    assert not sink._send_with_retry(event)


def test_webhook_https_preserves_sni_and_original_host(monkeypatch):
    """Verify PinnedIPHTTPSConnection configures SNI for original hostname."""
    mock_context = MagicMock()
    mock_sock = MagicMock()
    raw_sock = object()
    mock_context.wrap_socket.return_value = mock_sock

    conn = PinnedIPHTTPSConnection(
        pinned_ip="93.184.216.34",
        original_host="my-service.corp.com",
        port=443,
        timeout=5.0,
        context=mock_context,
    )
    connected_to = []

    def fake_connect(connection):
        connected_to.append((connection.host, connection.port))
        connection.sock = raw_sock

    monkeypatch.setattr("agent_os.webhooks.http.client.HTTPConnection.connect", fake_connect)
    conn.connect()

    assert conn.original_host == "my-service.corp.com"
    assert conn.host == "93.184.216.34"
    assert connected_to == [("93.184.216.34", 443)]
    mock_context.wrap_socket.assert_called_once_with(
        raw_sock, server_hostname="my-service.corp.com"
    )


def test_webhook_redirect_to_loopback_is_rejected(monkeypatch):
    """Verify a 302 redirect to a loopback address is rejected by anti-SSRF."""
    class FakeRedirectResponse:
        status = 302

        def read(self):
            return b""

        def getheader(self, name, default=None):
            if name.lower() == "location":
                return "http://127.0.0.1:8080/admin"
            return default

    class FakeHTTPConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, method, path, body=None, headers=None):
            pass

        def getresponse(self):
            return FakeRedirectResponse()

        def close(self):
            pass

    monkeypatch.setattr("agent_os.webhooks.socket.getaddrinfo", _public_dns)
    monkeypatch.setattr("agent_os.webhooks.PinnedIPHTTPSConnection", FakeHTTPConnection)

    sink = WebhookEventSink(url="https://example.com/initial", secret="secret")
    event = build_lifecycle_payload("run.created", run_id="run-1", workspace_id="ws", status="queued")

    assert not sink._send_with_retry(event)


def test_webhook_bounded_retry_and_fail_soft(monkeypatch):
    attempts = 0

    class FailingConnection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            nonlocal attempts
            attempts += 1
            raise OSError("Connection refused")

        def getresponse(self):
            raise OSError("Connection refused")

        def close(self):
            pass

    monkeypatch.setattr("agent_os.webhooks.socket.getaddrinfo", _public_dns)
    monkeypatch.setattr("agent_os.webhooks.PinnedIPHTTPSConnection", FailingConnection)
    monkeypatch.setattr("agent_os.webhooks.time.sleep", lambda _seconds: None)

    sink = WebhookEventSink(url="https://example.com/fail", secret="test-secret", max_retries=3)
    event = build_lifecycle_payload("run.failed", run_id="run-fail-1", workspace_id="ws-test", status="failed")

    assert not sink._send_with_retry(event)
    assert attempts == 3
