"""Resolve a FalkorDB handle, falling back to the server-side singleton.

Core text2sql functions accept an optional ``db`` parameter so the SDK can
inject its own connection without mutating process globals. When ``db`` is
None (route handlers that haven't threaded it yet), we lazily import the
module-level singleton from ``api.extensions``. The import is deferred so
the SDK can use this module without triggering ``api.extensions``'s
import-time FalkorDB connect.
"""

from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # Import only for type checking — avoids pulling falkordb at runtime when
    # callers pass an explicit handle and never need the server default.
    from falkordb.asyncio import FalkorDB


def resolve_db(db: Optional["FalkorDB"] = None) -> "FalkorDB":
    """Return the given ``db`` handle, or lazily import the server default."""
    if db is not None:
        return db
    # pylint: disable=import-outside-toplevel
    from api.extensions import db as _default_db
    return _default_db
