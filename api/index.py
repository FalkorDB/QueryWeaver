"""Main entry point for the text2sql API.

Module-level imports of ``dotenv`` / ``api.app_factory`` are guarded so that
``pip install queryweaver`` (no ``[server]`` extra) can still resolve the
``queryweaver`` console script and surface a friendly install message.
``app`` is exposed only when the server extras are present so uvicorn's
``api.index:app`` reference keeps working.
"""

try:
    # Load .env before any app imports that read os.getenv at module level.
    from dotenv import load_dotenv
    load_dotenv()
    from api.app_factory import create_app  # pylint: disable=wrong-import-position

    app = create_app()
    _SERVER_AVAILABLE = True
    _SERVER_IMPORT_ERROR: Exception | None = None
except ImportError as _exc:
    # SDK-only install: server extras are not present. Defer the failure to
    # ``main()`` so importing ``api.index`` (e.g. via the console script
    # entrypoint) does not crash before we can print the install message.
    app = None  # pylint: disable=invalid-name  # type: ignore[assignment]
    _SERVER_AVAILABLE = False
    _SERVER_IMPORT_ERROR = _exc


def main() -> None:
    """Console-script entrypoint (``queryweaver`` after ``pip install``).

    Requires the ``[server]`` extra (FastAPI + uvicorn). Plain
    ``pip install queryweaver`` installs the SDK only; the server is
    available via ``pip install queryweaver[server]``.
    """
    if not _SERVER_AVAILABLE:
        raise SystemExit(
            "queryweaver server requires the [server] extra. "
            "Install with: pip install queryweaver[server]\n"
            f"(missing: {_SERVER_IMPORT_ERROR})"
        )

    import os  # pylint: disable=import-outside-toplevel
    import uvicorn  # pylint: disable=import-outside-toplevel

    debug_mode = os.environ.get('FASTAPI_DEBUG', 'False').lower() == 'true'
    uvicorn.run(
        "api.index:app",
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        reload=debug_mode,
        log_level="info" if debug_mode else "warning",
    )


if __name__ == "__main__":
    main()
