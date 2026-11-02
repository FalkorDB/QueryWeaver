# Oracle Loader

This document describes the Oracle loader implementation in QueryWeaver.

## Overview

The Oracle loader enables QueryWeaver to connect to Oracle databases, extract schema information (tables, columns, foreign keys, relationships), and load it into a graph structure for Text2SQL queries.

It uses `python-oracledb` in thin mode, which speaks the Oracle wire protocol directly. No Oracle Instant Client installation is needed.

## Connection URL Format

```
oracle://username:password@host:port/service_name
```

### URL Components

- **username**: Your Oracle username
- **password**: Your Oracle password. Percent-encode any of `: @ / # ?` (the web interface's manual entry form does this for you)
- **host**: The database host
- **port**: The listener port (optional, defaults to `1521`)
- **service_name**: The service name to connect to (required)

### Query Parameters

- **schema**: The schema (owner) to load (optional, defaults to the connecting username). Oracle stores names in upper case unless they were quoted at creation, so the value is converted to upper case.
- **ssl**: Set to `true` to connect over TLS (TCPS) with server certificate DN matching. Required by Oracle Autonomous Database, which rejects plain TCP. No wallet is needed for endpoints with a publicly trusted certificate.

### Examples

On-premises database, connecting user's own schema:
```
oracle://scott:tiger@dbhost:1521/ORCLPDB1
```

Introspect a different schema:
```
oracle://scott:tiger@dbhost:1521/ORCLPDB1?schema=HR
```

Oracle Autonomous Database (TLS):
```
oracle://ADMIN:password@adb.us-ashburn-1.oraclecloud.com:1521/abc123_mydb_high.adb.oraclecloud.com?ssl=true
```

## Installation

The driver ships with the `server` extra, like the Snowflake connector:

```bash
uv sync --extra server
```

The SDK-only install rejects `oracle://` URLs with a clear error instead of failing on a missing import.

## Features

### 1. Schema Extraction
- Extracts all tables owned by the target schema from `ALL_TAB_COMMENTS`
- Skips recycle-bin objects (`BIN$...`), which are dropped tables rather than real ones
- Retrieves column data types, nullability, defaults and comments
- Identifies primary keys and foreign keys from `ALL_CONSTRAINTS` / `ALL_CONS_COLUMNS`

### 2. Relationship Mapping
- Discovers foreign key relationships, including composite keys, and creates graph edges for them

### 3. Sample Data
- Extracts random sample values per column using `ORDER BY DBMS_RANDOM.VALUE` with `FETCH FIRST n ROWS ONLY`
- Skips LOB-family columns (`CLOB`, `NCLOB`, `BLOB`, `BFILE`, `LONG`, `LONG RAW`, `XMLTYPE`): Oracle rejects `DISTINCT` and `ORDER BY` on them (`ORA-00932`)

### 4. Schema Modification Detection
- Detects DDL operations (CREATE, ALTER, DROP, etc.) and refreshes the graph

### 5. Query Execution
- Executes SQL against the database and returns rows as JSON (LOB values are read into plain values)
- Destructive-statement detection parses with the Oracle SQL dialect

## Usage

### Via Web Interface

1. Click on "Connect Database"
2. Select "Oracle"
3. Either paste a connection URL, or use manual entry: host, port, service name, username, password, optional schema, and the "Use TLS (TCPS)" switch for Autonomous Database

## Implementation Details

### Timeouts

The connect is bounded by `DB_CONNECT_TIMEOUT` (`tcp_connect_timeout`). Every round trip is bounded by `call_timeout`: `DB_SCHEMA_TIMEOUT` during introspection and `DB_STATEMENT_TIMEOUT` for user queries.

### Identifier Safety

Oracle has no bind-variable syntax for identifiers, so the table and column names used in sampling queries are checked against the characters Oracle allows in plain names (letters, digits, `_`, `$`, `#`) and then double-quoted. All values are passed as bind variables.

## Testing

```bash
uv run pytest tests/test_oracle_loader.py -v
```

The tests cover URL parsing (defaults, schema override, TLS, encoded credentials), value serialization, identifier validation, LOB sampling, recycle-bin filtering, schema modification detection and connection handling.

## Limitations

- Only one schema is extracted per connection
- Requires `SELECT` access to the `ALL_*` dictionary views for the target schema
- Connections that require an Oracle wallet (mutual TLS) are not supported; use one-way TLS (`?ssl=true`)

## Troubleshooting

### Connection Issues

1. Use the service name, not the SID
2. For Autonomous Database, add `?ssl=true`
3. If the password contains `: @ / # ?`, percent-encode it in the URL

### No Tables Found

1. Check the schema name. It defaults to the connecting user, but the tables may belong to a different owner (use `?schema=OWNER`)
2. Verify the user can see the tables through the `ALL_*` views

## Related Files

- `api/loaders/oracle_loader.py` - Main loader implementation
- `tests/test_oracle_loader.py` - Unit tests
- `api/core/pipeline.py` - Database type detection and SQL dialect mapping
- `app/src/components/modals/DatabaseModal.tsx` - Connection form
