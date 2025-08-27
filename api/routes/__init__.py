"""Routes module for text2sql API."""

from .auth import auth_router
from .graphs import graphs_router
from .database import database_router

__all__ = ["auth_router", "graphs_router", "database_router"]
