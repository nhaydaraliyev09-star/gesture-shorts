"""Local WebSocket bridge server for browser extension direct video control (Phase 4).

Operates strictly on 127.0.0.1 with per-session token authentication.
Implemented using Python standard library (no heavy third-party dependencies).
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import socket
import struct
import threading
from collections.abc import Callable
from typing import Any

WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"


class BridgeServer:
    """Minimal, secure, localhost-only WebSocket server for extension communication."""

    def __init__(
        self,
        port: int = 8765,
        token: str | None = None,
        on_status: Callable[[dict[str, Any]], None] | None = None,
        on_connection_change: Callable[[bool], None] | None = None,
    ) -> None:
        self.host = "127.0.0.1"
        self.port = port
        self.token = token or secrets.token_urlsafe(16)
        self.on_status = on_status
        self.on_connection_change = on_connection_change

        self._server_sock: socket.socket | None = None
        self._client_sock: socket.socket | None = None
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self.is_client_authenticated: bool = False

    def start(self) -> None:
        self._stop_event.clear()
        self._server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_sock.bind((self.host, self.port))
        self._server_sock.listen(1)
        self._server_sock.settimeout(0.5)

        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        with self._lock:
            if self._client_sock:
                try:
                    self._client_sock.close()
                except OSError:
                    pass
                self._client_sock = None
                self.is_client_authenticated = False
            if self._server_sock:
                try:
                    self._server_sock.close()
                except OSError:
                    pass
                self._server_sock = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)

    @property
    def is_connected(self) -> bool:
        with self._lock:
            return self._client_sock is not None and self.is_client_authenticated

    def send_action(self, action: str) -> bool:
        """Send action command (next, previous, toggle_play, mute) to connected extension."""
        if not self.is_connected:
            return False
        msg = json.dumps({"type": "action", "action": action})
        return self._send_ws_text(msg)

    def _run_server(self) -> None:
        while not self._stop_event.is_set():
            if not self._server_sock:
                break
            try:
                client, addr = self._server_sock.accept()
            except TimeoutError:
                continue
            except OSError:
                break

            # Security: strictly verify IP is loopback
            if addr[0] not in ("127.0.0.1", "localhost"):
                client.close()
                continue

            self._handle_client_handshake(client)

    def _handle_client_handshake(self, client: socket.socket) -> None:
        client.settimeout(3.0)
        try:
            req_data = client.recv(4096).decode("utf-8", errors="ignore")
            lines = req_data.split("\r\n")
            if not lines:
                client.close()
                return

            headers: dict[str, str] = {}
            for line in lines[1:]:
                if ": " in line:
                    k, v = line.split(": ", 1)
                    headers[k.lower()] = v.strip()

            # Security: Origin validation (reject non-localhost and non-chrome-extension)
            origin = headers.get("origin", "").lower()
            if origin and not (
                origin.startswith("chrome-extension://")
                or origin.startswith("moz-extension://")
                or "localhost" in origin
                or "127.0.0.1" in origin
            ):
                client.sendall(b"HTTP/1.1 403 Forbidden\r\n\r\n")
                client.close()
                return

            ws_key = headers.get("sec-websocket-key")
            if not ws_key:
                client.sendall(b"HTTP/1.1 400 Bad Request\r\n\r\n")
                client.close()
                return

            accept_val = base64.b64encode(
                hashlib.sha1((ws_key + WS_GUID).encode("utf-8")).digest()
            ).decode("utf-8")

            handshake_resp = (
                "HTTP/1.1 101 Switching Protocols\r\n"
                "Upgrade: websocket\r\n"
                "Connection: Upgrade\r\n"
                f"Sec-WebSocket-Accept: {accept_val}\r\n\r\n"
            )
            client.sendall(handshake_resp.encode("utf-8"))

            with self._lock:
                if self._client_sock:
                    try:
                        self._client_sock.close()
                    except OSError:
                        pass
                self._client_sock = client
                self.is_client_authenticated = False

            # Spawn reader thread for this client
            threading.Thread(target=self._client_loop, args=(client,), daemon=True).start()
        except (OSError, UnicodeDecodeError):
            try:
                client.close()
            except OSError:
                pass

    def _client_loop(self, client: socket.socket) -> None:
        client.settimeout(0.5)
        while not self._stop_event.is_set():
            try:
                # Read frame header
                header = client.recv(2)
                if not header or len(header) < 2:
                    break
                b1, b2 = header[0], header[1]
                opcode = b1 & 0x0F
                masked = (b2 & 0x80) != 0
                payload_len = b2 & 0x7F

                if opcode == 0x08:  # Close frame
                    break

                if payload_len == 126:
                    ext = client.recv(2)
                    payload_len = struct.unpack("!H", ext)[0]
                elif payload_len == 127:
                    ext = client.recv(8)
                    payload_len = struct.unpack("!Q", ext)[0]

                masks = client.recv(4) if masked else b""
                data = bytearray()
                while len(data) < payload_len:
                    chunk = client.recv(min(4096, payload_len - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)

                if masked:
                    for i in range(len(data)):
                        data[i] ^= masks[i % 4]

                if opcode == 0x01:  # Text frame
                    text = data.decode("utf-8", errors="ignore")
                    self._process_client_message(text)
            except TimeoutError:
                continue
            except OSError:
                break

        with self._lock:
            if self._client_sock == client:
                self._client_sock = None
                self.is_client_authenticated = False
                if cb := self.on_connection_change:
                    cb(False)
        try:
            client.close()
        except OSError:
            pass

    def _process_client_message(self, text: str) -> None:
        try:
            msg = json.loads(text)
        except json.JSONDecodeError:
            return

        m_type = msg.get("type")
        if m_type == "auth":
            token_sent = msg.get("token")
            if token_sent == self.token:
                with self._lock:
                    self.is_client_authenticated = True
                self._send_ws_text(json.dumps({"type": "auth_ok"}))
                if cb := self.on_connection_change:
                    cb(True)
            else:
                self._send_ws_text(json.dumps({"type": "auth_error", "message": "Invalid token"}))
                with self._lock:
                    if self._client_sock:
                        self._client_sock.close()
                        self._client_sock = None
                        self.is_client_authenticated = False
        elif m_type == "status" and self.is_client_authenticated:
            if on_st := self.on_status:
                on_st(msg)

    def _send_ws_text(self, text: str) -> bool:
        with self._lock:
            if not self._client_sock:
                return False
            sock = self._client_sock

        payload = text.encode("utf-8")
        length = len(payload)
        header = bytearray([0x81])  # FIN + Text frame
        if length <= 125:
            header.append(length)
        elif length <= 65535:
            header.append(126)
            header.extend(struct.pack("!H", length))
        else:
            header.append(127)
            header.extend(struct.pack("!Q", length))

        try:
            sock.sendall(header + payload)
            return True
        except OSError:
            return False
