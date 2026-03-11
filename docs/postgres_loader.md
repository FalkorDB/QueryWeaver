# PostgreSQL Schema Loader

This loader connects to a PostgreSQL database and extracts the complete schema information, including tables, columns, relationships, and constraints. The extracted schema is then loaded into a graph database for further analysis and query generation.

## Features

- **Complete Schema Extraction**: Retrieves all tables, columns, data types, constraints, and relationships
- **Custom Schema Support**: Configure which PostgreSQL schema to extract using the `search_path` option
- **Foreign Key Relationships**: Automatically discovers and maps foreign key relationships between tables
- **Column Metadata**: Extracts column comments, default values, nullability, and key types
- **Batch Processing**: Efficiently processes large schemas with progress tracking
- **Error Handling**: Robust error handling for connection issues and malformed schemas

## Installation

psycopg2-binary is already included in QueryWeaver's dependencies. Install project dependencies with:

```bash
uv sync
```

## Usage

### Basic Usage

{% capture python_0 %}
from api.loaders.postgres_loader import PostgreSQLLoader

# Connection URL format: postgresql://username:password@host:port/database
connection_url = "postgresql://postgres:password@localhost:5432/mydatabase"
graph_id = "my_schema_graph"

success, message = PostgreSQLLoader.load(graph_id, connection_url)

if success:
    print(f"Schema loaded successfully: {message}")
else:
    print(f"Failed to load schema: {message}")
{% endcapture %}

{% capture javascript_0 %}
import { PostgreSQLLoader } from 'your-pkg';

const connectionUrl = "postgresql://postgres:password@localhost:5432/mydatabase";
const graphId = "my_schema_graph";

const [success, message] = await PostgreSQLLoader.load(graphId, connectionUrl);
if (success) {
  console.log(`Schema loaded successfully: ${message}`);
} else {
  console.log(`Failed to load schema: ${message}`);
}
{% endcapture %}

{% capture java_0 %}
String connectionUrl = "postgresql://postgres:password@localhost:5432/mydatabase";
String graphId = "my_schema_graph";
Pair<Boolean, String> result = PostgreSQLLoader.load(graphId, connectionUrl);
if (result.getLeft()) {
    System.out.println("Schema loaded successfully: " + result.getRight());
} else {
    System.out.println("Failed to load schema: " + result.getRight());
}
{% endcapture %}

{% capture rust_0 %}
let connection_url = "postgresql://postgres:password@localhost:5432/mydatabase";
let graph_id = "my_schema_graph";
let (success, message) = postgresql_loader::load(graph_id, connection_url)?;
if success {
    println!("Schema loaded successfully: {}", message);
} else {
    println!("Failed to load schema: {}", message);
}
{% endcapture %}

{% include code_tabs.html id="basic_usage_tabs" python=python_0 javascript=javascript_0 java=java_0 rust=rust_0 %}

### Connection URL Format

```
postgresql://[username[:password]@][host[:port]][/database][?options]
```

**Examples:**
- `postgresql://postgres:password@localhost:5432/mydatabase`
- `postgresql://user:pass@example.com:5432/production_db`
- `postgresql://postgres@127.0.0.1/testdb`

### Custom Schema Configuration

By default, the loader extracts tables from the `public` schema. To use a different schema, add the `search_path` option to your connection URL using PostgreSQL's standard `options` parameter. 
More info [here](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-SEARCH-PATH).

**Format:**
```
postgresql://user:pass@host:port/database?options=-csearch_path%3Dschema_name
```

**Examples:**
- Extract from `sales` schema
  `postgresql://postgres:password@localhost:5432/mydb?options=-csearch_path=sales`
- Extract from `dbo` schema
  `postgresql://user:pass@host:5432/enterprise_db?options=-csearch_path=dbo`
- Extract from `inventory` schema
  `postgresql://admin:secret@192.168.1.100:5432/warehouse?options=-csearch_path%3Dinventory`

**Notes:**
- The `%3D` is the URL-encoded form of `=`
- If `search_path` is not specified, the loader defaults to `public`
- The schema must exist and the user must have `USAGE` permission on it
- This follows PostgreSQL's native `search_path` configuration option

**Using the UI:**

When connecting via the QueryWeaver UI with "Manual Entry" mode for PostgreSQL, you can specify the schema in the optional "Schema" field. Leave it empty to use the default `public` schema.

### Integration with Graph Database

{% capture python_1 %}
from api.loaders.postgres_loader import PostgreSQLLoader
from api.extensions import db

# Load PostgreSQL schema into graph
graph_id = "customer_db_schema"
connection_url = "postgresql://postgres:password@localhost:5432/customers"

success, message = PostgreSQLLoader.load(graph_id, connection_url)

if success:
    # The schema is now available in the graph database
    graph = db.select_graph(graph_id)

    # Query for all tables
    result = await graph.query("MATCH (t:Table) RETURN t.name")
    print("Tables:", [record[0] for record in result.result_set])
{% endcapture %}

{% capture javascript_1 %}
import { PostgreSQLLoader, db } from 'your-pkg';

