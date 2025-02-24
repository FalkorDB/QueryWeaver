""" This module contains the routes for the text2sql API. """
from flask import Blueprint, jsonify, render_template, request
from litellm import completion
from text2sql.config import Config
from text2sql.graph import find, load_json_graph, load_xml_graph
from text2sql.extensions import db


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

@main.route("/graphs/<string:graph_id>", methods=["POST"])
def load(graph_id: str):
    """
    This route is used to load the graph data into the database.
    It gets the Graph name as an argument and expects
    a JSON payload with the following structure: txt2sql/schema_schema.json
    """
    success, result = False, "Invalid content type"
    content_type = request.content_type

    if 'application/json' in content_type:
        data = request.get_json()
        success, result = load_json_graph(graph_id, data)
    elif 'application/xml' in content_type or 'text/xml' in content_type:
        xml_data = request.data
        success, result = load_xml_graph(graph_id, xml_data)

    if success:
        return jsonify({"message": result, "graph_id": graph_id})

    return jsonify({"error": result}), 400

@main.route("/graph/<string:graph_id>", methods=["GET"])
def query(graph_id: str):
    """
    text2sql
    """
    q = request.args.get('q', type=str)
    if not q:
        return jsonify({"error": "Missing query parameter 'q'"}), 400

    success, result = find(graph_id, q)
    if not success:
        return jsonify({"error": result}), 400

    completion_result = completion(model=Config.COMPLETION_MODEL,
                            messages=[
                                {
                                    "content": Config.Text_To_SQL_PROMPT,
                                    "role": "system"
                                },
                                {
                                    "content": q,
                                    "role": "user"
                                }
                            ]
                        )
    
    return jsonify(completion_result.choices[0].message.content)


def init_routes(app):
    """
    Initialize routes
    """
    app.register_blueprint(main)
