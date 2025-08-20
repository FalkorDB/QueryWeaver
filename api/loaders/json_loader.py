"""JSON loader module for processing JSON schema files."""

import json
from typing import Tuple

import tqdm
from jsonschema import ValidationError

from api.config import Config
from api.loaders.base_loader import BaseLoader
from api.loaders.graph_loader import load_to_graph
from api.loaders.schema_validator import validate_table_schema

try:
    with open(Config.SCHEMA_PATH, "r", encoding="utf-8") as f:
        schema = json.load(f)
except FileNotFoundError as exc:
    raise FileNotFoundError(f"Schema file not found: {Config.SCHEMA_PATH}") from exc
except json.JSONDecodeError as exc:
    raise ValueError(f"Invalid schema JSON: {str(exc)}") from exc


class JSONLoader(BaseLoader):
    """JSON schema loader for loading database schemas from JSON files."""

    @staticmethod
    async def load(graph_id: str, data) -> Tuple[bool, str]:
        """
        Load the graph data into the database.
        It gets the Graph name as an argument and expects
        a JSON payload with the following structure: txt2sql/schema_schema.json
        """

        # Validate the JSON with the schema should return a bad request if the payload is not valid
        try:
            validation_errors = validate_table_schema(data)
            if not validation_errors:
                print("✅ Schema is valid.")
            else:
                print("❌ Schema validation failed with the following issues:")
                for error in validation_errors:
                    print(f" - {error}")
                raise ValidationError(
                    "Schema validation failed. Please check the schema and try again."
                )

        except ValidationError as exc:
            return False, str(exc)

        relationships = {}
        for table_name, table_info in tqdm.tqdm(
            data["tables"].items(), "Create Table relationships"
        ):
            # Create Foreign Key relationships
            for fk_name, fk_info in tqdm.tqdm(
                table_info["foreign_keys"].items(), "Create Foreign Key relationships"
            ):
                if table_name not in relationships:
                    relationships[table_name] = []
                relationships[table_name].append(
                    {
                        "from": table_name,
                        "to": fk_info["referenced_table"],
                        "source_column": fk_info["column"],
                        "target_column": fk_info["referenced_column"],
                        "note": fk_name,
                    }
                )
        await load_to_graph(graph_id, data["tables"], relationships, db_name=data["database"])

        return True, "Graph loaded successfully"
