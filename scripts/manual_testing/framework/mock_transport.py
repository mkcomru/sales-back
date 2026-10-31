"""Mock transport server — black-hole that accepts all deliveries.

Starts a lightweight HTTP server that mimics a real transport module.
Accepts ``POST /transport/delivery`` and returns 200.  All received
payloads are recorded so tests can assert on outbound messages.

Usage::

    from framework.mock_transport import MockTransport

    transport = MockTransport()       # default port 9099
    await transport.start()
    # ... run tests with a custom connector ...
    print(transport.deliveries)       # inspect captured payloads
    await transport.stop()

The backend must be started with ``TRANSPORT__CUSTOM__URL=http://localhost:9099``
(already wired in the ``just dev`` recipe).
"""

from __future__ import annotations

import asyncio
from typing import Any

from aiohttp import web

from framework.output import console

MOCK_TRANSPORT_PORT = 9099


class MockTransport:
    """Async HTTP server that swallows outbound deliveries.

    Acts as a stand-in for telegram-module / wappi-module so that
    ``custom`` connectors have a working transport endpoint.
    """

    def __init__(self, port: int = MOCK_TRANSPORT_PORT) -> None:
        self.port = port
        self.deliveries: list[dict[str, Any]] = []
        self._runner: web.AppRunner | None = None

    @property
    def url(self) -> str:
        return f"http://localhost:{self.port}"

    async def start(self) -> None:
        app = web.Application()
        app.router.add_post("/transport/delivery", self._handle_delivery)
        app.router.add_get("/health", self._handle_health)
        app.router.add_route("*", "/{path:.*}", self._handle_catchall)

        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        console.print(f"[dim]   Mock transport listening on {self.url}[/dim]")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    async def _handle_delivery(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
        except Exception:
            payload = {"_raw": await request.text()}

        self.deliveries.append(payload)
        return web.json_response({"status": "accepted"})

    async def _handle_health(self, _request: web.Request) -> web.Response:
        return web.json_response({"status": "ok"})

    async def _handle_catchall(self, request: web.Request) -> web.Response:
        """Accept any request the backend sends (sync commands, etc.)."""
        return web.json_response({"status": "accepted"})

    def find_deliveries(
        self,
        *,
        conversation_id: str | None = None,
        connector_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Filter captured deliveries by field values."""
        results = self.deliveries
        if conversation_id:
            results = [d for d in results if d.get("conversation_id") == conversation_id]
        if connector_id:
            results = [d for d in results if d.get("connector_id") == connector_id]
        return results
