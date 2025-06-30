"""
CRM data generator module for creating complete database schemas with relationships.

This module provides functionality to generate comprehensive CRM database schemas
with proper primary/foreign key relationships and table structures.
"""

import json
import os
import time
from typing import Any, Dict, List, Optional

import requests
from litellm import completion

OUTPUT_FILE = "complete_crm_schema.json"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Global registry to track primary and foreign keys across tables
key_registry = {
    "primary_keys": {},  # table_name -> primary_key_column
    "foreign_keys": {},  # table_name -> {column_name -> (referenced_table, referenced_column)}
    "processed_tables": set(),  # Set of tables that have been processed
    "table_relationships": {},  # table_name -> set of related tables
}


def load_initial_schema(file_path: str) -> Dict[str, Any]:
    """Load the initial schema file with table names"""
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            schema = json.load(file)
            print(f"Loaded initial schema with {len(schema.get('tables', {}))} tables")
            return schema
    except Exception as e:
        print(f"Error loading schema file: {e}")
        return {"database": "crm_system", "tables": {}}


def save_schema(schema: Dict[str, Any], output_file: str = OUTPUT_FILE) -> None:
    """Save the current schema to a file with metadata"""
    # Add metadata
    if "metadata" not in schema:
        schema["metadata"] = {}

    schema["metadata"]["last_updated"] = time.strftime("%Y-%m-%d %H:%M:%S")
    schema["metadata"]["completed_tables"] = len(key_registry["processed_tables"])
    schema["metadata"]["total_tables"] = len(schema.get("tables", {}))
    schema["metadata"]["key_registry"] = {
        "primary_keys": key_registry["primary_keys"],
        "foreign_keys": key_registry["foreign_keys"],
        "table_relationships": {k: list(v) for k, v in key_registry["table_relationships"].items()},
    }

    with open(output_file, "w", encoding="utf-8") as file:
        json.dump(schema, file, indent=2)
    print(f"Schema saved to {output_file}")


def update_key_registry(table_name: str, table_data: Dict[str, Any]) -> None:
    """Update the key registry with information from a processed table"""
    # Mark table as processed
    key_registry["processed_tables"].add(table_name)

    # Track primary keys
    if "columns" in table_data:
        for col_name, col_data in table_data["columns"].items():
            if col_data.get("key") == "PRI":
                key_registry["primary_keys"][table_name] = col_name
                break

    # Track foreign keys and relationships
    if "foreign_keys" in table_data:
        if table_name not in key_registry["foreign_keys"]:
            key_registry["foreign_keys"][table_name] = {}

        if table_name not in key_registry["table_relationships"]:
            key_registry["table_relationships"][table_name] = set()

        for fk_data in table_data["foreign_keys"].values():
            column = fk_data.get("column")
            ref_table = fk_data.get("referenced_table")
            ref_column = fk_data.get("referenced_column")

            if column and ref_table and ref_column:
                key_registry["foreign_keys"][table_name][column] = (
                    ref_table,
                    ref_column,
                )

                # Update relationships
                key_registry["table_relationships"][table_name].add(ref_table)

                # Ensure the referenced table has an entry
                if ref_table not in key_registry["table_relationships"]:
                    key_registry["table_relationships"][ref_table] = set()

                # Add the reverse relationship
                key_registry["table_relationships"][ref_table].add(table_name)


def find_related_tables(table_name: str, all_tables: List[str]) -> List[str]:
    """Find tables that might be related to the current table"""
    related = []

    # Check registry first for already established relationships
    if table_name in key_registry["table_relationships"]:
        related.extend(key_registry["table_relationships"][table_name])

    # Extract base name
    base_parts = table_name.split("_")

    for other_table in all_tables:
        if other_table == table_name or other_table in related:
            continue

        # Direct naming relationship
        if table_name in other_table or other_table in table_name:
            related.append(other_table)
            continue

        # Check for common roots
        other_parts = other_table.split("_")
        for part in base_parts:
            if part in other_parts and len(part) > 3:  # Avoid short common words
                related.append(other_table)
                break

    return list(set(related))  # Remove duplicates


