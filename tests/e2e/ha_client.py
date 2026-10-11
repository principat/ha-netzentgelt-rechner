"""Minimal synchronous client for REST and WebSocket of a running Home Assistant."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any

from websockets.sync.client import connect


class HA:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

    # ---------------------------------------------------------------- REST

    def request(self, method: str, path: str, body: Any = None, timeout: float = 30) -> Any:
        data = None if body is None else json.dumps(body).encode()
        req = urllib.request.Request(
            self.url + path,
            data=data,
            method=method,
            headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw

    def state(self, entity_id: str) -> dict[str, Any]:
        result: dict[str, Any] = self.request("GET", f"/api/states/{entity_id}")
        return result

    def call(self, domain: str, service: str, **data: Any) -> None:
        self.request("POST", f"/api/services/{domain}/{service}", data)

    def wait_until(self, check: Any, timeout: float, what: str, interval: float = 0.5) -> Any:
        deadline = time.monotonic() + timeout
        last: Exception | None = None
        while time.monotonic() < deadline:
            try:
                result = check()
                if result:
                    return result
            except (urllib.error.URLError, ConnectionError, TimeoutError, OSError) as err:
                last = err
            time.sleep(interval)
        raise AssertionError(f"timeout waiting for {what} (last error: {last})")

    # ---------------------------------------------------------------- WebSocket

    def ws_commands(self, commands: list[dict[str, Any]]) -> list[Any]:
        """Authenticate, send the commands one after another and return their results."""
        ws_url = self.url.replace("http", "ws", 1) + "/api/websocket"
        results: list[Any] = []
        with connect(ws_url, max_size=None, open_timeout=30) as ws:
            json.loads(ws.recv())  # auth_required
            ws.send(json.dumps({"type": "auth", "access_token": self.token}))
            assert json.loads(ws.recv())["type"] == "auth_ok"
            for i, command in enumerate(commands, start=1):
                ws.send(json.dumps({**command, "id": i}))
                while True:
                    msg = json.loads(ws.recv())
                    if msg.get("id") == i and msg["type"] == "result":
                        assert msg["success"], msg
                        results.append(msg["result"])
                        break
        return results

    def entity_ids(self, domain: str) -> dict[str, str]:
        """translation_key -> entity_id for all entities of the integration."""
        (entries,) = self.ws_commands([{"type": "config/entity_registry/list"}])
        return {e["translation_key"]: e["entity_id"] for e in entries if e["platform"] == domain}
