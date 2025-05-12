""" This module contains the routes for the text2sql API. """
import json
import os
import logging
from functools import wraps
from dotenv import load_dotenv
from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context, Flask
from api.graph import find
from api.extensions import db
from api.loaders.csv_loader import CSVLoader
from api.loaders.json_loader import JSONLoader
from api.loaders.odata_loader import ODataLoader
from api.agents import RelevancyAgent, AnalysisAgent
from api.config import Config

# Load environment variables from .env file
load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Use the same delimiter as in the JavaScript
MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||'

main = Blueprint("main", __name__)

SECRET_TOKEN = os.getenv('SECRET_TOKEN')
SECRET_TOKEN_GEN = os.getenv('SECRET_TOKEN_GEN')
def verify_token(token):
    """ Verify the token provided in the request """
    return token == SECRET_TOKEN or token == SECRET_TOKEN_GEN

def token_required(f):
    """ Decorator to protect routes with token authentication """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.args.get('token', 'EMPTY')  # Get token from header
        os.environ["USER_TOKEN"] = token
        if not verify_token(token):
            return jsonify(message="Unauthorized"), 401
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)

# @app.before_request
# def before_request_func():
#     oidc_token = request.headers.get('x-vercel-oidc-token')
#     if oidc_token:
#         set_oidc_token(oidc_token)
#         credentials = assume_role()
#     else:
#         # Optional: require it for protected routes
#         pass

@app.route('/')
@token_required  # Apply token authentication decorator
def home():
    """ Home route """
    return render_template('chat.html')

@app.route('/graphs')
@token_required  # Apply token authentication decorator
def graphs():
    """
    This route is used to list all the graphs that are available in the database.
    """
    graphs = db.list_graphs()
    if os.getenv("USER_TOKEN") == SECRET_TOKEN:
        if 'hospital' in graphs:
            return ['hospital']
    else:
        graphs.remove('hospital')
    return graphs

@app.route("/graphs", methods=["POST"])
@token_required  # Apply token authentication decorator
def load():
    """
    This route is used to load the graph data into the database.
    It expects either:
    - A JSON payload (application/json)
    - A File upload (multipart/form-data)
    - An XML payload (application/xml or text/xml)
    """
    content_type = request.content_type
    success, result = False, "Invalid content type"
    graph_id = ""

    # ✅ Handle JSON Payload
    if content_type.startswith("application/json"):
        data = request.get_json()
        if not data or "database" not in data:
            return jsonify({"error": "Invalid JSON data"}), 400

        graph_id = data["database"]
        success, result = JSONLoader.load(graph_id, data)

    # ✅ Handle XML Payload
    elif content_type.startswith("application/xml") or content_type.startswith("text/xml"):
        xml_data = request.data
        graph_id = ""
        success, result = ODataLoader.load(graph_id, xml_data)

    # ✅ Handle CSV Payload
    elif content_type.startswith("text/csv"):
        csv_data = request.data
        graph_id = ""
        success, result = CSVLoader.load(graph_id, csv_data)

    # ✅ Handle File Upload (FormData with JSON/XML)
    elif content_type.startswith("multipart/form-data"):
        if "file" not in request.files:
            return jsonify({"error": "No file uploaded"}), 400

        file = request.files["file"]
        if file.filename == "":
            return jsonify({"error": "Empty file"}), 400

        # ✅ Check if file is JSON
        if file.filename.endswith(".json"):
            try:
                data = json.load(file)
                graph_id = data.get("database", "")
                success, result = JSONLoader.load(graph_id, data)
            except json.JSONDecodeError:
                return jsonify({"error": "Invalid JSON file"}), 400

        # ✅ Check if file is XML
        elif file.filename.endswith(".xml"):
            xml_data = file.read().decode("utf-8")  # Convert bytes to string
            graph_id = file.filename.replace(".xml", "")
            success, result = ODataLoader.load(graph_id, xml_data)
            
        # ✅ Check if file is csv
        elif file.filename.endswith(".csv"):
            csv_data = file.read().decode("utf-8")  # Convert bytes to string
            graph_id = file.filename.replace(".csv", "")
            success, result = CSVLoader.load(graph_id, csv_data)
            
        else:
            return jsonify({"error": "Unsupported file type"}), 415
    else:
        return jsonify({"error": "Unsupported Content-Type"}), 415

    # ✅ Return the final response
    if success:
        return jsonify({"message": result, "graph_id": graph_id})

    return jsonify({"error": result}), 400

@app.route("/graphs/<string:graph_id>", methods=["POST"])
@token_required  # Apply token authentication decorator
def query(graph_id: str):
    """
    text2sql
    """
    request_data = request.get_json()
    queries_history = request_data.get("chat")
    instructions = request_data.get("instructions")
    if not queries_history:
        return jsonify({"error": "Invalid or missing JSON data"}), 400
    
    logging.info(f"User Query: {queries_history[-1]}")

    # Create a generator function for streaming
    def generate():
        agent_rel = RelevancyAgent()
        agent_an = AnalysisAgent()


        step = {"type": "reasoning_step", "message": "Extracting relevant tables from schema..."}
        yield json.dumps(step) + MESSAGE_DELIMITER
        try:
            success, result, db_description, _ = find(graph_id, queries_history)
        except Exception as e:
            logging.error(f"Error in find function: {e}")
            return jsonify({"error": "Error in find function"}), 500
        if not success:
            return jsonify({"error": result}), 400

        answer_rel = agent_rel.get_answer(queries_history[-1], result)
        if answer_rel["status"] != "On-topic":
            step = {"type": "followup_questions", "message": "Off topic question: " + answer_rel["reason"]}
            logging.info(f"SQL Fail reason: {answer_rel["reason"]}")
            yield json.dumps(step) + MESSAGE_DELIMITER
        else:
            step = {"type": "reasoning_step",
                    "message": "Generating SQL query from the user query and extracted schema..."}
            yield json.dumps(step) + MESSAGE_DELIMITER
            answer_an = agent_an.get_analysis(queries_history[-1], result, db_description, instructions)

            logging.info(f"SQL Result: {answer_an['sql_query']}")
            yield json.dumps({"type": "final_result", "data": answer_an['sql_query'], "conf": answer_an['confidence'],
                             "miss": answer_an['missing_information'],
                             "amb": answer_an['ambiguities'],
                             "exp": answer_an['explanation']}) + MESSAGE_DELIMITER

    return Response(stream_with_context(generate()), content_type='application/json')

if __name__ == "__main__":
    app.register_blueprint(main)
    app.run(debug=True)
