"""Schema validation module for table schemas."""

REQUIRED_COLUMN_KEYS = {"description", "type", "null", "key", "default"}
VALID_NULL_VALUES = {"YES", "NO"}


def validate_table_schema(schema):
    """
    Validate a table schema structure.

    Args:
        schema (dict): The schema dictionary to validate

    Returns:
        list: List of validation errors found
    """
    errors = []

    # Validate top-level database key
    if "database" not in schema or not isinstance(schema["database"], str):
        errors.append("Missing or invalid 'database' key")

    # Validate tables key
    if "tables" not in schema or not isinstance(schema["tables"], dict):
        errors.append("Missing or invalid 'tables' key")
        return errors

    for table_name, table_data in schema["tables"].items():
        errors.extend(_validate_table(table_name, table_data))

    return errors


def _validate_table(table_name, table_data):
    """Validate a single table's structure."""
    errors = []

    if not table_data.get("description"):
        errors.append(f"Table '{table_name}' is missing a description")

    if "columns" not in table_data or not isinstance(table_data["columns"], dict):
        errors.append(f"Table '{table_name}' has no valid 'columns' definition")
        return errors

    for column_name, column_data in table_data["columns"].items():
        errors.extend(_validate_column(table_name, column_name, column_data))

    # Optional: validate foreign keys
    if "foreign_keys" in table_data:
        errors.extend(_validate_foreign_keys(table_name, table_data["foreign_keys"]))

    return errors


def _validate_column(table_name, column_name, column_data):
    """Validate a single column's structure."""
    errors = []

    # Check for missing required keys
    missing_keys = REQUIRED_COLUMN_KEYS - column_data.keys()
    if missing_keys:
        errors.append(
            f"Column '{column_name}' in table '{table_name}' "
            f"is missing keys: {missing_keys}"
        )
        return errors

    # Validate non-empty description
    if not column_data.get("description"):
        errors.append(
            f"Column '{column_name}' in table '{table_name}' has an empty description"
        )

    # Validate 'null' field
    if column_data["null"] not in VALID_NULL_VALUES:
        errors.append(
            f"Column '{column_name}' in table '{table_name}' "
            f"has invalid 'null' value: {column_data['null']}"
        )

    return errors


def _validate_foreign_keys(table_name, foreign_keys):
    """Validate foreign keys structure."""
    errors = []

    if not isinstance(foreign_keys, dict):
        errors.append(
            f"Foreign keys for table '{table_name}' must be a dictionary"
        )
        return errors

    for fk_name, fk_data in foreign_keys.items():
        for key in ("column", "referenced_table", "referenced_column"):
            if key not in fk_data or not fk_data[key]:
                errors.append(
                    f"Foreign key '{fk_name}' in table '{table_name}' is missing '{key}'"
                )

    return errors