def get_table_prompt(
    table_name: str, schema: Dict[str, Any], all_table_names: List[str], topology
) -> str:
    """Generate a prompt for the LLM to create a table schema with proper relationships"""
    existing_tables = schema.get("tables", {})

    # Find related tables
    related_tables = find_related_tables(table_name, all_table_names)
    related_tables_str = ", ".join(related_tables) if related_tables else "None identified yet"

    # # Suggest primary key pattern
    # table_base = table_name.split("_")[0] if "_" in table_name else table_name
    # suggested_pk = f"{table_name}_id"  # Default pattern

    # # Check if related tables have primary keys to follow same pattern
    # for related in related_tables:
    #     if related in key_registry["primary_keys"]:
    #         related_pk = key_registry["primary_keys"][related]
    #         if related_pk.endswith("_id") and related in related_pk:
    #             # Follow the same pattern
    #             suggested_pk = f"{table_name}_id"
    #             break

    # Prepare foreign key suggestions
    fk_suggestions = []
    for related in related_tables:
        if related in key_registry["primary_keys"]:
            fk_suggestions.append(
                {
                    "column": f"{related}_id",
                    "referenced_table": related,
                    "referenced_column": key_registry["primary_keys"][related],
                }
            )

    fk_suggestions_str = ""
    if fk_suggestions:
        fk_suggestions_str = "Consider these foreign key relationships:\n"
        for i, fk in enumerate(fk_suggestions[:5]):  # Limit to 5 suggestions
            fk_suggestions_str += (
                f"{i+1}. {fk['column']} -> {fk['referenced_table']}.{fk['referenced_column']}\n"
            )

    # Include examples of related tables that have been processed
    related_examples = ""
    example_count = 0
    for related in related_tables:
        if (
            related in existing_tables
            and isinstance(existing_tables[related], dict)
            and "columns" in existing_tables[related]
            and example_count < 2
        ):
            related_examples += (
                f"\nRelated table example:\n```json\n"
                f"{json.dumps({related: existing_tables[related]}, indent=2)}\n```\n"
            )
            example_count += 1

    # Use contacts table as primary example if no related examples found
    contacts_example = """
{
  "contacts": {
    "description": ("Stores information about individual contacts within the CRM "
                   "system, including personal details and relationship to companies."),
    "columns": {
      "contact_id": {
        "description": "Unique identifier for each contact",
        "type": "int(11)",
        "null": "NO",
        "key": "PRI",
        "default": null,
        "extra": "auto_increment"
      },
      "first_name": {
        "description": "Contact's first name",
        "type": "varchar(50)",
        "null": "NO",
        "key": "",
        "default": null,
        "extra": ""
      },
      "email": {
        "description": "Contact's primary email address",
        "type": "varchar(100)",
        "null": "NO",
        "key": "UNI",
        "default": null,
        "extra": ""
      },
      "company_id": {
        "description": "Foreign key to the companies table",
        "type": "int(11)",
        "null": "YES",
        "key": "MUL",
        "default": null,
        "extra": ""
      },
      "created_date": {
        "description": "Date and time when the contact was created",
        "type": "timestamp",
        "null": "NO",
        "key": "",
        "default": "CURRENT_TIMESTAMP",
        "extra": ""
      },
      "updated_date": {
        "description": "Date and time when the contact was last updated",
        "type": "timestamp",
        "null": "YES",
        "key": "",
        "default": null,
        "extra": "on update CURRENT_TIMESTAMP"
      }
    },
    "indexes": {
      "PRIMARY": {
        "columns": [
          {
            "name": "contact_id",
            "sub_part": null,
            "seq_in_index": 1
          }
        ],
        "unique": true,
        "type": "BTREE"
      },
      "email_unique": {
        "columns": [
          {
            "name": "email",
            "sub_part": null,
            "seq_in_index": 1
          }
        ],
        "unique": true,
        "type": "BTREE"
      },
      "company_id_index": {
        "columns": [
          {
            "name": "company_id",
            "sub_part": null,
            "seq_in_index": 1
          }
        ],
        "unique": false,
        "type": "BTREE"
      }
    },
    "foreign_keys": {
      "fk_contacts_company": {
        "column": "company_id",
        "referenced_table": "companies",
        "referenced_column": "company_id"
      }
    }
  }
}
"""
    # Create context about the table's purpose
    table_context = get_table_context(table_name, related_tables)
    keys = json.dumps(topology["tables"][table_name])
    prompt = f"""
You are an expert database architect specializing in CRM systems. Create a detailed 
JSON schema for the '{table_name}' table in our CRM database.

CONTEXT ABOUT THIS TABLE:
{table_context}

POTENTIALLY RELATED TABLES:
{related_tables_str}

The primary Key and the foreign keys (topology) for this table should include the following:
{keys}

{fk_suggestions_str}

Your response must include:
1. A comprehensive description of the table's purpose
2. All relevant columns with:
   - Detailed descriptions 
   - Appropriate MySQL data types
   - NULL/NOT NULL constraints
   - Key designations (PRI, UNI, MUL, etc.)
   - Default values
   - Extra properties (auto_increment, on update, etc.)
3. All necessary indexes including:
   - Primary key index
   - Unique constraints
   - Foreign key indexes
   - Other performance indexes
4. All foreign key relationships with:
   - Constraint names
   - Referenced tables and columns
5. Ensure that you using the exact keys from the topology, PK is for primary key and FK is for foreign key.

EXACTLY FOLLOW THIS FORMAT from our contacts table:
```json
{contacts_example}
```
{related_examples}

IMPORTANT GUIDELINES:
- Always include standard timestamps (created_date, updated_date) for all tables
- All tables should have a primary key with auto_increment
- Follow proper MySQL data type conventions
- Include appropriate indexes for performance
- Every column needs a description, type, null status
- All names should follow snake_case convention
- For many-to-many relationships, create appropriate junction tables
- Ensure referential integrity with foreign key constraints

Return ONLY valid JSON for the '{table_name}' table structure without any
explanation or additional text:
{{
  "{table_name}": {{
    "description": "...",
    "columns": {{...}},
    "indexes": {{...}},
    "foreign_keys": {{...}}
  }}
}}
"""
    return prompt


