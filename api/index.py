"""Main entry point for the text2sql API."""

from api.app_factory import create_app

app = create_app()

if __name__ == "__main__":
    import os
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode)
# This allows running the app with `hypercorn api.index:app` or directly with `python api/index.py`
# For production, use: hypercorn api.index:app --bind 0.0.0.0:5000
# For development with debug mode, use: FLASK_DEBUG=True python api/index.py
