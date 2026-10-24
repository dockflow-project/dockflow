"""Remote requests must not disclose credentials or replay writes on redirects."""

import contextlib
import io
import json
import threading
from email.message import Message
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import HTTPSHandler
from urllib.response import addinfourl

import pytest
from dockflow_database.errors import DockflowError
from dockflow_pipelines.client import Client


@pytest.fixture(autouse=True)
def local_transports(monkeypatch):
    monkeypatch.setenv("NO_PROXY", "*")


@contextlib.contextmanager
def http_server(respond):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            # Drain POST data before closing; unread bytes can reset Windows TCP.
            self.rfile.read(int(self.headers.get("Content-Length", "0")))
            respond(self)

        do_POST = do_GET

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(
        target=lambda: server.serve_forever(poll_interval=0.01), daemon=True
    )
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("same_origin", [False, True])
def test_redirects_do_not_forward_credentials_or_replay_requests(
    tmp_path, status, method, same_origin
):
    token = tmp_path / "token"
    token.write_text("synthetic-redirect-test-token")
    received = []

    def destination(request):
        received.append((request.path, request.headers.get("Authorization")))
        request.send_response(200)
        request.end_headers()
        request.wfile.write(b"{}")

    with http_server(destination) as other_origin:

        def origin(request):
            if request.path == "/target":
                destination(request)
                return
            request.send_response(status)
            request.send_header(
                "Location", "/target" if same_origin else other_origin + "/target"
            )
            request.end_headers()

        with http_server(origin) as endpoint:
            client = Client(endpoint, {"token_file": token})
            with pytest.raises(DockflowError, match="redirect") as error:
                client.request(
                    method,
                    "/dockflow/v1/experiments",
                    {"display_name": "test"} if method == "POST" else None,
                )
            assert error.value.code == "UNAVAILABLE"
            assert token.read_text() not in str(error.value)
    assert received == []


def test_direct_requests_still_send_configured_authentication(tmp_path):
    token = tmp_path / "token"
    token.write_text("synthetic-direct-test-token")
    received = []

    def origin(request):
        received.append(request.headers.get("Authorization"))
        request.send_response(200)
        request.end_headers()
        request.wfile.write(json.dumps({"ok": True}).encode())

    with http_server(origin) as endpoint:
        assert Client(endpoint, {"token_file": token}).request("GET", "/api") == {
            "ok": True
        }
    assert received == ["Bearer synthetic-direct-test-token"]


def test_https_redirect_cannot_downgrade_to_http(tmp_path, monkeypatch):
    token = tmp_path / "token"
    token.write_text("synthetic-https-test-token")
    received = []

    def destination(request):
        received.append(request.headers.get("Authorization"))
        request.send_response(200)
        request.end_headers()
        request.wfile.write(b"{}")

    with http_server(destination) as endpoint:
        # Stub only TLS transport; exercise the actual opener and redirect policy.
        def https_response(handler, request):
            assert request.full_url.startswith("https://")
            headers = Message()
            headers["Location"] = endpoint + "/target"
            response = addinfourl(io.BytesIO(b""), headers, request.full_url, code=302)
            response.msg = "Found"
            return response

        monkeypatch.setattr(HTTPSHandler, "https_open", https_response)
        with pytest.raises(DockflowError, match="redirect"):
            Client("https://service.example", {"token_file": token}).request(
                "GET", "/api"
            )
    assert received == []
