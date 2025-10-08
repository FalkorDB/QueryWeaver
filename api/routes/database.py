"""Database connection routes for the text2sql API."""
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from api.auth.user_management import token_required
from api.core.schema_loader import load_database
from api.routes.tokens import UNAUTHORIZED_RESPONSE

database_router = APIRouter(tags=["Database Connection"])

# Use the same delimiter as in the JavaScript frontend for streaming chunks
MESSAGE_DELIMITER = "|||FALKORDB_MESSAGE_BOUNDARY|||"

class DatabaseConnectionRequest(BaseModel):
    """Database connection request model.

    Args:
        BaseModel (_type_): _description_
    """

    url: str

@database_router.post("/database", operation_id="connect_database", tags=["mcp_tool"], responses={
    401: UNAUTHORIZED_RESPONSE
})
@token_required
async def connect_database(request: Request, db_request: DatabaseConnectionRequest):
    """
    Accepts a JSON payload with a database URL and attempts to connect.
    Supports both PostgreSQL and MySQL databases.
    Streams progress steps as a sequence of JSON messages separated by MESSAGE_DELIMITER.
    """
    generator = await load_database(db_request.url, request.state.user_id)
    return StreamingResponse(generator, media_type="application/json")
