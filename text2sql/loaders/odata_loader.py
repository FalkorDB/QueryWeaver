import re
from typing import Tuple
import xml.etree.ElementTree as ET
import tqdm
from text2sql.loaders.base_loadr import BaseLoader
from text2sql.extensions import db

class ODataLoader(BaseLoader):
    """
    This class is responsible for loading OData schemas into a Graph.
    """

    @staticmethod
    def load(graph_id: str, data) -> Tuple[bool, str]:
        """ Load XML ODATA schema into a Graph. """

        try:
            # Parse the OData schema
            entities, relationships = ODataLoader._parse_odata_schema(data)
        except ET.ParseError:
            return False, "Invalid XML content"

        # Generate Cypher queries
        entities_queries, relationships_queries = ODataLoader._generate_cypher_queries(entities, relationships)

        graph = db.select_graph(graph_id)

        # Run the Create entities Cypher queries
        for query in tqdm.tqdm(entities_queries, "Creating entities"):
            graph.query(query)

        # Run the Create relationships Cypher queries
        for query in tqdm.tqdm(relationships_queries, "Creating relationships"):
            graph.query(query)

        return True, "Graph loaded successfully"

    @staticmethod
    def _parse_odata_schema(data) -> Tuple[dict, dict]:
        """
        This function parses the OData schema and returns entities and relationships.
        """
        entities = {}
        relationships = {}

        root = ET.fromstring(data)

        # Define namespaces
        namespaces = {
            'edmx': "http://docs.oasis-open.org/odata/ns/edmx",
            'edm': "http://docs.oasis-open.org/odata/ns/edm"
        }

        schema_element = root.find(".//edmx:DataServices/edm:Schema", namespaces)
        if schema_element is None:
            raise ET.ParseError("Schema element not found")
            
        entity_types = schema_element.findall("edm:EntityType", namespaces)
        for entity_type in tqdm.tqdm(entity_types, "Parsing OData schema"):
            entity_name = entity_type.get("Name")
            entities[entity_name] = {prop.get("Name"): prop.get("Type") for prop in entity_type.findall("edm:Property", namespaces)}
            description = entity_type.findall("edm:Annotation", namespaces)
            if len(description) == 1:
                entities[entity_name]["description"] = description[0].get("String").replace("'", "\\'")

            for rel in entity_type.findall("edm:NavigationProperty", namespaces):
                if rel.get("Name") not in relationships:
                    relationships[rel.get("Name")] = []    
                relationships[rel.get("Name")].append({
                    "from": entity_name,
                    "to": re.findall("Priority.OData.(\\w+)\\b", rel.get("Type"))[0]
                })

        return entities, relationships
    
    @staticmethod
    def _generate_cypher_queries(entities, relationships):
        """
        This function generates Cypher queries for entities and relationships.
        """
        entities_queries = []
        relationships_queries = []

        for entity_name, props in tqdm.tqdm(entities.items(), "Generating create entity Cypher queries"):
            query = "CREATE (n:Table {{"
            query += f"name: '{entity_name}', "
            query += ", ".join([f"{key}: '{value}'" for key, value in props.items()])
            query += "})"
            entities_queries.append(query)

        for relationship_name, relationships in tqdm.tqdm(relationships.items(), "Generating create relationship Cypher queries"):
            for relationship in relationships:
                query = f"""MATCH (a:Table {{ name:{relationship["from"] }}}),
                (b:Table {{ name: {relationship["to"]} }})
                CREATE (a)-[r:REFERENCES]->(b)
                SET r.name = '{relationship_name}'
                """
                relationships_queries.append(query)

        return entities_queries, relationships_queries
