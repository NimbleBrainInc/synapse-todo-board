"""Write notices over SSE or stateful JSON with a standing GET stream."""

import asyncio
import socket
import threading
import time

import fastmcp
import pytest
import uvicorn
from fastmcp.server.auth.providers.debug import DebugTokenVerifier

from .conftest import _run
from .test_notifications import LIST_CHANGED, _calls, _toy_server


@pytest.mark.parametrize(
    ("settings_json_response", "json_response_override", "stateless_http", "authenticated"),
    [
        (False, None, False, False),
        (False, None, True, False),
        (True, None, False, False),
        (False, True, False, False),
        (True, False, True, False),
        (False, True, False, True),
    ],
    ids=[
        "stateful-sse",
        "stateless-sse",
        "stateful-json",
        "json-overrides-sse-setting",
        "stateless-sse-overrides-json-setting",
        "authenticated-json-overrides-sse-setting",
    ],
)
def test_write_notifications_reach_http_clients(
    monkeypatch, settings_json_response, json_response_override, stateless_http, authenticated
):
    monkeypatch.setattr(fastmcp.settings, "json_response", settings_json_response)
    monkeypatch.setattr(fastmcp.settings, "stateless_http", stateless_http)
    json_response = (
        settings_json_response if json_response_override is None else json_response_override
    )
    server_auth = DebugTokenVerifier() if authenticated else None
    app = _toy_server(auth=server_auth).http_app(json_response=json_response_override)
    responses = []

    async def observe_responses(scope, receive, send):
        async def record(message):
            if scope["type"] == "http" and message["type"] == "http.response.start":
                content_type = dict(message.get("headers", [])).get(b"content-type", b"")
                responses.append((scope["method"], message["status"], content_type))
            await send(message)

        await app(scope, receive, record)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        server = uvicorn.Server(
            uvicorn.Config(observe_responses, loop="asyncio", ws="none", log_level="critical")
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [listener]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not server.started:
                assert thread.is_alive(), "HTTP server stopped before startup"
                assert time.monotonic() < deadline, "HTTP server did not start"
                time.sleep(0.01)

            async def wait_for_get():
                if json_response:
                    deadline = time.monotonic() + 5
                    while not any(
                        method == "GET" and status == 200 for method, status, _ in responses
                    ):
                        assert time.monotonic() < deadline, "Standing GET stream did not connect"
                        await asyncio.sleep(0.01)
                    assert any(
                        method == "GET"
                        and status == 200
                        and content.startswith(b"text/event-stream")
                        for method, status, content in responses
                    ), "Stateful JSON notifications need the standing GET stream"

            seen = _run(
                _calls(
                    f"http://127.0.0.1:{port}/mcp",
                    [("write", {}), ("read", {}), ("write", {}), ("fail", {})],
                    raises=("fail",),
                    auth="todo-notification-test" if authenticated else None,
                    before_calls=wait_for_get,
                )
            )
            assert seen == [LIST_CHANGED, LIST_CHANGED]
            expected_type = b"application/json" if json_response else b"text/event-stream"
            posts = [
                content
                for method, status, content in responses
                if method == "POST" and status == 200
            ]
            assert posts and all(content.startswith(expected_type) for content in posts)
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            assert not thread.is_alive(), "HTTP server did not stop"
