# Routes module for text2sql API

from .auth import auth_bp
from .graphs import graphs_bp
from .database import database_bp

__all__ = ["auth_bp", "graphs_bp", "database_bp"]
