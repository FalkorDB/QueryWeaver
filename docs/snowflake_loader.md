# Snowflake Loader

This document describes the Snowflake loader implementation in QueryWeaver.

## Overview

The Snowflake loader enables QueryWeaver to connect to Snowflake databases, extract schema information (tables, columns, foreign keys, relationships), and load it into a graph structure for Text2SQL queries.

## Connection URL Format

To connect to a Snowflake database, use the following URL format:

```
snowflake://username:password@account/database/schema?warehouse=warehouse_name
```

### URL Components

- **username**: Your Snowflake username
- **password**: Your Snowflake password (optional, can be empty)
- **account**: Your Snowflake account identifier (e.g., `myorg-myaccount`)
- **database**: The database name to connect to (required)
- **schema**: The schema name (optional, defaults to `PUBLIC`)
- **warehouse**: The warehouse name (optional, defaults to `COMPUTE_WH`)

### Examples

Full URL with all parameters:
```
snowflake://john:mypass123@myorg-account/SALES_DB/PUBLIC?warehouse=COMPUTE_WH
```

Minimal URL (using defaults):
```
snowflake://john:mypass123@myorg-account/SALES_DB
```

URL without password:
```
snowflake://john@myorg-account/SALES_DB/PUBLIC?warehouse=ANALYTICS_WH
```

## Features

The Snowflake loader provides the following features:

### 1. Schema Extraction
- Extracts all tables in the specified schema
- Retrieves column information including data types, nullability, defaults, and comments
- Identifies primary keys and foreign keys
- Extracts table and column comments

### 2. Relationship Mapping
- Discovers foreign key relationships between tables
- Creates graph edges representing these relationships

### 3. Sample Data
- Extracts sample values from columns (using Snowflake's `SAMPLE` clause)
- Provides representative data for better query generation

### 4. Schema Modification Detection
- Detects DDL operations (CREATE, ALTER, DROP, etc.)
- Automatically refreshes the graph when schema changes are detected

### 5. Query Execution
- Executes SQL queries on the Snowflake database
- Returns results in JSON format
- Handles both SELECT and DML operations

## Usage

### Via Web Interface

1. Navigate to the QueryWeaver web interface
2. Click on "Connect Database"
3. Enter your Snowflake connection URL
4. The schema will be automatically extracted and loaded

### Via API

```python
import requests

url = "http://localhost:5000/api/database/connect"
data = {
    "url": "snowflake://user:pass@account/database/schema?warehouse=wh"
}

response = requests.post(url, json=data)
print(response.json())
```

## Implementation Details

### Random Sampling

The Snowflake loader uses Snowflake's native `SAMPLE` clause for random sampling:

```sql
SELECT DISTINCT "column_name"
FROM "table_name"
WHERE "column_name" IS NOT NULL
SAMPLE (30 ROWS)
LIMIT 3;
```

### Information Schema Queries

The loader queries Snowflake's `INFORMATION_SCHEMA` views to extract metadata:
- `INFORMATION_SCHEMA.TABLES` - Table information
- `INFORMATION_SCHEMA.COLUMNS` - Column information
- `INFORMATION_SCHEMA.TABLE_CONSTRAINTS` - Constraint information
- `INFORMATION_SCHEMA.KEY_COLUMN_USAGE` - Foreign key relationships
- `INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE` - Constraint column mappings

## Testing

The Snowflake loader includes comprehensive unit tests covering:
- URL parsing and validation
- Value serialization
- Schema modification detection
- Connection handling
- Error handling

To run the tests:

```bash
uv run pytest tests/test_snowflake_loader.py -v
```

## Limitations

- Only supports single schema extraction per connection
- Requires appropriate permissions to access `INFORMATION_SCHEMA` views
- Sample data extraction may be limited by Snowflake's sampling mechanisms

## Security Considerations

- Passwords are not stored; they are only used during connection
- All SQL queries are parameterized to prevent injection attacks
- Connection credentials should be stored securely using environment variables or secrets management

## Troubleshooting

### Connection Issues

If you encounter connection errors:
1. Verify your account identifier is correct
2. Check that your credentials are valid
3. Ensure the database and schema exist
4. Verify the warehouse is running and accessible
5. Check network connectivity to Snowflake

### Schema Extraction Issues

If schema extraction fails:
1. Verify you have the necessary permissions to access `INFORMATION_SCHEMA`
2. Check that the schema contains tables
3. Ensure the schema name is correct (case-sensitive in Snowflake)

### Sample Data Issues

If sample data extraction fails:
1. Check that tables contain data
2. Verify column names are correct
3. Ensure you have SELECT permissions on the tables

## Related Files

- `api/loaders/snowflake_loader.py` - Main loader implementation
- `tests/test_snowflake_loader.py` - Unit tests
- `api/core/schema_loader.py` - Database type detection
- `api/core/text2sql.py` - Query execution integration
