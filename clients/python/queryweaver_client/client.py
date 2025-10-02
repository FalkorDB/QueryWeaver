"""QueryWeaver HTTP API client.

Simple wrapper around the REST API exposed by a running QueryWeaver server.
Supports API token authentication (Bearer) and session cookie usage.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

import aiohttp


class APIError(Exception):
    """Raised for non-2xx responses from the server."""


MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"


class QueryWeaverClient:
    """Minimal QueryWeaver client.

    Usage:
      async with QueryWeaverClient("http://localhost:5000", api_token="...") as client:
        await client.list_schemas()
        result = await client.connect_database("postgresql://user:pass@host/db")

    Authentication:
      - api_token: sent as Bearer token in Authorization header
      - session cookie: pass a `aiohttp.ClientSession()` with cookies set
      - If both session and api_token are provided, the Authorization header
        will be automatically added to the provided session's headers

    Args:
        base_url: The base URL of the QueryWeaver server
        api_token: Optional API token for Bearer authentication
        session: Optional aiohttp ClientSession. If provided with api_token,
                 the Authorization header will be added to this session
        timeout: Request timeout in seconds (default: 30)
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

        # Track whether we own the session (created by us) so we only close it when
        # appropriate. If a session is provided and api_token is set, avoid mutating
        # the session.headers (a CIMultiDictProxy) which can raise AttributeError.
        # Instead, if the session exposes a writable `_default_headers` attribute,
        # set the Authorization header there; otherwise we will merge
        # `self._default_headers` into each request.
        self._owns_session = self._session is None

        if self._session and api_token:
            # Prefer updating the session.headers when it's a mutable mapping (helps tests
            # that supply a simple DummySession). If session.headers is a read-only proxy
            # (aiohttp's CIMultiDictProxy), this will raise; in that case fall back to
            # setting _default_headers if available, otherwise rely on per-request headers.
            try:
                # some session implementations expose a writable headers dict
                self._session.headers.update({"Authorization": f"Bearer {api_token}"})
            except Exception:
                default_headers = getattr(self._session, "_default_headers", None)
                if default_headers is not None:
                    default_headers["Authorization"] = f"Bearer {api_token}"

    async def __aenter__(self):
        if self._session is None:
            self._session = aiohttp.ClientSession(headers=self._default_headers)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._session and not self._session.closed:
            await self._session.close()

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    async def _raise_for_status(self, resp: aiohttp.ClientResponse) -> None:
        if not 200 <= resp.status < 300:
            # try to parse json error
            try:
                payload = await resp.json()
            except (json.JSONDecodeError, aiohttp.ContentTypeError, ValueError):
                payload = await resp.text()
            raise APIError(f"HTTP {resp.status}: {payload}")

    async def _parse_streaming_response(self, resp: aiohttp.ClientResponse) -> Dict[str, Any]:
        """Parse streaming response by buffering and splitting on MESSAGE_DELIMITER.

        Returns the last event from the stream, which typically contains the final result.
        """
        buffer = ""
        events = []

        async for chunk in resp.content.iter_any():
            chunk_str = chunk.decode('utf-8')
            buffer += chunk_str

            # Split by the delimiter and process complete messages
            parts = buffer.split(MESSAGE_DELIMITER)

            # Keep the last part in the buffer (it may be incomplete)
            buffer = parts[-1]

            # Process all complete messages
            for part in parts[:-1]:
                part = part.strip()
                if not part:
                    continue
                try:
                    events.append(json.loads(part))
                except json.JSONDecodeError:
                    # If we can't parse it, store it as raw
                    events.append({"raw": part})

        # Process any remaining data in the buffer
        if buffer.strip():
            try:
                events.append(json.loads(buffer.strip()))
            except json.JSONDecodeError:
                events.append({"raw": buffer.strip()})

        # Return the last event which typically contains the final result
        return events[-1] if events else {}

    async def list_schemas(self) -> List[str]:
        """GET /graphs - list available user schemas/databases.

        Returns:
            List[str]: A list of database/schema names.
        """
        async with self._session.get(self._url("/graphs"), timeout=self.timeout) as resp:
            await self._raise_for_status(resp)
            return await resp.json()

    async def get_schema(self, graph_id: str) -> Dict[str, Any]:
        """GET /graphs/{graph_id}/data - return schema nodes/edges."""
        async with self._session.get(self._url(f"/graphs/{graph_id}/data"),
                                     timeout=self.timeout) as resp:
            await self._raise_for_status(resp)
            return await resp.json()

    async def delete_schema(self, graph_id: str) -> Dict[str, Any]:
        """DELETE /graphs/{graph_id} - delete a schema."""
        async with self._session.delete(self._url(f"/graphs/{graph_id}"),
                                        timeout=self.timeout) as resp:
            await self._raise_for_status(resp)
            return await resp.json()

    async def refresh_schema(self, graph_id: str) -> Dict[str, Any]:
        """POST /graphs/{graph_id}/refresh - refresh schema."""
        async with self._session.post(self._url(f"/graphs/{graph_id}/refresh"),
                                      timeout=self.timeout) as resp:
            await self._raise_for_status(resp)
            return await resp.json()

    async def connect_database(self, db_url: str) -> Dict[str, Any]:
        """POST /database - connect to a database and return final result."""
        payload = {"url": db_url}
        async with self._session.post(self._url("/database"), json=payload,
                                      timeout=self.timeout) as resp:
            await self._raise_for_status(resp)
            return await self._parse_streaming_response(resp)

    async def query(self, graph_id: str, chat_data: Dict[str, Any],
                    auto_confirm: bool = False) -> Dict[str, Any]:
        """POST /graphs/{graph_id} - run a natural language query and return final result.

        Args:
            graph_id: The database/schema ID to query
            chat_data: The chat data containing the query messages
            auto_confirm: If True, automatically confirm destructive operations.
                         If False (default), returns confirmation request for user approval.

        Returns:
            Dict containing the query result or confirmation request
        """
        async with self._session.post(self._url(f"/graphs/{graph_id}"),
                                      json=chat_data, timeout=self.timeout) as resp:
            await self._raise_for_status(resp)
            result = await self._parse_streaming_response(resp)

        # If auto_confirm is enabled and result requires confirmation, automatically
        # confirm the destructive operation
        is_destructive = (isinstance(result, dict) and
                         result.get("type") == "destructive_confirmation")
        if auto_confirm and is_destructive:
            confirm_data = {
                "sql_query": result.get("sql_query"),
                "confirmation": "YES",
                "chat": chat_data.get("messages", [])
            }
            return await self.confirm(graph_id, confirm_data)

        return result

    async def confirm(self, graph_id: str, confirm_data: Dict[str, Any]) -> Dict[str, Any]:
        """POST /graphs/{graph_id}/confirm - confirm destructive operation and return result."""
        async with self._session.post(self._url(f"/graphs/{graph_id}/confirm"),
                                      json=confirm_data, timeout=self.timeout) as resp:
            await self._raise_for_status(resp)
            return await self._parse_streaming_response(resp)
