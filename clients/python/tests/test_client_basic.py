"""Test cases for QueryWeaverClient using a dummy session to simulate server responses."""

from json import dumps
from typing import Optional

import pytest

from queryweaver_client.client import QueryWeaverClient, APIError

class DummyResp:  # pylint: disable=too-few-public-methods
    """ A dummy response object to simulate aiohttp.ClientResponse. """

    def __init__(self, status=200, json_data=None, text=""):
        self.status = status
        self._json = json_data
        self._text = text
        self.content: Optional['DummyContent'] = None

    @property
    def ok(self):
        """Check if the response is successful.

        Returns:
            bool: True if the response status is in the 2xx range, False otherwise.
        """
        return 200 <= self.status < 300

    async def text(self):
        """Return the text content of the response.

        Returns:
            str: The text content of the response.
        """
        return self._text

    async def json(self):
        """Convert the response to JSON.

        Raises:
            ValueError: If the response does not contain valid JSON.

        Returns:
            dict: The JSON content of the response.
        """
        if self._json is None:
            raise ValueError("no json")
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

class DummyContent: # pylint: disable=too-few-public-methods
    """ A dummy content object to simulate aiohttp.StreamReader. """

    async def iter_any(self):
        """Simulate streaming response content."""
        # yield a few JSON lines as bytes
        yield dumps({"step": 1}).encode('utf-8')
        yield dumps({"step": 2}).encode('utf-8')

class DummySession:
    """Dummy session class to simulate aiohttp session objects for testing."""

    def __init__(self):
        self.headers = {}
        self.closed = False

    async def close(self):
        """Close the dummy session."""
        self.closed = True

    def get(self, url, timeout=None): # pylint: disable=unused-argument
        """Simulate a GET request for testing purposes.

        Args:
            url (str): The URL to send the GET request to.
            timeout (float, optional): The timeout for the request. Defaults to None.

        Returns:
            DummyResp: A dummy response object with sample graph data.
        """
        return DummyResp(json_data=[])

    def post(self, url, json=None, timeout=None): # pylint: disable=unused-argument
        """Simulate a POST request for testing purposes.

        Args:
            url (str): The URL to send the POST request to.
            json (dict, optional): The JSON data to send in the request body. Defaults to None.
            timeout (float, optional): The timeout for the request. Defaults to None.

        Returns:
            DummyResp: A dummy response object with appropriate content based on the URL.
        """
        if "/database" in url:
            resp = DummyResp()
            resp.content = DummyContent()
            return resp

        if "/graphs/" in url and not url.endswith("/confirm"):
            # Handle query requests to /graphs/{graph_id}
            resp = DummyResp()
            resp.content = DummyContent()
            return resp

        if url.endswith("/confirm"):
            # Handle confirm requests
            resp = DummyResp()
            resp.content = DummyContent()
            return resp

        return DummyResp(json_data={"ok": True})

    def delete(self, url, timeout=None): # pylint: disable=unused-argument
        """Simulate DELETE request.

        Args:
            url (str): The URL to send the request to.
            timeout (float, optional): The timeout for the request. Defaults to None.

        Returns:
            DummyResp: The simulated response object.
        """
        return DummyResp(json_data={"deleted": True})

@pytest.mark.asyncio
async def test_list_schemas_and_delete():
    """Test list_schemas and delete_schema methods."""
    sess = DummySession()
    async with QueryWeaverClient("http://localhost:5000", session=sess) as client:
        result = await client.list_schemas()
        assert result == []
        result = await client.delete_schema("mydb")
        assert result == {"deleted": True}


@pytest.mark.asyncio
async def test_connect_database_sync():
    """Test synchronous connect_database returns final result"""
    sess = DummySession()
    async with QueryWeaverClient("http://localhost:5000", session=sess) as client:
        result = await client.connect_database("postgres://x")
        assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_query():
    """Test query method returns final result from streaming response"""
    sess = DummySession()
    async with QueryWeaverClient("http://localhost:5000", session=sess) as client:
        chat_data = {
            "messages": [
                {"role": "user", "content": "Show me all users"}
            ]
        }
        result = await client.query("my_schema", chat_data)
        assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_confirm():
    """Test confirm method returns final result from streaming response"""
    sess = DummySession()
    async with QueryWeaverClient("http://localhost:5000", session=sess) as client:
        confirm_data = {
            "sql_query": "DELETE FROM users WHERE age > 30",
            "confirmation": "YES",
            "chat": [{"role": "user", "content": "Delete old users"}]
        }
        result = await client.confirm("my_schema", confirm_data)
        assert isinstance(result, dict)


