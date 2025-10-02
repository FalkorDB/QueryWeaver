import json
import pytest

from queryweaver_client.client import QueryWeaverClient, APIError


class DummyResp:
    def __init__(self, status_code=200, json_data=None, text=""):
        self.status_code = status_code
        self._json = json_data
        self.text = text

    @property
    def ok(self):
        return 200 <= self.status_code < 300

    def json(self):
        if self._json is None:
            raise ValueError("no json")
        return self._json

    def iter_lines(self, decode_unicode=True):
        # yield a few JSON lines
        yield json.dumps({"step": 1})
        yield json.dumps({"step": 2})


class DummySession:
    def __init__(self):
        self.headers = {}

    def get(self, url, timeout=None):
        return DummyResp(json_data={"graphs": []})

    def post(self, url, json=None, stream=False, timeout=None):
        if url.endswith("/database") and stream:
            return DummyResp(json_data=None)
        return DummyResp(json_data={"ok": True})

    def delete(self, url, timeout=None):
        return DummyResp(json_data={"deleted": True})


def test_list_graphs_and_delete():
    sess = DummySession()
    c = QueryWeaverClient("http://localhost:5000", session=sess)
    assert c.list_graphs() == {"graphs": []}
    assert c.delete_graph("mydb") == {"deleted": True}


def test_connect_database_stream():
    sess = DummySession()
    c = QueryWeaverClient("http://localhost:5000", session=sess)
    it = c.connect_database("postgres://x")
    out = list(it)
    assert isinstance(out, list)


def test_error_raised_for_bad_status():
    class BadSession(DummySession):
        def get(self, url, timeout=None):
            return DummyResp(status_code=500, text="boom")

    sess = BadSession()
    c = QueryWeaverClient("http://localhost:5000", session=sess)
    with pytest.raises(APIError):
        c.list_graphs()
