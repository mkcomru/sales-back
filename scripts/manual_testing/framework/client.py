"""Base test client with common API methods."""

from datetime import datetime
from typing import Any

import httpx

from framework.config import config
from framework.output import console, error, success


class BaseTestClient:
    """Base client for manual testing with common API methods.

    Subclass this to add domain-specific methods for your test.

    Example:
        class TasksClient(BaseTestClient):
            async def create_task(self, order_id: int, title: str, ...) -> dict:
                return await self.post(
                    f"/companies/{self.company_id}/orders/{order_id}/tasks",
                    json={...}
                )
    """

    def __init__(self) -> None:
        self.access_token: str | None = None
        self.refresh_token: str | None = None
        self.user_id: int | None = None
        self.company_id: int | None = None
        self.company_user_id: int | None = None
        self.thread_id: str | None = None
        self.customer_id: int | None = None
        self.order_id: int | None = None

    @property
    def headers(self) -> dict[str, str]:
        """Authorization headers for authenticated requests."""
        if not self.access_token:
            return {}
        return {"Authorization": f"Bearer {self.access_token}"}

    @property
    def service_headers(self) -> dict[str, str]:
        """Headers for internal/service API calls."""
        return {"X-Service-Key": config.service_api_key}

    def _client(self, timeout: float | None = None) -> httpx.AsyncClient:
        """Create configured httpx client."""
        return httpx.AsyncClient(
            base_url=config.api_url,
            timeout=timeout or config.request_timeout,
        )

    async def get(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        use_service_auth: bool = False,
    ) -> dict[str, Any]:
        """Make authenticated GET request."""
        async with self._client() as client:
            auth_headers = self.service_headers if use_service_auth else self.headers
            response = await client.get(
                path,
                params=params,
                headers={**auth_headers, **(headers or {})},
            )
            response.raise_for_status()
            return response.json()

    async def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        use_service_auth: bool = False,
    ) -> dict[str, Any]:
        """Make authenticated POST request."""
        async with self._client() as client:
            auth_headers = self.service_headers if use_service_auth else self.headers
            response = await client.post(
                path,
                json=json,
                headers={**auth_headers, **(headers or {})},
            )
            response.raise_for_status()
            return response.json()

    async def patch(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        use_service_auth: bool = False,
    ) -> dict[str, Any]:
        """Make authenticated PATCH request."""
        async with self._client() as client:
            auth_headers = self.service_headers if use_service_auth else self.headers
            response = await client.patch(
                path,
                json=json,
                headers={**auth_headers, **(headers or {})},
            )
            response.raise_for_status()
            return response.json()

    async def put(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        *,
        headers: dict[str, str] | None = None,
        use_service_auth: bool = False,
    ) -> dict[str, Any]:
        """Make authenticated PUT request."""
        async with self._client() as client:
            auth_headers = self.service_headers if use_service_auth else self.headers
            response = await client.put(
                path,
                json=json,
                headers={**auth_headers, **(headers or {})},
            )
            response.raise_for_status()
            return response.json()

    async def delete(
        self,
        path: str,
        *,
        headers: dict[str, str] | None = None,
        use_service_auth: bool = False,
    ) -> bool:
        """Make authenticated DELETE request. Returns True on 204."""
        async with self._client() as client:
            auth_headers = self.service_headers if use_service_auth else self.headers
            response = await client.delete(
                path,
                headers={**auth_headers, **(headers or {})},
            )
            return response.status_code == 204

    async def raw_request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Make raw request without raising on error. Useful for testing error cases."""
        async with self._client() as client:
            return await client.request(
                method,
                path,
                json=json,
                params=params,
                headers={**self.headers, **(headers or {})},
            )

    # ─────────────────────────────────────────────────────────────────────────
    # Common API Methods (shared across all tests)
    # ─────────────────────────────────────────────────────────────────────────

    async def login(self, email: str | None = None, password: str | None = None) -> dict[str, Any]:
        """Login and get tokens. Uses config defaults if not provided."""
        email = email or config.superuser_email
        password = password or config.superuser_password

        async with self._client() as client:
            response = await client.post(
                "/auth/login",
                json={"email": email, "password": password},
            )
            if response.status_code == 401:
                return {"error": "Invalid credentials"}
            response.raise_for_status()
            return response.json()

    async def get_me(self) -> dict[str, Any]:
        """Get current user info."""
        return await self.get("/users/me")

    async def list_companies(self) -> list[dict[str, Any]]:
        """List companies for current user."""
        return await self.get("/companies")

    async def create_company(self, name: str, description: str = "Test company") -> dict[str, Any]:
        """Create a new company with test defaults."""
        return await self.post(
            "/companies",
            json={
                "name": name,
                "description": description,
                "rules": "Test rules",
                "tone_of_voice": "Professional",
                "assistant_name": "Test Assistant",
                "qualification_workflow": "Standard",
                "qualification_examples": "Examples",
                "collection_name": name.lower().replace(" ", "_").replace("-", "_"),
                "stages_config": [],
                "category_rules": [],
            },
        )

    async def list_company_members(self) -> list[dict[str, Any]]:
        """List company members."""
        response = await self.get(f"/companies/{self.company_id}/members")
        return response.get("items", [])

    async def get_or_create_thread(
        self,
        user_id: str | None = None,
        conversation_id: str | None = None,
    ) -> dict[str, Any]:
        """Get or create thread via internal API."""
        ts = datetime.now().timestamp()
        return await self.post(
            "/internal/chat/threads/get-or-create",
            json={
                "user_id": user_id or f"test_user_{ts}",
                "company_id": self.company_id,
                "channel_type": "test",
                "connector_id": "test_connector",
                "conversation_id": conversation_id or f"test_conv_{ts}",
            },
        )

    async def get_thread(self, thread_id: str) -> dict[str, Any]:
        """Get thread details."""
        return await self.get(f"/companies/{self.company_id}/threads/{thread_id}")

    async def get_order_by_thread(self, thread_id: str) -> dict[str, Any]:
        """Get order context for thread (internal API)."""
        return await self.get(f"/internal/orders/by-thread/{thread_id}")

    async def get_order(self, order_id: int) -> dict[str, Any]:
        """Get order by ID."""
        return await self.get(f"/companies/{self.company_id}/orders/{order_id}")

    # ─────────────────────────────────────────────────────────────────────────
    # Health Checks
    # ─────────────────────────────────────────────────────────────────────────

    async def check_backend_health(self) -> bool:
        """Check if backend is healthy."""
        try:
            async with httpx.AsyncClient(timeout=config.health_check_timeout) as client:
                response = await client.get(f"{config.base_url}/health")
                return response.status_code == 200
        except Exception:
            return False

    async def check_sales_agent_health(self) -> bool:
        """Check if sales-agent is healthy."""
        try:
            async with httpx.AsyncClient(timeout=config.health_check_timeout) as client:
                response = await client.get("http://localhost:8080/healthz")
                return response.status_code == 200
        except Exception:
            return False
