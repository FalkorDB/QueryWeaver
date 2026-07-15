"""Public metadata route (``/version``) for the QueryWeaver API.

These endpoints are intentionally unauthenticated so the frontend can read
them before login. Their tag is not mapped to any MCP type, so FastMCP's
default EXCLUDE route map keeps them out of the MCP tool surface.
"""

from importlib.metadata import version, PackageNotFoundError

from fastapi import APIRouter

# Router
meta_router = APIRouter(tags=["Meta"])


def app_version() -> str:
    """Return the running QueryWeaver version.

    Prefers installed distribution metadata; falls back to the package's
    ``__version__`` when running from a source checkout without dist metadata.
    """
    try:
        return version("queryweaver")
    except PackageNotFoundError:
        from queryweaver import __version__  # pylint: disable=import-outside-toplevel
        return __version__


@meta_router.get("/version")
async def get_version() -> dict[str, str]:
    """Public endpoint returning the application name and version."""
    return {"name": "queryweaver", "version": app_version()}
