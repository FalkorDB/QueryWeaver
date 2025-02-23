""" This module contains the routes for the text2sql API. """
from flask import Blueprint, jsonify, render_template, request
from text2sql.graph import find, load_graph
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
    data = request.get_json()
    success, result = load_graph(graph_id, data)
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
    if success:
        return jsonify(result)

    return jsonify({"error": result}), 400

def init_routes(app):
    """
    Initialize routes
    """
    app.register_blueprint(main)
