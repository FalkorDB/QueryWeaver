"""Main entry point for the text2sql API."""

# Load .env before any app imports that read os.getenv at module level
from dotenv import load_dotenv
load_dotenv()

from api.app_factory import create_app  # pylint: disable=wrong-import-position

app = create_app()

if __name__ == "__main__":
    import os
    import uvicorn

    # Read FASTAPI_DEBUG to determine debug mode
    debug_mode = os.environ.get('FASTAPI_DEBUG', 'False').lower() == 'true'
    uvicorn.run(
        "api.index:app",
        host="127.0.0.1",
        port=5000,
        reload=debug_mode,
        log_level="info" if debug_mode else "warning",
    )
# This allows running the app with `uvicorn api.index:app` or directly with `python api/index.py`
# Ensure the environment variable FASTAPI_DEBUG is set to 'True' for debug mode
# or 'False' for production mode.
