"""Main entry point for the text2sql API."""

from api.app_factory import create_app

app = create_app()

if __name__ == "__main__":
    import os
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode)
# This allows running the app with `flask run` or directly with `python api/index.py`
# Ensure the environment variable FLASK_DEBUG is set to 'True' for debug mode
# or 'False' for production mode.
