"""QueryWeaver HTTP API client.

Simple wrapper around the REST API exposed by a running QueryWeaver server.
Supports API token authentication (Bearer) and session cookie usage.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import aiohttp


class APIError(Exception):
    """Raised for non-2xx responses from the server."""


class QueryWeaverClient:
    """Minimal QueryWeaver client.

    Usage:
      async with QueryWeaverClient("http://localhost:5000", api_token="...") as client:
        await client.list_schemas()
        result = await client.connect_database("postgresql://user:pass@host/db")

    Authentication:
      - api_token: sent as Bearer token in Authorization header
      - session cookie: pass a `aiohttp.ClientSession()` with cookies set
    """

    def __init__(
        self,
        base_url: str,
        api_token: Optional[str] = None,
        session: Optional[aiohttp.ClientSession] = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self._session = session
        self.timeout = aiohttp.ClientTimeout(total=timeout)

        # default headers
        self._default_headers = {"Accept": "application/json"}
        if api_token:
            self._default_headers["Authorization"] = f"Bearer {api_token}"

    async def __aenter__(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=self._default_headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _raise_for_status(self, resp: aiohttp.ClientResponse) -> None:
        if not resp.ok:
            # try to parse json error
            try:
                payload = resp.json()
            except Exception:
                payload = resp.text
            raise APIError(f"HTTP {resp.status}: {payload}")

    async def list_schemas(self) -> Dict[str, Any]:
        """GET /graphs - list available user schemas/databases."""
        async with self._session.get(self._url("/graphs"), timeout=self.timeout) as resp:
            self._raise_for_status(resp)
            return await resp.json()

    async def get_schema(self, graph_id: str) -> Dict[str, Any]:
        """GET /graphs/{graph_id}/data - return schema nodes/edges."""
        async with self._session.get(self._url(f"/graphs/{graph_id}/data"), timeout=self.timeout) as resp:
            self._raise_for_status(resp)
            return await resp.json()

    async def delete_schema(self, graph_id: str) -> Dict[str, Any]:
        """DELETE /graphs/{graph_id} - delete a schema."""
        async with self._session.delete(self._url(f"/graphs/{graph_id}"), timeout=self.timeout) as resp:
            self._raise_for_status(resp)
            return await resp.json()

    async def refresh_schema(self, graph_id: str) -> Dict[str, Any]:
        """POST /graphs/{graph_id}/refresh - refresh schema."""
        async with self._session.post(self._url(f"/graphs/{graph_id}/refresh"), timeout=self.timeout) as resp:
            self._raise_for_status(resp)
            return await resp.json()

    async def connect_database(self, db_url: str) -> Dict[str, Any]:
        """POST /database - connect to a database and return final result."""
        payload = {"url": db_url}
        async with self._session.post(self._url("/database"), json=payload, timeout=self.timeout) as resp:
            self._raise_for_status(resp)

            # Consume the streaming response and return the final result
            events = []
            async for chunk in resp.content.iter_any():
                chunk_str = chunk.decode('utf-8')
                if not chunk_str.strip():
                    continue
                try:
                    events.append(json.loads(chunk_str))
                except Exception:
                    # fallback: try to split by '|||' or newline
                    parts = chunk_str.split("|||")
                    for part in parts:
                        part = part.strip()
                        if not part:
                            continue
                        try:
                            events.append(json.loads(part))
                        except Exception:
                            events.append({"raw": part})

            # Return the last event which typically contains the final status/result
            return events[-1] if events else {}

    async def query(self, graph_id: str, chat_data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /graphs/{graph_id} - run a natural language query and return final result."""
        async with self._session.post(self._url(f"/graphs/{graph_id}"), json=chat_data, timeout=self.timeout) as resp:
            self._raise_for_status(resp)

            # Consume the streaming response and return the final result
            events = []
            async for chunk in resp.content.iter_any():
                chunk_str = chunk.decode('utf-8')
                if not chunk_str.strip():
                    continue
                try:
                    events.append(json.loads(chunk_str))
                except Exception:
                    # server may send partial JSON, try to yield raw
                    events.append({"raw": chunk_str})

            # Return the last event which typically contains the final SQL result
            return events[-1] if events else {}

    async def confirm(self, graph_id: str, confirm_data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /graphs/{graph_id}/confirm - confirm destructive operation and return result."""
        async with self._session.post(self._url(f"/graphs/{graph_id}/confirm"), json=confirm_data, timeout=self.timeout) as resp:
            self._raise_for_status(resp)

            # Consume the streaming response and return the final result
            events = []
            async for chunk in resp.content.iter_any():
                chunk_str = chunk.decode('utf-8')
                if not chunk_str.strip():
                    continue
                try:
                    events.append(json.loads(chunk_str))
                except Exception:
                    events.append({"raw": chunk_str})

            # Return the last event
            return events[-1] if events else {}
