"""Graph retrieval limits concurrent queries and preserves result order."""

import asyncio
from types import SimpleNamespace

import pytest

from api.graph import (
    _GRAPH_QUERY_BATCH_SIZE, _find_tables, _find_tables_by_columns, _find_tables_sphere,
)


@pytest.mark.unit
@pytest.mark.parametrize("find", [_find_tables, _find_tables_by_columns, _find_tables_sphere])
@pytest.mark.parametrize("count", [0, 1, 35, 512])
async def test_graph_queries_are_bounded_and_keep_all_rows(find, count):
    active = 0
    peak = 0
    calls = []

    class Graph:
        async def query(self, query, params, timeout):
            nonlocal active, peak
            value = next(iter(params.values()))
            active += 1
            peak = max(peak, active)
            calls.append(value)
            await asyncio.sleep(0)
            active -= 1
            return SimpleNamespace(result_set=[[value, "first"], [value, "second"]])

    values = [str(i) for i in range(count)] if find is _find_tables_sphere else [[float(i)] for i in range(count)]
    result = await find(Graph(), values)

    assert peak <= _GRAPH_QUERY_BATCH_SIZE
    if count > 1:
        assert peak > 1
    assert calls == values
    assert result == [[value, row] for value in values for row in ("first", "second")]


@pytest.mark.unit
@pytest.mark.parametrize("find", [_find_tables, _find_tables_by_columns, _find_tables_sphere])
async def test_graph_query_failure_does_not_return_partial_rows(find):
    class Graph:
        async def query(self, query, params, timeout):
            value = next(iter(params.values()))
            index = int(value) if isinstance(value, str) else int(value[0])
            if index == _GRAPH_QUERY_BATCH_SIZE:
                raise RuntimeError("query failed")
            return SimpleNamespace(result_set=[[value]])

    count = _GRAPH_QUERY_BATCH_SIZE + 1
    values = [str(i) for i in range(count)] if find is _find_tables_sphere else [[float(i)] for i in range(count)]
    if find is _find_tables_sphere:
        assert await find(Graph(), values) == []
    else:
        with pytest.raises(RuntimeError, match="query failed"):
            await find(Graph(), values)
