"""
The wsgi.py file is the entry point for the application. 
It creates an instance of the Flask application using the create_app 
function defined in the __init__.py file. 
If the script is executed directly (i.e., not imported as a module), 
the application runs in debug mode. 
This allows for easier debugging during development.
"""
from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(debug=True)