def get_table_context(table_name: str, related_tables: List[str]) -> str:
    """Generate contextual information about a table based on its name and related tables"""
    # Extract words from table name
    words = table_name.replace("_", " ").split()

    # Common CRM entities
    entities = {
        "contact": "Contains information about individuals",
        "company": "Contains information about organizations/businesses",
        "lead": "Represents potential customers or sales opportunities",
        "opportunity": "Represents qualified sales opportunities",
        "deal": "Represents sales deals in progress or completed",
        "task": "Represents activities or to-do items",
        "meeting": "Contains information about scheduled meetings",
        "call": "Contains information about phone calls",
        "email": "Contains information about email communication",
        "user": "Contains information about CRM system users",
        "product": "Contains information about products or services",
        "quote": "Contains information about price quotes",
        "invoice": "Contains information about invoices",
        "order": "Contains information about customer orders",
        "subscription": "Contains information about recurring subscriptions",
        "ticket": "Contains information about support tickets",
        "campaign": "Contains information about marketing campaigns",
    }

    # Common relationship patterns
    relationship_patterns = {
        "tags": "This is a tagging or categorization table that likely links to various entities",
        "notes": "This contains notes or comments associated with other entities",
        "addresses": "This contains address information associated with other entities",
        "preferences": "This contains preference settings associated with other entities",
        "relationships": "This defines relationships between entities",
        "social": "This contains social media information",
        "assignments": "This tracks assignment of entities to users",
        "sources": "This tracks where entities originated from",
        "statuses": "This defines possible status values for entities",
        "types": "This defines type categories for entities",
        "stages": "This defines stage progression for entities",
        "logs": "This tracks history or logs of activities",
        "attachments": "This contains file attachments",
        "performance": "This tracks performance metrics",
        "feedback": "This contains feedback information",
        "settings": "This contains configuration settings",
    }

    context = f"The '{table_name}' table appears to be "

    # Check if this is a junction/linking table
    if "_" in table_name and not any(p in table_name for p in relationship_patterns):
        parts = table_name.split("_")
        if len(parts) == 2 and all(len(p) > 2 for p in parts):
            return (f"This appears to be a junction table linking '{parts[0]}' and "
                   f"'{parts[1]}', likely with a many-to-many relationship.")

    # Check for main entities
    for entity, description in entities.items():
        if entity in words:
            context += f"{description}. "
            break
    else:
        context += "part of the CRM system. "

    # Check for relationship patterns
    for pattern, description in relationship_patterns.items():
        if pattern in table_name:
            context += f"{description}. "
            break

    # Add related tables info
    if related_tables:
        context += (
            f"It appears to be related to the following tables: {', '.join(related_tables)}. "
        )

        # Guess if it's a child table
        for related in related_tables:
            if related in table_name and len(related) < len(table_name):
                context += f"It may be a child or detail table for the {related} table. "
                break

    return context


