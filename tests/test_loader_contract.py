"""Every loader must accept the explicit graph handle.

``schema_loader`` calls ``loader.load(user_id, url, db=db)`` and
``_emit_schema_refresh`` calls ``loader.refresh_graph_schema(..., db=db)``, so a
loader missing the parameter raises ``TypeError`` at runtime rather than at
import — Snowflake did, which broke connecting and refreshing a Snowflake
database outright. A signature check catches that without needing a live
warehouse.
"""

import inspect

import pytest

# Imported via api.core.pipeline: importing a loader module first hits a
# circular import (pipeline imports the loaders, the loaders import api.core).
# Going through pipeline initialises the package in the right order, which also
# makes the snowflake import below work.
from api.core.pipeline import MySQLLoader, PostgresLoader
from api.loaders.snowflake_loader import SnowflakeLoader

LOADERS = [PostgresLoader, MySQLLoader, SnowflakeLoader]


@pytest.mark.unit
@pytest.mark.parametrize("loader", LOADERS, ids=lambda l: l.__name__)
@pytest.mark.parametrize("method", ["load", "refresh_graph_schema"])
def test_loader_accepts_explicit_db_handle(loader, method):
    params = inspect.signature(getattr(loader, method)).parameters
    assert "db" in params, (
        f"{loader.__name__}.{method} must accept db= — callers pass it, so a "
        "missing parameter is a runtime TypeError"
    )
    assert params["db"].default is None, (
        f"{loader.__name__}.{method} db= must be optional"
    )


@pytest.mark.unit
@pytest.mark.parametrize("loader", LOADERS, ids=lambda l: l.__name__)
def test_loader_refresh_resolves_the_handle(loader):
    """Refresh must resolve the passed handle, not reach for the singleton.

    Using the module-level ``api.extensions.db`` ignores the caller's handle,
    which is what the parameter exists to provide.
    """
    source = inspect.getsource(getattr(loader, "refresh_graph_schema"))
    assert "resolve_db(" in source, f"{loader.__name__} should use resolve_db(db)"
    assert "from api.extensions import db" not in source, (
        f"{loader.__name__} refresh ignores the caller's handle"
    )
