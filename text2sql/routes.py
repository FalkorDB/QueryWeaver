""" This module contains the routes for the text2sql API. """
import json
import os
from functools import wraps
from dotenv import load_dotenv
from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context, Flask
from litellm import completion
from text2sql.config import Config
from text2sql.graph import find
from text2sql.extensions import db
from text2sql.loaders.csv_loader import CSVLoader
from text2sql.loaders.json_loader import JSONLoader
from text2sql.loaders.odata_loader import ODataLoader
from text2sql.utils import llm_answer_validator, llm_table_validator
from text2sql.agents import RelevancyAgent, AnalysisAgent

# Load environment variables from .env file
load_dotenv()

# Use the same delimiter as in the JavaScript
MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||'

main = Blueprint("main", __name__)

SECRET_TOKEN = os.getenv('SECRET_TOKEN')
def verify_token(token):
    """ Verify the token provided in the request """
    return token == SECRET_TOKEN or (token is None and SECRET_TOKEN is None)

def token_required(f):
    """ Decorator to protect routes with token authentication """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        token = request.headers.get('Authorization')  # Get token from header
        if not verify_token(token):
            return jsonify(message="Unauthorized"), 401
        return f(*args, **kwargs)
    return decorated_function

app = Flask(__name__)


@main.route('/')
@token_required  # Apply token authentication decorator
def home():
    """ Home route """
    return render_template('chat.html')

@main.route('/graphs')
@token_required  # Apply token authentication decorator
def graphs():
    """
    This route is used to list all the graphs that are available in the database.
    """
    return db.list_graphs()

@main.route("/graphs", methods=["POST"])
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

@main.route("/graphs/<string:graph_id>", methods=["POST"])
@token_required  # Apply token authentication decorator
def query(graph_id: str):
    """
    text2sql
    """


    # Create a generator function for streaming
    def generate():
        agent_rel = RelevancyAgent()
        agent_an = AnalysisAgent()

        to_show = True

        step = {"type": "reasoning_step", "message": "Extracting relevant tables from schema..."}
        yield json.dumps(step) + MESSAGE_DELIMITER

        success, result, db_description, tables_by_method = find(graph_id, queries_history)
        if not success:
            return jsonify({"error": result}), 400

        # if to_show:


        answer_rel = agent_rel.get_answer(queries_history[-1], result)
        answer_an = agent_an.get_analysis(queries_history[-1], result, db_description)
        if answer_rel["status"] != "On-topic":
            step = {"type": "followup_questions", "message": "Off topic question: " + answer_rel["reason"]}
            yield json.dumps(step) + MESSAGE_DELIMITER

            # step = {"type": "reasoning_step", "data": "You may try the following instead: " + str(answer_rel["suggestions"])}
            # yield json.dumps(step) + MESSAGE_DELIMITER
        # else:
        else:
            # answer_fol = agent_fol.get_answer(queries_history[-1], queries_history[:-1], result)
            # if answer_fol["status"] == "Needs more data":
            #     step = {"type": "followup_questions", "message": answer_fol["followUpQuestion"]}
            #     yield json.dumps(step) + MESSAGE_DELIMITER

                # step = {"type": "reasoning_step", "message": "You may try the following instead: " + answer_fol["followUpQuestion"]}
                # yield json.dumps(step) + MESSAGE_DELIMITER
                # else:
                    # SQL generation
            step = {"type": "reasoning_step",
                    "message": "Generating SQL query from the user query and extracted schema..."}
            yield json.dumps(step) + MESSAGE_DELIMITER

            user_content = json.dumps({
                                        "schema": result,
                                        "previous_queries": queries_history[:-1],
                                        "user_query": queries_history[-1]
                                    })
            completion_result = completion(model=Config.COMPLETION_MODEL,
                                    messages=[
                                        {
                                            "content": Config.Text_To_SQL_PROMPT.format(db_description=db_description),
                                            "role": "system"
                                        },
                                        {
                                            "content": user_content,
                                            "role": "user"
                                        }
                                    ],
                                    temperature=0,
                                    aws_profile_name=Config.AWS_PROFILE,
                                    aws_region_name=Config.AWS_REGION,
                                )
            
            answer = completion_result.choices[0].message.content

            yield json.dumps({"type": "final_result", "data": answer}) + MESSAGE_DELIMITER

    return Response(stream_with_context(generate()), content_type='application/json')

# def init_routes(app):
#     """
#     Initialize routes
#     """
#     app.register_blueprint(main)
