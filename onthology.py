"""Ontology generation module for CRM system knowledge graph."""

from falkordb import FalkorDB
from graphrag_sdk import Ontology
from graphrag_sdk.models.litellm import LiteModel

model = LiteModel(model_name="gemini/gemini-2.0-flash")
db = FalkorDB(host="localhost", port=6379)
KG_NAME = "crm_system"
ontology = Ontology.from_kg_graph(db.select_graph(KG_NAME), 1000000000)
ontology.save_to_graph(db.select_graph(f"{{{KG_NAME}}}_schema"))
