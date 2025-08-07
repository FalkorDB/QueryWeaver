# Routes module for text2sql API

from .main import main_bp
from .graphs import graphs_bp
from .database import database_bp

__all__ = ["main_bp", "graphs_bp", "database_bp"]
