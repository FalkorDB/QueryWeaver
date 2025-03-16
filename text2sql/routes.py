""" This module contains the routes for the text2sql API. """
import json
from flask import Blueprint, Response, jsonify, render_template, request, stream_with_context
from litellm import completion
from text2sql.config import Config
from text2sql.graph import find
from text2sql.extensions import db
from text2sql.loaders.csv_loader import CSVLoader
from text2sql.loaders.json_loader import JSONLoader
from text2sql.loaders.odata_loader import ODataLoader
from text2sql.utils import llm_answer_validator, llm_table_validator

# Use the same delimiter as in the JavaScript
MESSAGE_DELIMITER = '|||FALKORDB_MESSAGE_BOUNDARY|||'

main = Blueprint("main", __name__)

@main.route('/')
def home():
    """ Home route """
    return render_template('chat.html')

@main.route('/graphs')
def graphs():
    """
    This route is used to list all the graphs that are available in the database.
    """
    return db.list_graphs()

@main.route("/graphs", methods=["POST"])
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
def query(graph_id: str):
    """
    text2sql
    """
    # q = request.args.get('q', type=str)
    # if not q:
    #     return jsonify({"error": "Missing query parameter 'q'"}), 400

    queries_history = request.get_json()
    if not queries_history:
        return jsonify({"error": "Invalid or missing JSON data"}), 400

    # Create a generator function for streaming
    def generate():

        step = {"type": "reasoning_step", "message": "Extracting relevant tables from schema..."}
        yield json.dumps(step) + MESSAGE_DELIMITER

        success, result, db_description = find(graph_id, queries_history)
        if not success:
            return jsonify({"error": result}), 400

        # Extract table names and descriptions
        table_info = json.dumps([(table[0], table[1]) for table in result])

        step = {"type": "reasoning_step",
                "message": f"This is the list of tables extracted: {table_info}"}

        yield json.dumps(step) + MESSAGE_DELIMITER

        # SQL generation
        step = {"type": "reasoning_step",
                "message": "Generating SQL query from the user query and extracted schema"}
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
                                ]
                            )
        answer = completion_result.choices[0].message.content
        question = queries_history[-1]
        score, exp = llm_table_validator(question, answer, table_info)
        print(f"Score: {score}")
        yield json.dumps({"type": "final_result", "data": answer}) + MESSAGE_DELIMITER

    return Response(stream_with_context(generate()), content_type='application/json')

def init_routes(app):
    """
    Initialize routes
    """
    app.register_blueprint(main)
