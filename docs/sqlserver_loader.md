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
- **encrypt**: `true`/`false` to require or disable TLS on the connection (optional
  query parameter). **The server certificate is not verified**: FreeTDS encrypts
  the connection but `pymssql` exposes no CA setting, so this protects against
  passive eavesdropping only. An on-path attacker presenting any certificate can
  still read the login, including the password. Use a trusted network or VPN when
  that matters.

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

- Tables in the selected schema (views are not extracted)
- Columns with their base data types (an alias type such as `dbo.Name` is reported
  as `nvarchar(50)`), nullability, defaults and key flags
- Extended properties (`MS_Description`) used as table and column descriptions
- Foreign keys, including composite keys — both sides must live in the selected schema

All catalog queries join `sys.schemas` and bind the schema name as a parameter, so
the loader extracts only the tables in the requested schema, and tables in other schemas
cannot collide with same-named tables in the selected schema. This scopes what is
loaded into the graph, not what the login may access: generated queries run with the
login's own permissions, so grant it access to the selected schema only if that is
the boundary you want.

Tables are stored in the graph under bare names for `dbo` and as `schema.table` for
any other schema. SQL Server has no per-session default schema: an unqualified name
resolves against the login's default schema, so `SELECT * FROM orders` would miss
`sales.orders`, or quietly read `dbo.orders` instead. Storing the qualified name
means the generated SQL names the right table. A name part containing a dot is
stored bracketed (`[sales.eu].Orders`, `[weird.name]`), since T-SQL would otherwise
read `sales.eu.Orders` as database, schema and table.

The table, column and foreign-key catalogs are each read in one schema-wide query
before any sampling starts.

### Sample Values

Sample values are collected per column with a schema-qualified, bracket-quoted
query. The `DISTINCT` sits in a derived table because SQL Server rejects
`SELECT DISTINCT … ORDER BY NEWID()`:

```sql
SELECT TOP 3 [column_name]
FROM (SELECT DISTINCT [column_name] FROM [dbo].[table_name]
      WHERE [column_name] IS NOT NULL) AS sampled
ORDER BY NEWID();
```

Sampling is best-effort: a column whose type has no `DISTINCT` (`xml`, `text`,
`image`, the spatial types) is logged and left without samples rather than
failing the schema load. The schema and table are quoted separately, so a dot in
either name does not stop the table being sampled.

Sampling stops early, and the remaining columns load without samples, once
`DB_SCHEMA_TIMEOUT` has passed since introspection started, or the connection is lost (a
timed-out statement can leave the FreeTDS connection unusable).

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
returns `[` for `sqlserver`.

## Usage

### From the Web Interface

1. Open the "Connect a database" dialog
2. Select **SQL Server**
3. Fill in host, port, database, credentials and (optionally) schema

### From the API

`POST /database` requires an API token and streams its progress as JSON messages
separated by `|||FALKORDB_MESSAGE_BOUNDARY|||`:

```python
import json
import requests

BOUNDARY = "|||FALKORDB_MESSAGE_BOUNDARY|||"

response = requests.post(
    "http://localhost:5000/database",
    headers={"Authorization": "Bearer <API_TOKEN>"},
    json={"url": "sqlserver://sa:MyPassw0rd@localhost:1433/AdventureWorks"},
    stream=True,
)
response.raise_for_status()

buffer = ""
for chunk in response.iter_content(chunk_size=1024, decode_unicode=True):
    buffer += chunk
    while BOUNDARY in buffer:
        message, buffer = buffer.split(BOUNDARY, 1)
        if message.strip():
            print(json.loads(message))
```

## Implementation Details

### Catalog Queries

The loader reads from SQL Server system catalog views:

- `sys.tables` joined with `sys.schemas` — table list
- `sys.columns` joined with `sys.types` — column metadata
- `sys.indexes` / `sys.index_columns` — primary keys
- `sys.foreign_keys` / `sys.foreign_key_columns` — foreign keys
- `sys.extended_properties` (with `class = 1`) — table and column descriptions

### Cursor Contract

Introspection opens its cursor with `as_dict=True`, so `pymssql` returns catalog
rows as dictionaries keyed by column name; positional access (`row[0]`) raises
`KeyError` with this setting and is never used there.

User queries use a plain tuple cursor instead, because `as_dict=True` raises
`ColumnsWithoutNamesError` for a `COUNT(*)` without an alias and lets duplicate names
(`o.id, c.id`) overwrite each other. Result rows are keyed from
`cursor.description`: an unnamed column becomes `column_<n>` by position and a
repeated name gets a `_2`, `_3` suffix.

### Timeouts

`DB_CONNECT_TIMEOUT` maps to `login_timeout` and bounds the connection and login
handshake.

Each statement is bounded by `pymssql`'s `timeout`, set to `DB_STATEMENT_TIMEOUT`
for every connection this loader opens — the same per-statement ceiling the other
loaders give user queries.

> `pymssql` documents that `timeout` and `login_timeout` have a *process-wide*
> effect, because the underlying db-lib API functions used to implement them are
> global. Giving introspection and query execution different values would let
> concurrent operations overwrite each other's, so both use the same one.

`DB_SCHEMA_TIMEOUT` is a sampling cutoff, not a hard limit on the whole
introspection: it is checked before each sample query starts (see
[Sample Values](#sample-values)). The three catalog queries and a sample query
already running are each still bounded only by `DB_STATEMENT_TIMEOUT`, so the worst
case is about `DB_SCHEMA_TIMEOUT` plus four statement timeouts, rather than one
statement timeout per column.

## Testing

`tests/test_sqlserver_loader.py` covers:

- Bracket quoting and `]` escaping (including injection attempts)
- URL parsing: ports, defaults, percent-encoded credentials, `schema` and `encrypt`
- Dict-cursor row access for sample values, and result rows with unnamed or
  duplicate columns
- Schema qualification of catalog and sample queries
- Column, foreign-key and relationship mapping
- Value serialization and schema-modification detection
- Query execution: select, non-select, error and connection-failure paths

```bash
uv run --extra server --extra dev pytest tests/test_sqlserver_loader.py -v
```

`tests/test_sqlserver_integration.py` runs the same introspection against a real
server, because a fake cursor cannot tell you whether the SQL parses or what the
driver decodes a column into. It builds a deliberately awkward schema — non-ASCII
table and column names, a `]` and a `.` in a table name, `xml`/`text`/`geography`
columns, a `uniqueidentifier`, a composite key and a cross-schema foreign key —
and asserts the tables load, the non-comparable types degrade to no samples, and
the cross-schema key is excluded from both entities and relationships.

It skips unless `SQLSERVER_TEST_URL` is set:

```bash
docker run -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD='Str0ng!Passw0rd' \
    -p 1433:1433 -d mcr.microsoft.com/mssql/server:2022-latest

SQLSERVER_TEST_URL='sqlserver://sa:Str0ng!Passw0rd@localhost:1433/master' \
    uv run --extra server --extra dev pytest tests/test_sqlserver_integration.py -v
```

## Limitations

- One schema per connection (defaults to `dbo`); connect again to load another
- Requires permission to read the `sys.*` catalog views
- Windows/Azure AD integrated authentication is not supported; use SQL logins
- The `encrypt` option does not verify the server certificate; see [Parameters](#parameters)
