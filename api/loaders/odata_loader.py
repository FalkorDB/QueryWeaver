import re
import xml.etree.ElementTree as ET
from typing import Tuple

import tqdm

from api.loaders.base_loader import BaseLoader
from api.loaders.graph_loader import load_to_graph


class ODataLoader(BaseLoader):
    """
    This class is responsible for loading OData schemas into a Graph.
    """

    @staticmethod
    async def load(graph_id: str, data) -> Tuple[bool, str]:
        """Load XML ODATA schema into a Graph."""

        try:
            # Parse the OData schema
            entities, relationships = ODataLoader._parse_odata_schema(data)
        except ET.ParseError:
            return False, "Invalid XML content"

        await load_to_graph(graph_id, entities, relationships, db_name="ERP system")

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
            "edmx": "http://docs.oasis-open.org/odata/ns/edmx",
            "edm": "http://docs.oasis-open.org/odata/ns/edm",
        }

        schema_element = root.find(".//edmx:DataServices/edm:Schema", namespaces)
        if schema_element is None:
            raise ET.ParseError("Schema element not found")

        entity_types = schema_element.findall("edm:EntityType", namespaces)
        for entity_type in tqdm.tqdm(entity_types, "Parsing OData schema"):
            entity_name = entity_type.get("Name")
            entities[entity_name] = {"col_descriptions": []}
            entities[entity_name]["columns"] = {}
            for prop in entity_type.findall("edm:Property", namespaces):
                prop_name = prop.get("Name")
                try:
                    if prop_name is not None:
                        entities[entity_name]["columns"][prop_name] = {}
                        entities[entity_name]["columns"][prop_name]["type"] = prop.get(
                            "Type"
                        ).split(".")[-1]
                        col_des = entity_name
                        if len(prop.findall("edm:Annotation", namespaces)) > 0:
                            if len(prop.findall("edm:Annotation", namespaces)[0].get("String")) > 0:
                                col_des = prop.findall("edm:Annotation", namespaces)[0].get(
                                    "String"
                                )
                        entities[entity_name]["col_descriptions"].append(col_des)
                        entities[entity_name]["columns"][prop_name]["description"] = col_des
                except Exception as e:
                    print(f"Error parsing property {prop_name} for entity {entity_name}")
                    continue

            #  = {prop.get("Name"): prop.get("Type") \
            #     for prop in entity_type.findall("edm:Property", namespaces)}
            description = entity_type.findall("edm:Annotation", namespaces)
            if len(description) > 0:
                entities[entity_name]["description"] = (
                    description[0].get("String").replace("'", "\\'")
                )
            else:
                try:
                    entities[entity_name]["description"] = (
                        entity_name
                        + " with Primery key: "
                        + entity_type.find("edm:Key/edm:PropertyRef", namespaces).attrib["Name"]
                    )
                except:
                    print(f"Error parsing description for entity {entity_name}")
                    entities[entity_name]["description"] = entity_name

        for entity_type in tqdm.tqdm(entity_types, "Parsing OData schema - relationships"):

            entity_name = entity_type.attrib["Name"]

            for rel in entity_type.findall("edm:NavigationProperty", namespaces):
                rel_name = rel.get("Name")
                raw_type = rel.get("Type")  # e.g., 'Collection(Priority.OData.ABILITYVALUES)'

                # Clean 'Collection(...)' wrapper if exists
                if raw_type.startswith("Collection(") and raw_type.endswith(")"):
                    raw_type = raw_type[len("Collection(") : -1]

                # Extract the target entity name
                match = re.search(r"(\w+)$", raw_type)
                target_entity = match.group(1) if match else "UNKNOWN"

                source_entity = entity_name
                target_entity = target_entity
                source_fields = entities.get(entity_name, {})["columns"]
                target_fields = entities.get(target_entity, {})["columns"]

                # TODO This usage is for demonstration purposes only, it should be \
                # replaced with a more robust method
                source_col, target_col = guess_relationship_columns(source_fields, target_fields)
                if source_col and target_col:
                    # Store the relationship
                    if rel_name not in relationships:
                        relationships[rel_name] = []
                    # src_col, tgt_col = guess_relationship_columns(source_entity, \
                    #     target_entity, entities[source_entity], entities[target_entity])
                    relationships[rel_name].append(
                        {
                            "from": source_entity,
                            "to": target_entity,
                            "source_column": source_col,
                            "target_column": target_col,
                            "note": (
                                "inferred" if source_col and target_col else "implicit/subform"
                            ),
                        }
                    )

        return entities, relationships


# TODO: this funtion is for demonstration purposes only, it should be \
# replaced with a more robust method
def guess_relationship_columns(source_fields, target_fields):
    for src_key, src_meta in source_fields.items():
        if src_key == "description":
            continue
        for tgt_key, tgt_meta in target_fields.items():
            if tgt_key == "description":
                continue
            # Heuristic: same type and similar name
            if src_meta["type"] == tgt_meta["type"] and (
                src_key.lower() in tgt_key.lower() or tgt_key.lower() in src_key.lower()
            ):
                return src_key, tgt_key
    return None, None
