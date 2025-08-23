"""Database connection routes for the text2sql API."""

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.loaders.postgres_loader import PostgresLoader
from api.loaders.mysql_loader import MySQLLoader
from api.auth.user_management import token_required
from api.logging_config import get_logger

database_router = APIRouter()
logger = get_logger(__name__)


class DatabaseConnectionRequest(BaseModel):
    """Database connection request model.

    Args:
        BaseModel (_type_): _description_
    """
    url: str


@database_router.post("/database")
@token_required
async def connect_database(request: Request, db_request: DatabaseConnectionRequest):
    """
    Accepts a JSON payload with a database URL and attempts to connect.
    Supports both PostgreSQL and MySQL databases.
    Returns success or error message.
    """
    url = db_request.url
    if not url:
        raise HTTPException(status_code=400, detail="No URL provided")

    # Validate URL format
    if not isinstance(url, str) or len(url.strip()) == 0:
        raise HTTPException(status_code=400, detail="Invalid URL format")

    try:
        success = False
        result = ""

        # Check for PostgreSQL URL
        if url.startswith("postgres://") or url.startswith("postgresql://"):
            try:
                # Attempt to connect/load using the PostgreSQL loader
                success, result = PostgresLoader.load(request.state.user_id, url)
            except (ValueError, ConnectionError) as e:
                logger.error("PostgreSQL connection error", error=str(e))
                raise HTTPException(
                    status_code=500,
                    detail="Failed to connect to PostgreSQL database",
                )

        # Check for MySQL URL
        elif url.startswith("mysql://"):
            try:
                # Attempt to connect/load using the MySQL loader
                success, result = MySQLLoader.load(request.state.user_id, url)
            except (ValueError, ConnectionError) as e:
                logger.error("MySQL connection error", error=str(e))
                raise HTTPException(
                    status_code=500, detail="Failed to connect to MySQL database"
                )

        else:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Invalid database URL. Supported formats: postgresql:// "
                    "or mysql://"
                ),
            )

        if success:
            return JSONResponse(content={
                "success": True,
                "message": "Database connected successfully"
            })

        # Don't return detailed error messages to prevent information exposure
        logger.error("Database loader failed", error=str(result))
        raise HTTPException(status_code=400, detail="Failed to load database schema")

    except (ValueError, TypeError) as e:
        logger.error("Unexpected error in database connection", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error")