def call_llm_api(prompt: str, retries: int = MAX_RETRIES) -> Optional[str]:
    """Call the LLM API with the given prompt, with retry logic"""
    for attempt in range(1, retries + 1):
        try:
            config = {}
            config["temperature"] = 0.5
            config["response_format"] = {"type": "json_object"}

            response = completion(
                model="gemini/gemini-2.0-flash",
                messages=[{"role": "user", "content": prompt}],
                **config,
            )
            result = (
                response.json()
                .get("choices", [{}])[0]
                .get("message", "")
                .get("content", "")
                .strip()
            )
            if result:
                return result

            print(f"Empty response from API (attempt {attempt}/{retries})")

        except requests.exceptions.RequestException as e:
            print(f"API request error (attempt {attempt}/{retries}): {e}")

        if attempt < retries:
            sleep_time = RETRY_DELAY * attempt
            print(f"Retrying in {sleep_time} seconds...")
            time.sleep(sleep_time)

    print("All retry attempts failed")
    return None


def parse_llm_response(response: str, table_name: str) -> Optional[Dict[str, Any]]:
    """Parse the LLM response and extract the table schema with validation"""
    try:
        # Extract JSON from response if needed
        if "```json" in response:
            response = response.split("```json")[1].split("```")[0].strip()
        elif "```" in response:
            response = response.split("```")[1].strip()

        # Handle common formatting issues
        response = response.replace("\n", " ").replace("\r", " ")

        # Cleanup any trailing/leading text
        start_idx = response.find("{")
        end_idx = response.rfind("}") + 1
        if 0 <= start_idx < end_idx:
            response = response[start_idx:end_idx]

        parsed = json.loads(response)

        # Validation of required components
        if table_name in parsed:
            table_data = parsed[table_name]
            required_keys = ["description", "columns", "indexes", "foreign_keys"]

            # Check if all required sections exist
            if all(key in table_data for key in required_keys):
                # Verify columns have required attributes
                for col_name, col_data in table_data["columns"].items():
                    required_col_attrs = ["description", "type", "null"]
                    if not all(attr in col_data for attr in required_col_attrs):
                        print(f"Warning: Column {col_name} is missing required attributes")

                return {table_name: table_data}

            missing = [key for key in required_keys if key not in table_data]
            print(f"Warning: Table schema missing required sections: {missing}")
            return {table_name: table_data}  # Return anyway, but with warning

        # Try to get the first key if table_name is not found
        first_key = next(iter(parsed))
        print(f"Warning: Table name mismatch. Expected {table_name}, got {first_key}")
        return {table_name: parsed[first_key]}
    except Exception as e:
        print(f"Error parsing LLM response for {table_name}: {e}")
        print(f"Raw response: {response[:500]}...")  # Show first 500 chars
        return None


