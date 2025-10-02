"""QueryWeaver HTTP API client.

Simple wrapper around the REST API exposed by a running QueryWeaver server.
Supports API token authentication (Bearer) and session cookie usage.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterator, Optional

import requests


class APIError(Exception):
    """Raised for non-2xx responses from the server."""


class QueryWeaverClient:
    """Minimal QueryWeaver client.

    Usage:
      client = QueryWeaverClient("http://localhost:5000", api_token="...")
      client.list_graphs()
      client.connect_database("postgresql://user:pass@host/db")

    Authentication:
      - api_token: sent as Bearer token in Authorization header
      - session cookie: pass a `requests.Session()` with cookies set
    """

    def __init__(
        self,
        base_url: str,
        api_token: Optional[str] = None,
    session: Optional[Any] = None,
        timeout: int = 30,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self._session = session or requests.Session()
        self.timeout = timeout

        # default headers
        self._session.headers.update({"Accept": "application/json"})
        if api_token:
            self._session.headers.update({"Authorization": f"Bearer {api_token}"})

    def _url(self, path: str) -> str:
        return f"{self.base_url}{path}"

    def _raise_for_status(self, resp: requests.Response) -> None:
        if not resp.ok:
            # try to parse json error
            try:
                payload = resp.json()
            except Exception:
                payload = resp.text
            raise APIError(f"HTTP {resp.status_code}: {payload}")

    def list_graphs(self) -> Dict[str, Any]:
        """GET /graphs - list available user graphs/databases."""
        resp = self._session.get(self._url("/graphs"), timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()

    def get_graph_schema(self, graph_id: str) -> Dict[str, Any]:
        """GET /graphs/{graph_id}/data - return schema nodes/edges."""
        resp = self._session.get(self._url(f"/graphs/{graph_id}/data"), timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()

    def delete_graph(self, graph_id: str) -> Dict[str, Any]:
        """DELETE /graphs/{graph_id} - delete a graph."""
        resp = self._session.delete(self._url(f"/graphs/{graph_id}"), timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()

    def refresh_graph(self, graph_id: str) -> Dict[str, Any]:
        """POST /graphs/{graph_id}/refresh - refresh schema."""
        resp = self._session.post(self._url(f"/graphs/{graph_id}/refresh"), timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()

    def connect_database(self, db_url: str) -> Iterator[Dict[str, Any]]:
        """POST /database - send database url and stream progress.

        Returns an iterator that yields decoded JSON objects as they arrive
        separated by the server's streaming protocol.
        """
        payload = {"url": db_url}
        resp = self._session.post(self._url("/database"), json=payload, stream=True, timeout=self.timeout)
        self._raise_for_status(resp)

        # The server streams JSON and uses a delimiter. We'll yield by lines
        for chunk in resp.iter_lines(decode_unicode=True):
            if not chunk:
                continue
            # the backend may send concatenated json, attempt to split by common delimiter
            # The client doesn't need to know exact delimiter; try to parse each chunk as JSON
            try:
                yield json.loads(chunk)
            except Exception:
                # fallback: try to split by '|||' or newline
                parts = chunk.split("|||")
                for part in parts:
                    part = part.strip()
                    if not part:
                        continue
                    try:
                        yield json.loads(part)
                    except Exception:
                        yield {"raw": part}

    def generate_token(self) -> Dict[str, Any]:
        """POST /tokens/generate - generate API token (requires OAuth session)."""
        resp = self._session.post(self._url("/tokens/generate"), timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()

    def list_tokens(self) -> Dict[str, Any]:
        """GET /tokens/list - list API tokens."""
        resp = self._session.get(self._url("/tokens/list"), timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()

    def delete_token(self, token_id: str) -> Dict[str, Any]:
        """DELETE /tokens/{token_id} - delete token by last-4-chars id."""
        resp = self._session.delete(self._url(f"/tokens/{token_id}"), timeout=self.timeout)
        self._raise_for_status(resp)
        return resp.json()

    # Chat/query endpoints
    def query(self, graph_id: str, chat_data: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """POST /graphs/{graph_id} - send ChatRequest and stream generator responses.

        chat_data must match the server-side ChatRequest model. Usually a dict with
        {'messages': [...], 'sources': [...]} etc. This method yields JSON objects
        as they are streamed by the server.
        """
        resp = self._session.post(self._url(f"/graphs/{graph_id}"), json=chat_data, stream=True, timeout=self.timeout)
        self._raise_for_status(resp)
        for chunk in resp.iter_lines(decode_unicode=True):
            if not chunk:
                continue
            try:
                yield json.loads(chunk)
            except Exception:
                # server may send partial JSON, try to yield raw
                yield {"raw": chunk}

    def confirm(self, graph_id: str, confirm_data: Dict[str, Any]) -> Iterator[Dict[str, Any]]:
        """POST /graphs/{graph_id}/confirm - confirm destructive ops; stream responses."""
        resp = self._session.post(self._url(f"/graphs/{graph_id}/confirm"), json=confirm_data, stream=True, timeout=self.timeout)
        self._raise_for_status(resp)
        for chunk in resp.iter_lines(decode_unicode=True):
            if not chunk:
                continue
            try:
                yield json.loads(chunk)
            except Exception:
                yield {"raw": chunk}
