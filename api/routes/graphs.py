"""Graph-related routes for the text2sql API."""

from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel

from api.core.schema_loader import list_databases
from api.core.text2sql import (
    GENERAL_PREFIX,
    ChatRequest,
    ConfirmRequest,
    GraphNotFoundError,
    InternalError,
    InvalidArgumentError,
    delete_database,
    execute_destructive_operation,
    get_schema,
    query_database,
    refresh_database_schema,
)
from api.auth.user_management import token_required
from api.routes.tokens import UNAUTHORIZED_RESPONSE

graphs_router = APIRouter(tags=["Graphs & Databases"])


class GraphData(BaseModel):
    """Graph data model.

    Args:
        BaseModel (_type_): _description_
    """

    database: str


@graphs_router.get(
    "",
    operation_id="list_databases",
    tags=["mcp_tool"],
    responses={401: UNAUTHORIZED_RESPONSE},
)
@token_required
async def list_graphs(request: Request):
    """
    This route is used to list all the graphs (databases names) that are available in the database.
    """
    graphs = await list_databases(request.state.user_id, GENERAL_PREFIX)
    return JSONResponse(content=graphs)


@graphs_router.get(
    "/{graph_id}/data",
    operation_id="database_schema",
    tags=["mcp_tool"],
    responses={401: UNAUTHORIZED_RESPONSE},
)
@token_required
async def get_graph_data(
    request: Request, graph_id: str
):  # pylint: disable=too-many-locals,too-many-branches
    """Return all nodes and edges for the specified database schema (namespaced to the user).

    This endpoint returns a JSON object with two keys: `nodes` and `edges`.
    Nodes contain a minimal set of properties (id, name, labels, props).
    Edges contain source and target node names (or internal ids), type and props.

        args:
            graph_id (str): The ID of the graph to query (the database name).
    """

    try:
        schema = await get_schema(request.state.user_id, graph_id)
        return JSONResponse(content=schema)
    except GraphNotFoundError as gnfe:
        return JSONResponse(content={"error": str(gnfe)}, status_code=404)
    except InternalError as ie:
        return JSONResponse(content={"error": str(ie)}, status_code=500)


@graphs_router.post("", responses={401: UNAUTHORIZED_RESPONSE})
@token_required
async def load_graph(
    request: Request, data: GraphData = None, file: UploadFile = File(None)
):  # pylint: disable=unused-argument
    """
    This route is used to load the graph data into the database.
    It expects either:
    - A JSON payload (application/json)
    - A File upload (multipart/form-data)
    - An XML payload (application/xml or text/xml)
    """

    # ✅ Handle JSON Payload
    if data:  # pylint: disable=no-else-raise
        raise HTTPException(status_code=501, detail="JSONLoader is not implemented yet")
    # ✅ Handle File Upload
    elif file:
        filename = file.filename

        # ✅ Check if file is JSON
        if filename.endswith(".json"):  # pylint: disable=no-else-raise
            raise HTTPException(
                status_code=501, detail="JSONLoader is not implemented yet"
            )

        # ✅ Check if file is XML
        elif filename.endswith(".xml"):
            raise HTTPException(
                status_code=501, detail="ODataLoader is not implemented yet"
            )

        # ✅ Check if file is csv
        elif filename.endswith(".csv"):
            raise HTTPException(
                status_code=501, detail="CSVLoader is not implemented yet"
            )
        else:
            raise HTTPException(status_code=415, detail="Unsupported file type")
    else:
        raise HTTPException(status_code=415, detail="Unsupported Content-Type")


@graphs_router.post(
    "/{graph_id}",
    operation_id="query_database",
    tags=["mcp_tool"],
    responses={401: UNAUTHORIZED_RESPONSE},
)
@token_required
async def query_graph(
    request: Request, graph_id: str, chat_data: ChatRequest
):  # pylint: disable=too-many-statements
    """
    Query the Database with the given graph_id and chat_data.

        Args:
            graph_id (str): The ID of the graph to query.
            chat_data (ChatRequest): The chat data containing user queries and context.
    """
    try:
        generator = await query_database(request.state.user_id, graph_id, chat_data)
        return StreamingResponse(generator, media_type="application/json")
    except InvalidArgumentError as iae:
        return JSONResponse(content={"error": str(iae)}, status_code=400)


@graphs_router.post("/{graph_id}/confirm", responses={401: UNAUTHORIZED_RESPONSE})
@token_required
async def confirm_destructive_operation(
    request: Request,
    graph_id: str,
    confirm_data: ConfirmRequest,
):
    """
    Handle user confirmation for destructive SQL operations
    """

    try:
        generator = await execute_destructive_operation(
            request.state.user_id, graph_id, confirm_data
        )
        return StreamingResponse(generator, media_type="application/json")
    except InvalidArgumentError as iae:
        return JSONResponse(content={"error": str(iae)}, status_code=400)


@graphs_router.post("/{graph_id}/refresh", responses={401: UNAUTHORIZED_RESPONSE})
@token_required
async def refresh_graph_schema(request: Request, graph_id: str):
    """
    Manually refresh the graph schema from the database.
    This endpoint allows users to manually trigger a schema refresh
    if they suspect the graph is out of sync with the database.
    """
    try:
        return await refresh_database_schema(request.state.user_id, graph_id)
    except InternalError as ie:
        return JSONResponse(content={"error": str(ie)}, status_code=500)


@graphs_router.delete("/{graph_id}", responses={401: UNAUTHORIZED_RESPONSE})
@token_required
async def delete_graph(request: Request, graph_id: str):
    """Delete the specified graph (namespaced to the user).

    This will attempt to delete the FalkorDB graph belonging to the
    authenticated user. The graph id used by the client is stripped of
    namespace and will be namespaced using the user's id from the request
    state.
    """

    try:
        result = await delete_database(request.state.user_id, graph_id)
        return JSONResponse(content=result)

    except InvalidArgumentError as iae:
        return JSONResponse(content={"error": str(iae)}, status_code=400)
    except GraphNotFoundError as gnfe:
        return JSONResponse(content={"error": str(gnfe)}, status_code=404)
    except InternalError as ie:
        return JSONResponse(content={"error": str(ie)}, status_code=500)
