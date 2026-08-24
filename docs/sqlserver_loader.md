# SQL Server Loader

This document describes the Microsoft SQL Server loader implementation in QueryWeaver.

## Overview

The SQL Server loader connects to a Microsoft SQL Server (or Azure SQL) instance,
extracts schema information (tables, columns, primary keys, foreign keys and
relationships) and loads it into a graph so it can be used for Text2SQL queries.

It is built on [`pymssql`](https://pypi.org/project/pymssql/), which ships with the
`server` extra:

```bash
uv sync --extra server
```

## Connection URL Format

```text
sqlserver://username:password@host:port/database
```

### Parameters

- **username**: SQL Server login
- **password**: password for the login
- **host**: server hostname or IP
- **port**: server port (optional, defaults to `1433`)
- **database**: database to introspect
- **schema**: schema to introspect (optional query parameter, defaults to `dbo`)
- **encrypt**: `true`/`false` to force TLS on the connection (optional query parameter)

Credentials are percent-decoded, so passwords containing `@`, `/` or `:` are
supported when they are percent-encoded in the URL.

### Examples

```text
sqlserver://sa:MyPassw0rd@localhost:1433/AdventureWorks
sqlserver://sa:MyPassw0rd@localhost/AdventureWorks?schema=sales
sqlserver://appuser:s3cr3t@sql.example.com:1433/reporting?schema=dbo&encrypt=true
```

## Features

### Schema Extraction

- Tables and views in the selected schema
- Columns with data types, nullability, defaults and primary-key flags
- Extended properties (`MS_Description`) used as table and column descriptions
- Foreign keys, including composite keys
- Many-to-many relationships inferred from junction tables

All catalog queries join `sys.schemas` and bind the schema name as a parameter, so
a connection only ever sees the requested schema. Tables in other schemas are not
extracted and cannot collide with same-named tables in the selected schema.

### Sample Values

Sample values are collected per column with a schema-qualified, bracket-quoted
query:

```sql
SELECT DISTINCT TOP 3 [column_name]
FROM [dbo].[table_name]
WHERE [column_name] IS NOT NULL;
```

### Query Execution

- Executes SQL against the connected database
- Uses T-SQL (`tsql`) as the sqlglot dialect, so `SELECT TOP n`, `[bracketed]`
  identifiers and `FOR JSON PATH` parse correctly and are not misclassified by the
  destructive-operation guard
- Rolls back and closes the connection on failure

## Identifier Quoting

SQL Server delimits identifiers with brackets. A literal `]` inside a name is
escaped by doubling it, so `my]table` becomes `[my]]table]`. This is applied both
in the loader's own catalog/sample queries and in
`api/sql_utils/sql_sanitizer.py`, where `DatabaseSpecificQuoter.get_quote_char`
returns `[` for `sqlserver` and `mssql`.

## Usage

### From the Web Interface

1. Open the "Connect a database" dialog
2. Select **SQL Server**
3. Fill in host, port, database, credentials and (optionally) schema

### From the API

```python
import requests

response = requests.post(
    "http://localhost:5000/api/database/connect",
    json={"url": "sqlserver://sa:MyPassw0rd@localhost:1433/AdventureWorks"},
)
print(response.json())
```

## Implementation Details

### Catalog Queries

The loader reads from SQL Server system catalog views:

- `sys.tables` / `sys.views` joined with `sys.schemas` — table list
- `sys.columns` joined with `sys.types` — column metadata
- `sys.indexes` / `sys.index_columns` — primary keys
- `sys.foreign_keys` / `sys.foreign_key_columns` — foreign keys
- `sys.extended_properties` (with `class = 1`) — table and column descriptions

### Cursor Contract

Connections are opened with `as_dict=True`, so `pymssql` returns rows as
dictionaries keyed by column name. Positional access (`row[0]`) raises `KeyError`
with this setting and is never used.

## Testing

`tests/test_sqlserver_loader.py` covers:

- Bracket quoting and `]` escaping (including injection attempts)
- URL parsing: ports, defaults, percent-encoded credentials, `schema` and `encrypt`
- Dict-cursor row access for sample values
- Schema qualification of catalog and sample queries
- Column, foreign-key and relationship mapping
- Value serialization and schema-modification detection
- Query execution: select, non-select, error and connection-failure paths

```bash
uv run --extra server --extra dev pytest tests/test_sqlserver_loader.py -v
```

## Limitations

- One schema per connection (defaults to `dbo`); connect again to load another
- Requires permission to read the `sys.*` catalog views
- Windows/Azure AD integrated authentication is not supported; use SQL logins
