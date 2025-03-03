from falkordb import FalkorDB
from graphrag_sdk import Ontology
from graphrag_sdk.models.litellm import LiteModel

model = LiteModel(model_name="gemini/gemini-2.0-flash")
db = FalkorDB(host='localhost', port=6379)
kg_name = "crm_system"
ontology = Ontology.from_kg_graph(db.select_graph(kg_name), 1000000000)
ontology.save_to_graph(db.select_graph(f"{{{kg_name}}}_schema"))