def process_table(
    table_name: str, schema: Dict[str, Any], all_table_names: List[str], topology
) -> Dict[str, Any]:
    """Process a single table and update the schema"""
    print(f"Processing table: {table_name}")

    # Skip if table already has detailed schema
    if (
        table_name in schema["tables"]
        and isinstance(schema["tables"][table_name], dict)
        and "columns" in schema["tables"][table_name]
        and "indexes" in schema["tables"][table_name]
        and "foreign_keys" in schema["tables"][table_name]
    ):
        print(f"Table {table_name} already processed. Skipping.")
        return schema

    # Generate prompt for this table
    prompt = get_table_prompt(table_name, schema["tables"], all_table_names, topology)

    # Call LLM API
    response = call_llm_api(prompt)
    if not response:
        print(f"Failed to get response for {table_name}. Skipping.")
        return schema

    # Parse response
    table_schema = parse_llm_response(response, table_name)
    if not table_schema:
        print(f"Failed to parse response for {table_name}. Skipping.")
        return schema

    # Update schema
    schema["tables"].update(table_schema)
    print(f"Successfully processed {table_name}")

    # Save intermediate results
    save_schema(schema, f"intermediate_{table_name.replace('/', '_')}.json")

    return schema


def main():
    """Main function to generate complete CRM schema with relationships."""
    # Load the initial schema with table names
    initial_schema_path = "examples/crm_tables.json"  # Replace with your actual file path
    initial_schema = load_initial_schema(initial_schema_path)

    # Get the list of tables to process
    tables = list(initial_schema.get("tables", {}).keys())
    all_table_names = tables.copy()  # Keep a full list for reference

    topology = generate_keys(tables)

    # Initialize our working schema
    schema = {"database": initial_schema.get("database", "crm_system"), "tables": {}}

    # If we have existing work, load it
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as file:
                schema = json.load(file)
            print(f"Loaded existing schema from {OUTPUT_FILE}")
        except Exception as e:
            print(f"Error loading existing schema: {e}")

    # Prioritize tables to process - process base tables first
    def table_priority(table_name):
        # Base tables should be processed first
        if "_" not in table_name:
            return 0
        # Junction tables last
        if table_name.count("_") > 1:
            return 2
        # Related tables in the middle
        return 1

    # Sort tables by priority
    tables.sort(key=table_priority)

    # Process tables
    for i, table_name in enumerate(tables):
        print(
            f"\nProcessing table {i+1}/{len(tables)}: {table_name} "
            f"(Priority: {table_priority(table_name)})"
        )
        schema = process_table(table_name, schema, all_table_names, topology)

        # Save progress after each table
        save_schema(schema)

        # Add delay to avoid rate limits
        if i < len(tables) - 1:
            delay = 2 + (0.5 * i % 5)  # Varied delay to help avoid pattern detection
            print(f"Waiting {delay} seconds before next request...")
            time.sleep(delay)

    print(f"\nCompleted processing all {len(tables)} tables")
    print(f"Final schema saved to {OUTPUT_FILE}")

    # Validate the final schema
    validate_schema(schema)


def generate_keys(tables) -> Dict[str, Any]:
    """Generate primary and foreign keys for CRM tables."""
    path = "examples/crm_topology.json"
    last_key = 0  # Initialize default value
    schema = {"tables": {}}  # Initialize default schema

    # If we have existing work, load it
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as file:
                schema = json.load(file)
            if schema.get("tables"):
                last_key = tables.index(list(schema["tables"].keys())[-1])
            print(f"Loaded existing schema from {path}")
        except Exception as e:
            print(f"Error loading existing schema: {e}")
            last_key = 0

    prompt = """
    You are an expert database architect specializing in CRM systems. Create a detailed JSON schema for the '{table_name}' table in our CRM database.
    The all tables are:
    {tables}

    Please genereate the primary key and foreign key for the table in the following json format:
    "contacts": {{
        "contact_id": "PK",
        "company_id": "FK",
        "user_id": "FK",
        "lead_id": "FK"
      }},
    

    Only generate the primery key and the foreign keys based on you knowledge on crm databases in the above schema.
    Your output for the table '{table_name}':
    """
    for table in tables[last_key:]:

        p = prompt.format(table_name=table, tables=tables)
        response = call_llm_api(p)
        new_table = json.loads(response)
        schema["tables"].update(new_table)

    with open(path, "w", encoding="utf-8") as file:
        json.dump(schema, file, indent=2)
    print(f"Schema saved to {path}")
    print(f"Final schema saved to {path}")

    return schema


