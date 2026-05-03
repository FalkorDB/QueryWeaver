"""Main entry point for the text2sql API."""

# Load .env before any app imports that read os.getenv at module level
from dotenv import load_dotenv
load_dotenv()

from api.app_factory import create_app  # pylint: disable=wrong-import-position

app = create_app()


def main() -> None:
    """Console-script entrypoint (``queryweaver`` after ``pip install``)."""
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
# This allows running the app with `uvicorn api.index:app` or directly with `python api/index.py`
# Ensure the environment variable FASTAPI_DEBUG is set to 'True' for debug mode
# or 'False' for production mode.
