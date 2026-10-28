"""Tests for Phase 4 WebSocket bridge server and adapter fallback."""

from __future__ import annotations

import base64
import hashlib
import json
import socket
from unittest.mock import MagicMock

from gesture_shorts.adapters import PlatformAdapter
from gesture_shorts.bridge import WS_GUID, BridgeServer


def make_ws_handshake(
    sock: socket.socket, host: str, port: int, key: str = "dGhlIHNhbXBsZSBub25jZQ=="
) -> str:
    req = (
        f"GET / HTTP/1.1\r\n"
        f"Host: {host}:{port}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n"
        f"Origin: chrome-extension://abcdefghijklmnop\r\n\r\n"
    )
    sock.sendall(req.encode("utf-8"))
    resp = sock.recv(2048).decode("utf-8")
    return resp


def send_masked_text(sock: socket.socket, text: str) -> None:
    payload = text.encode("utf-8")
    length = len(payload)
    mask = b"\x12\x34\x56\x78"

    header = bytearray([0x81, 0x80 | length])
    header.extend(mask)

    masked_data = bytearray(payload)
    for i in range(len(masked_data)):
        masked_data[i] ^= mask[i % 4]

    sock.sendall(header + masked_data)


def recv_unmasked_text(sock: socket.socket) -> str:
    header = sock.recv(2)
    length = header[1] & 0x7F
    data = sock.recv(length)
    return data.decode("utf-8")


def test_bridge_handshake_and_authentication() -> None:
    server = BridgeServer(port=0, token="secret123")
    server.start()
    # Get bound port
    port = server._server_sock.getsockname()[1]

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect(("127.0.0.1", port))
        resp = make_ws_handshake(client, "127.0.0.1", port)
        assert "101 Switching Protocols" in resp
        expected_accept = base64.b64encode(
            hashlib.sha1(("dGhlIHNhbXBsZSBub25jZQ==" + WS_GUID).encode("utf-8")).digest()
        ).decode("utf-8")
        assert expected_accept in resp

        # Send valid authentication
        send_masked_text(client, json.dumps({"type": "auth", "token": "secret123"}))
        auth_resp = recv_unmasked_text(client)
        assert json.loads(auth_resp)["type"] == "auth_ok"
        assert server.is_connected
    finally:
        client.close()
        server.stop()


def test_bridge_rejects_invalid_token() -> None:
    server = BridgeServer(port=0, token="correct_token")
    server.start()
    port = server._server_sock.getsockname()[1]

    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        client.connect(("127.0.0.1", port))
        make_ws_handshake(client, "127.0.0.1", port)

        # Send invalid token
        send_masked_text(client, json.dumps({"type": "auth", "token": "wrong_token"}))
        err_resp = recv_unmasked_text(client)
        assert json.loads(err_resp)["type"] == "auth_error"
        assert not server.is_connected
    finally:
        client.close()
        server.stop()


def test_adapter_uses_bridge_when_connected_and_falls_back() -> None:
    bridge = MagicMock(spec=BridgeServer)
    bridge.is_connected = True
    bridge.send_action.return_value = True

    notifications: list[str] = []
    adapter = PlatformAdapter("YouTube", notifications.append, bridge=bridge)
    adapter._send_key = MagicMock()

    # 1. When bridge is connected: uses bridge
    res = adapter.perform("next", require_browser_focus=True)
    assert res
    assert "Next ▲ (Bridge)" in notifications
    bridge.send_action.assert_called_with("next")
    adapter._send_key.assert_not_called()

    # 2. When bridge is disconnected: falls back to pynput
    bridge.is_connected = False
    adapter.focus_checker.is_target_focused = MagicMock(return_value=(True, None))
    adapter._send_key.return_value = True

    res2 = adapter.perform("next", require_browser_focus=True)
    assert res2
    assert "Next ▲" in notifications
    adapter._send_key.assert_called_once()
