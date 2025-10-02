import json
import pytest

from queryweaver_client.client import QueryWeaverClient, APIError


class DummyResp:
    def __init__(self, status=200, json_data=None, text=""):
        self.status = status
        self._json = json_data
        self.text = text
        self.content = None

    @property
    def ok(self):
        return 200 <= self.status < 300

    async def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class DummyContent:
    async def iter_any(self):
        # yield a few JSON lines as bytes
        yield json.dumps({"step": 1}).encode('utf-8')
        yield json.dumps({"step": 2}).encode('utf-8')


class DummySession:
    def __init__(self):
        self.headers = {}
        self.closed = False

    async def close(self):
        self.closed = True

    def get(self, url, timeout=None):
        return DummyResp(json_data={"graphs": []})

    def post(self, url, json=None, timeout=None):
        if "/database" in url:
            resp = DummyResp()
            resp.content = DummyContent()
            return resp
        elif "/graphs/" in url and not url.endswith("/confirm"):
            # Handle query requests to /graphs/{graph_id}
            resp = DummyResp()
            resp.content = DummyContent()
            return resp
        elif url.endswith("/confirm"):
            # Handle confirm requests
            resp = DummyResp()
            resp.content = DummyContent()
            return resp
        return DummyResp(json_data={"ok": True})

    def delete(self, url, timeout=None):
        return DummyResp(json_data={"deleted": True})


@pytest.mark.asyncio
async def test_list_schemas_and_delete():
    sess = DummySession()
    async with QueryWeaverClient("http://localhost:5000", session=sess) as client:
        result = await client.list_schemas()
        assert result == {"graphs": []}
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
    class BadSession(DummySession):
        def get(self, url, timeout=None):
            return DummyResp(status=500, text="boom")

    sess = BadSession()
    async with QueryWeaverClient("http://localhost:5000", session=sess) as client:
        with pytest.raises(APIError):
            await client.list_schemas()
