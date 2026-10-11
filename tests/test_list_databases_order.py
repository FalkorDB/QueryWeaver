"""list_databases returns graphs in a stable order, whatever GRAPH.LIST returns."""

from api.core.schema_loader import list_databases


class _FakeDB:  # pylint: disable=too-few-public-methods
    def __init__(self, graphs):
        self._graphs = graphs

    async def list_graphs(self):
        return list(self._graphs)


async def test_user_graphs_are_sorted():
    db = _FakeDB(["u1_testdb_delete", "other_x", "u1_testdb", "u1_alpha"])
    assert await list_databases("u1", db=db) == ["alpha", "testdb", "testdb_delete"]


async def test_demo_graphs_sorted_and_after_user_graphs():
    db = _FakeDB(["DEMO_b", "u1_z", "DEMO_a", "u1_a"])
    assert await list_databases("u1", general_prefix="DEMO_", db=db) == [
        "a", "z", "DEMO_a", "DEMO_b",
    ]


async def test_order_independent_of_server_order():
    graphs = ["u1_testdb", "u1_testdb_delete", "u1_crm"]
    first = await list_databases("u1", db=_FakeDB(graphs))
    second = await list_databases("u1", db=_FakeDB(list(reversed(graphs))))
    assert first == second == ["crm", "testdb", "testdb_delete"]