const graphId = "customer_db_schema";
const connectionUrl = "postgresql://postgres:password@localhost:5432/customers";

const [success, message] = await PostgreSQLLoader.load(graphId, connectionUrl);
if (success) {
  const graph = db.selectGraph(graphId);
  const result = await graph.query("MATCH (t:Table) RETURN t.name");
  console.log("Tables:", result.map(r => r[0]));
}
{% endcapture %}

{% capture java_1 %}
String graphId = "customer_db_schema";
String connectionUrl = "postgresql://postgres:password@localhost:5432/customers";
Pair<Boolean, String> result = PostgreSQLLoader.load(graphId, connectionUrl);
if (result.getLeft()) {
    Graph graph = db.selectGraph(graphId);
    ResultSet rs = graph.query("MATCH (t:Table) RETURN t.name");
    // Print table names
    for (Record record : rs) {
        System.out.println(record.get(0));
    }
}
{% endcapture %}

{% capture rust_1 %}
let graph_id = "customer_db_schema";
let connection_url = "postgresql://postgres:password@localhost:5432/customers";
let (success, message) = postgresql_loader::load(graph_id, connection_url)?;
if success {
    let graph = db.select_graph(graph_id);
    let result = graph.query("MATCH (t:Table) RETURN t.name")?;
    println!("Tables: {:?}", result.iter().map(|r| &r[0]).collect::<Vec<_>>());
}
{% endcapture %}

{% include code_tabs.html id="integration_tabs" python=python_1 javascript=javascript_1 java=java_1 rust=rust_1 %}

## Schema Structure

The loader extracts the following information:

### Tables
- Table name
- Table description/comment
- Column information
- Foreign key relationships

### Columns
- Column name
- Data type
- Nullability
- Default values
- Key type (PRIMARY KEY, FOREIGN KEY, or NONE)
- Column descriptions/comments

### Relationships
- Foreign key constraints
- Referenced tables and columns
- Constraint names and metadata

## Graph Database Schema

The extracted schema is stored in the graph database with the following node types:

- **Database**: Represents the source database
- **Table**: Represents database tables
- **Column**: Represents table columns

And the following relationship types:

- **BELONGS_TO**: Connects columns to their tables
- **REFERENCES**: Connects foreign key columns to their referenced columns

## Error Handling

The loader handles various error conditions:

- **Connection Errors**: Invalid connection URLs or database unavailability
- **Permission Errors**: Insufficient database permissions
- **Schema Errors**: Invalid or corrupt schema information
- **Graph Errors**: Issues with graph database operations

## Example Output

{% capture shell_2 %}
Extracting table information: 100%|██████████| 15/15 [00:02<00:00,  7.50it/s]
Creating Graph Table Nodes: 100%|██████████| 15/15 [00:05<00:00,  2.80it/s]
Creating embeddings for customers columns: 100%|██████████| 2/2 [00:01<00:00,  1.20it/s]
Creating Graph Columns for customers: 100%|██████████| 8/8 [00:03<00:00,  2.40it/s]
...
Creating Graph Table Relationships: 100%|██████████| 12/12 [00:02<00:00,  5.20it/s]

PostgreSQL schema loaded successfully. Found 15 tables.
{% endcapture %}

{% include code_tabs.html id="output_tabs" shell=shell_2 %}

## Requirements

- Python 3.12+
- psycopg2-binary
- Access to a PostgreSQL database
- Existing graph database infrastructure (FalkorDB)

## Limitations

- Currently only supports PostgreSQL databases
- Extracts schema from one schema at a time (defaults to 'public', configurable via `search_path`)
- Requires read permissions on information_schema and pg_* system tables
- Large schemas may take time to process due to embedding generation

## Troubleshooting

### Common Issues

1. **Connection Failed**: Verify the connection URL format and database credentials
2. **Permission Denied**: Ensure the database user has read access to system tables
3. **No Tables Found**:
- Check that tables exist in the target schema
- If using a custom schema, verify the `search_path` option is correctly formatted
- Ensure the schema name is spelled correctly (schema names are case-sensitive when created or referenced with double quotes; unquoted identifiers are folded to lower-case)
4. **Graph Database Error**: Verify that the graph database is running and accessible
5. **Schema Permission Error**: Ensure the database user has `USAGE` permission on the target schema:
    ```sql
    GRANT USAGE ON SCHEMA my_schema TO my_user;
    GRANT SELECT ON ALL TABLES IN SCHEMA my_schema TO my_user;
    ```

### Verifying Schema Configuration

To verify which schema will be used, you can test the search_path parsing:

{% capture python_2 %}
from api.loaders.postgres_loader import PostgresLoader

# Test URL parsing
url = "postgresql://user:pass@localhost:5432/mydatabase?options=-c search_path=my_schema"
schema = PostgresLoader.parse_schema_from_url(url)
print(f"Schema to be used: {schema}")  # Output: my_schema
{% endcapture %}

### Debug Mode

For debugging, you can enable verbose output by modifying the loader to print additional information about the extraction process.