def validate_schema(schema: Dict[str, Any]) -> None:
    """Perform final validation on the complete schema"""
    print("\nValidating schema...")
    issues = []

    table_count = len(schema["tables"])
    tables_with_columns = sum(
        1 for t in schema["tables"].values() if isinstance(t, dict) and "columns" in t
    )
    tables_with_indexes = sum(
        1 for t in schema["tables"].values() if isinstance(t, dict) and "indexes" in t
    )
    tables_with_foreign_keys = sum(
        1 for t in schema["tables"].values() if isinstance(t, dict) and "foreign_keys" in t
    )

    print(f"Total tables: {table_count}")
    print(f"Tables with columns: {tables_with_columns}")
    print(f"Tables with indexes: {tables_with_indexes}")
    print(f"Tables with foreign keys: {tables_with_foreign_keys}")

    # Check if all tables have required sections
    incomplete_tables = []
    for table_name, table_data in schema["tables"].items():
        if not isinstance(table_data, dict):
            incomplete_tables.append(f"{table_name} (empty)")
            continue

        missing = []
        if "description" not in table_data or not table_data["description"]:
            missing.append("description")
        if "columns" not in table_data or not table_data["columns"]:
            missing.append("columns")
        if "indexes" not in table_data or not table_data["indexes"]:
            missing.append("indexes")
        if "foreign_keys" not in table_data:  # Can be empty, just needs to exist
            missing.append("foreign_keys")

        if missing:
            incomplete_tables.append(f"{table_name} (missing: {', '.join(missing)})")

    if incomplete_tables:
        issues.append(f"Incomplete tables: {len(incomplete_tables)}")
        print("Incomplete tables:")
        for table in incomplete_tables[:10]:  # Show first 10
            print(f"  - {table}")
        if len(incomplete_tables) > 10:
            print(f"  ... and {len(incomplete_tables) - 10} more")

    # Check foreign key references
    invalid_fks = []
    for table_name, table_data in schema["tables"].items():
        if not isinstance(table_data, dict) or "foreign_keys" not in table_data:
            continue

        for fk_name, fk_data in table_data["foreign_keys"].items():
            ref_table = fk_data.get("referenced_table")
            ref_column = fk_data.get("referenced_column")

            if ref_table and ref_table not in schema["tables"]:
                invalid_fks.append(f"{table_name}.{fk_name} -> {ref_table} (table not found)")
            elif ref_table and ref_column:
                ref_table_data = schema["tables"].get(ref_table, {})
                if not isinstance(ref_table_data, dict) or "columns" not in ref_table_data:
                    invalid_fks.append(f"{table_name}.{fk_name} -> {ref_table} (no columns)")
                elif ref_column not in ref_table_data.get("columns", {}):
                    invalid_fks.append(
                        f"{table_name}.{fk_name} -> {ref_table}.{ref_column} (column not found)"
                    )

    if invalid_fks:
        issues.append(f"Invalid foreign keys: {len(invalid_fks)}")
        print("Invalid foreign keys:")
        for fk in invalid_fks[:10]:  # Show first 10
            print(f"  - {fk}")
        if len(invalid_fks) > 10:
            print(f"  ... and {len(invalid_fks) - 10} more")

    if issues:
        print(f"\nValidation complete. Found {len(issues)} issue types.")
    else:
        print("\nValidation complete. No issues found!")


if __name__ == "__main__":
    main()
