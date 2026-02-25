"""Utility functions for the text2sql API."""
import json
from typing import Dict, List, Optional, TypedDict

from litellm import completion, batch_completion

from api.config import Config


class ForeignKeyInfo(TypedDict):
    """Foreign key constraint information."""
    constraint_name: str
    column: str
    referenced_table: str
    referenced_column: str


class ColumnInfo(TypedDict):
    """Column metadata information."""
    type: str
    null: str
    key: str
    description: str
    default: Optional[str]
    sample_values: List[str]


class TableInfo(TypedDict):
    """Table metadata information."""
    description: str
    columns: Dict[str, ColumnInfo]
    foreign_keys: List[ForeignKeyInfo]
    col_descriptions: List[str]


def create_combined_description(  # pylint: disable=too-many-locals
    table_info: Dict[str, TableInfo], batch_size: int = 10
) -> Dict[str, TableInfo]:
    """
    Create a combined description from a dictionary of table descriptions.

    Args:
        table_info (Dict[str, TableInfo]): Mapping of table names to their metadata.
        batch_size (int): Number of tables to process per batch when calling the LLM (default: 10).
    Returns:
        Dict[str, TableInfo]: Updated mapping containing descriptions.
    """
    if not isinstance(table_info, dict):
        raise TypeError("table_info must be a dictionary keyed by table name.")

    messages_list = []
    table_keys = []

    system_prompt = (
        "You are a database table description generator. "
        "Generate ONE concise sentence starting with the table name, "
        "describing what the table stores, using present tense. "
        "Do not add explanations."
    )

    user_prompt_template = (
        "Table Name: {table_name}\n"
        "Table Schema: {table_prop}\n"
        "Provide a concise description of this table."
    )

    for table_name, table_prop in table_info.items():
        # The col_descriptions property is duplicated in the schema (columns has it)
        table_prop = table_prop.copy()
        table_prop.pop("col_descriptions", None)
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": user_prompt_template.format(
                    table_name=table_name, table_prop=json.dumps(table_prop)
                ),
            },
        ]

        messages_list.append(messages)
        table_keys.append(table_name)

    for batch_start in range(0, len(messages_list), batch_size):
        batch_messages = messages_list[batch_start : batch_start + batch_size]
        response = batch_completion(
            model=Config.COMPLETION_MODEL,
            messages=batch_messages,
            temperature=0,
            max_tokens=50,
        )

        for offset, batch_response in enumerate(response):
            table_index = batch_start + offset
            if table_index >= len(table_keys):
                break
            table_name = table_keys[table_index]
            if isinstance(batch_response, Exception):
                table_info[table_name]["description"] = table_name
            else:
                content = batch_response.choices[0].message["content"].strip()
                table_info[table_name]["description"] = content

    return table_info

def generate_db_description(
    db_name: str,
    table_names: List[str],
    temperature: float = 0.5,
    max_tokens: int = 150,
) -> str:
    """
    Generates a short and concise description of a database.

    Args:
    - database_name (str): The name of the database.
    - table_names (list): A list of table names within the database.
    - temperature (float): Sampling temperature. Higher values mean more creativity (default: 0.5).
    - max_tokens (int): The maximum number of tokens to generate in the response (default: 150).

    Returns:
    - str: A description of the database.
    """
    if not isinstance(db_name, str):
        raise TypeError("database_name must be a string.")

    if not isinstance(table_names, list):
        raise TypeError("table_names must be a list of strings.")

    # Ensure all table names are strings
    if not all(isinstance(table, str) for table in table_names):
        raise ValueError("All items in table_names must be strings.")

    if not table_names:
        return f"{db_name} is a database with no tables."

    # Format the table names appropriately
    if len(table_names) == 1:
        tables_formatted = table_names[0]
    elif len(table_names) == 2:
        tables_formatted = " and ".join(table_names)
    else:
        tables_formatted = ", ".join(table_names[:-1]) + f", and {table_names[-1]}"

    prompt = (
        f"You are a helpful assistant. Generate a concise description of "
        f"the database named '{db_name}' which contains the following tables: "
        f"{tables_formatted}.\n\nDescription:"
    )

    response = completion(
        model=Config.COMPLETION_MODEL,
        messages=[
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
        max_tokens=max_tokens,
        n=1,
        stop=None,
    )
    description = response.choices[0].message["content"]
    return description
