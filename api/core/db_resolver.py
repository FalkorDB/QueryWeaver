"""Resolve a FalkorDB handle, falling back to the server-side singleton.

Core text2sql functions accept an optional ``db`` parameter so the SDK can
inject its own connection without mutating process globals. When ``db`` is
None (route handlers that haven't threaded it yet), we lazily import the
module-level singleton from ``api.extensions``. The import is deferred so
the SDK can use this module without triggering ``api.extensions``'s
import-time FalkorDB connect.
"""


def resolve_db(db=None):
    """Return the given ``db`` handle, or lazily import the server default."""
    if db is not None:
        return db
    # pylint: disable=import-outside-toplevel
    from api.extensions import db as _default_db
    return _default_db
