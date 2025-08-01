"""Main entry point for the text2sql API."""

from api.app_factory import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
