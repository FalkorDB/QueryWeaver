import json
import os
import time
import requests
from typing import Dict, List, Any, Optional
from litellm import completion, validate_environment, utils as litellm_utils

OUTPUT_FILE = "complete_crm_schema.json"
MAX_RETRIES = 3
RETRY_DELAY = 5  # seconds

# Initialize the schema with the base structure
schema = {
    "database": "crm_system",
    "tables": {}
}

def load_initial_schema(file_path: str) -> Dict[str, Any]:
    """Load the initial schema file with table names"""
    try:
        with open(file_path, 'r') as file:
            return json.load(file)
    except Exception as e:
        print(f"Error loading schema file: {e}")
        return {"database": "crm_system", "tables": {}}

def save_schema(schema: Dict[str, Any], output_file: str = OUTPUT_FILE) -> None:
    """Save the current schema to a file"""
    with open(output_file, 'w') as file:
        json.dump(schema, file, indent=2)
    print(f"Schema saved to {output_file}")

def find_related_tables(table_name: str, all_tables: List[str]) -> List[str]:
    """Find tables that might be related to the current table based on naming patterns"""
    related = []
    
    # Extract base name by removing common prefixes/suffixes
    base_parts = table_name.split('_')
    
    for other_table in all_tables:
        if other_table == table_name:
            continue
            
        # Direct naming relationship (e.g., contacts and contact_addresses)
        if table_name in other_table or other_table in table_name:
            related.append(other_table)
            continue
            
        # Check for common roots
        other_parts = other_table.split('_')
        for part in base_parts:
            if part in other_parts and len(part) > 3:  # Avoid short common words
                related.append(other_table)
                break
    
    return related

def get_table_prompt(table_name: str, existing_tables: Dict[str, Any], all_table_names: List[str]) -> str:
    """Generate a detailed prompt for the LLM to create a table schema matching the example"""
    
    # Identify potentially related tables
    related_tables = find_related_tables(table_name, all_table_names)
    related_tables_str = ", ".join(related_tables) if related_tables else "None identified yet"
    
    # Include the contacts table as an example format
    contacts_example = """
{
  "contacts": {
    "description": "Stores information about individual contacts within the CRM system, including personal details and relationship to companies.",
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
    
    # Include examples of other completed tables if available
    additional_examples = ""
    example_count = 0
    for table, details in existing_tables.items():
        if (isinstance(details, dict) and 'columns' in details and 
            'indexes' in details and 'foreign_keys' in details and 
            table != "contacts" and example_count < 1):
            additional_examples += f"\nAnother example table:\n```json\n{json.dumps({table: details}, indent=2)}\n```\n"
            example_count += 1
    
    # Create a context-specific description based on the table name
    table_context = get_table_context(table_name, related_tables)
    
    prompt = f"""
You are an expert database architect specializing in CRM systems. Create a detailed JSON schema for the '{table_name}' table in our CRM database.

CONTEXT ABOUT THIS TABLE:
{table_context}

POTENTIALLY RELATED TABLES:
{related_tables_str}

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

EXACTLY FOLLOW THIS FORMAT from our contacts table:
```json
{contacts_example}
```
{additional_examples}

IMPORTANT GUIDELINES:
- Always include standard timestamps (created_date, updated_date) for all tables
- All tables should have a primary key with auto_increment
- Follow proper MySQL data type conventions
- Include appropriate indexes for performance
- Define foreign keys wherever relations exist
- Every column needs a description, type, null status
- All names should follow snake_case convention

Return ONLY valid JSON for the '{table_name}' table structure without any explanation or additional text:
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
    words = table_name.replace('_', ' ').split()
    
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
        "campaign": "Contains information about marketing campaigns"
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
        "settings": "This contains configuration settings"
    }
    
    context = f"The '{table_name}' table appears to be "
    
    # Check if this is a junction/linking table
    if "_" in table_name and not any(p in table_name for p in relationship_patterns.keys()):
        parts = table_name.split("_")
        if len(parts) == 2 and all(len(p) > 2 for p in parts):
            return f"This appears to be a junction table linking '{parts[0]}' and '{parts[1]}', likely with a many-to-many relationship."
    
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
        context += f"It appears to be related to the following tables: {', '.join(related_tables)}. "
        
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
            config['temperature'] = 0.5
            config['response_format'] = { "type": "json_object" }
        
            
            response = completion(
                model="gemini/gemini-2.0-flash",
                messages=[{"role": "user", "content": prompt}],
                **config
            )
            result = response.json().get("choices", [{}])[0].get("message", "").get("content", "").strip()
            if result:
                return result
            else:
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
        response = response.replace('\n', ' ').replace('\r', ' ')
        
        # Cleanup any trailing/leading text
        start_idx = response.find('{')
        end_idx = response.rfind('}') + 1
        if start_idx >= 0 and end_idx > start_idx:
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
            else:
                missing = [key for key in required_keys if key not in table_data]
                print(f"Warning: Table schema missing required sections: {missing}")
                return {table_name: table_data}  # Return anyway, but with warning
        else:
            # Try to get the first key if table_name is not found
            first_key = next(iter(parsed))
            print(f"Warning: Table name mismatch. Expected {table_name}, got {first_key}")
            return {table_name: parsed[first_key]}
    except Exception as e:
        print(f"Error parsing LLM response for {table_name}: {e}")
        print(f"Raw response: {response[:500]}...")  # Show first 500 chars
        return None

def process_table(table_name: str, schema: Dict[str, Any], all_table_names: List[str]) -> Dict[str, Any]:
    """Process a single table and update the schema"""
    print(f"Processing table: {table_name}")
    
    # Skip if table already has detailed schema
    if (table_name in schema["tables"] and 
        isinstance(schema["tables"][table_name], dict) and 
        "columns" in schema["tables"][table_name] and
        "indexes" in schema["tables"][table_name] and
        "foreign_keys" in schema["tables"][table_name]):
        print(f"Table {table_name} already processed. Skipping.")
        return schema
    
    # Generate prompt for this table
    prompt = get_table_prompt(table_name, schema["tables"], all_table_names)
    
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
    # Load the initial schema with table names
    initial_schema_path = "examples/crm_tables.json"  # Replace with your actual file path
    initial_schema = load_initial_schema(initial_schema_path)
    
    # Get the list of tables to process
    tables = list(initial_schema.get("tables", {}).keys())
    all_table_names = tables.copy()  # Keep a full list for reference
    
    # Initialize our working schema
    schema = {
        "database": initial_schema.get("database", "crm_system"),
        "tables": {}
    }
    
    # If we have existing work, load it
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, 'r') as file:
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
        print(f"\nProcessing table {i+1}/{len(tables)}: {table_name} (Priority: {table_priority(table_name)})")
        schema = process_table(table_name, schema, all_table_names)
        
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

def validate_schema(schema: Dict[str, Any]) -> None:
    """Perform final validation on the complete schema"""
    print("\nValidating schema...")
    issues = []
    
    table_count = len(schema["tables"])
    tables_with_columns = sum(1 for t in schema["tables"].values() 
                             if isinstance(t, dict) and "columns" in t)
    tables_with_indexes = sum(1 for t in schema["tables"].values() 
                             if isinstance(t, dict) and "indexes" in t)
    tables_with_foreign_keys = sum(1 for t in schema["tables"].values() 
                                  if isinstance(t, dict) and "foreign_keys" in t)
    
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
                    invalid_fks.append(f"{table_name}.{fk_name} -> {ref_table}.{ref_column} (column not found)")
    
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