@pytest.mark.asyncio
async def test_error_raised_for_bad_status():
    """Test error handling for bad HTTP status codes."""
    class BadSession(DummySession):
        """Simulate a bad session for testing."""

        def get(self, url, timeout=None): # pylint: disable=unused-argument
            return DummyResp(status=500, text="boom")

    sess = BadSession()
    async with QueryWeaverClient("http://localhost:5000", session=sess) as client:
        with pytest.raises(APIError):
            await client.list_schemas()


@pytest.mark.asyncio
async def test_api_token_applied_to_provided_session():
    """Test that api_token is applied to a provided session's headers."""
    sess = DummySession()
    QueryWeaverClient("http://localhost:5000",
                     api_token="test-token-123",
                     session=sess)

    # Verify the Authorization header was added to the session
    assert "Authorization" in sess.headers
    assert sess.headers["Authorization"] == "Bearer test-token-123"


@pytest.mark.asyncio
async def test_query_auto_confirm():
    """Test query with auto_confirm handles destructive operations automatically."""
    class CustomContent:  # pylint: disable=too-few-public-methods
        """Custom content that returns specific JSON data."""

        def __init__(self, data):
            self.data = data

        async def iter_any(self):
            """Yield the data as encoded JSON."""
            yield dumps(self.data).encode('utf-8')

    class DestructiveSession(DummySession):  # pylint: disable=too-few-public-methods
        """Session that returns destructive confirmation request."""

        def __init__(self):
            super().__init__()
            self.confirm_called = False

        def post(self, url, json=None, timeout=None): # pylint: disable=unused-argument
            if url.endswith("/confirm"):
                # Confirm endpoint returns final result
                self.confirm_called = True
                resp = DummyResp(json_data={"result": "confirmed"})
                resp.content = CustomContent({"result": "confirmed"})  # type: ignore
                return resp

            # Query endpoint returns destructive confirmation request
            confirmation_data = {
                "type": "destructive_confirmation",
                "sql_query": "DELETE FROM users",
                "message": "This will delete data"
            }
            resp = DummyResp(json_data=confirmation_data)
            resp.content = CustomContent(confirmation_data)  # type: ignore
            return resp

    sess = DestructiveSession()
    async with QueryWeaverClient("http://localhost:5000", session=sess) as client:
        chat_data = {
            "messages": [
                {"role": "user", "content": "Delete all users"}
            ]
        }

        # With auto_confirm=True, should automatically call confirm
        result = await client.query("my_schema", chat_data, auto_confirm=True)
        assert sess.confirm_called
        assert result == {"result": "confirmed"}


@pytest.mark.asyncio
async def test_query_no_auto_confirm():
    """Test query without auto_confirm returns confirmation request."""
    class CustomContent:  # pylint: disable=too-few-public-methods
        """Custom content that returns specific JSON data."""

        def __init__(self, data):
            self.data = data

        async def iter_any(self):
            """Yield the data as encoded JSON."""
            yield dumps(self.data).encode('utf-8')

    class DestructiveSession(DummySession):  # pylint: disable=too-few-public-methods
        """Session that returns destructive confirmation request."""

        def post(self, url, json=None, timeout=None): # pylint: disable=unused-argument
            # Query endpoint returns destructive confirmation request
            confirmation_data = {
                "type": "destructive_confirmation",
                "sql_query": "DELETE FROM users",
                "message": "This will delete data"
            }
            resp = DummyResp(json_data=confirmation_data)
            resp.content = CustomContent(confirmation_data)  # type: ignore
            return resp

    sess = DestructiveSession()
    async with QueryWeaverClient("http://localhost:5000", session=sess) as client:
        chat_data = {
            "messages": [
                {"role": "user", "content": "Delete all users"}
            ]
        }

        # Without auto_confirm, should return confirmation request
        result = await client.query("my_schema", chat_data, auto_confirm=False)
        assert result["type"] == "destructive_confirmation"
        assert result["sql_query"] == "DELETE FROM users"
