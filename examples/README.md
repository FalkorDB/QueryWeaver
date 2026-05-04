# QueryWeaver SDK — E-commerce Demo

End-to-end walkthrough of using the `queryweaver` Python package against
a realistic 12-table PostgreSQL schema.

## What's in here

| File | Purpose |
|---|---|
| `ecommerce_example.sql` | Creates a `queryweaver_demo` database with 12 tables and ~120 rows of seed data |
| `ecommerce_example.py` | SDK script: connect → introspect schema → run a one-shot query → run a follow-up with chat history → tear down |

The schema models a small e-commerce business:

```text
users ───┬── addresses
         ├── orders ── order_items ── product_variants ── products ── categories (self-ref)
         │      └── payments                    │            │
         │                                      │            └── product_suppliers ── suppliers (M:N)
         └── reviews ─────────────────────────────────────── products
                                                inventory ──┘
```

12 tables, 13 foreign-key relationships including one self-reference
(`categories.parent_id`) and one many-to-many (`product_suppliers`).

## Prerequisites

- Docker
- Python 3.12+
- An LLM provider key — OpenAI, Azure OpenAI, Gemini, Anthropic, or Cohere
- A FalkorDB instance (the steps below run one in Docker)

## 1. Start PostgreSQL

```bash
docker run -d --name queryweaver-pg \
  -e POSTGRES_USER=root \
  -e POSTGRES_PASSWORD=123123 \
  -p 5432:5432 \
  postgres:15
```

## 2. Start FalkorDB

```bash
docker run -d --name queryweaver-falkor \
  -p 6379:6379 \
  falkordb/falkordb:latest
```

(Or skip this step and point at a managed FalkorDB by setting `FALKORDB_URL`
in step 5.)

## 3. Load the demo schema and seed data

```bash
docker cp examples/ecommerce_example.sql queryweaver-pg:/tmp/demo.sql
docker exec queryweaver-pg psql -U root -d postgres -f /tmp/demo.sql
```

The script ends with a row-count summary — you should see all 12 tables
populated.

## 4. Install the SDK

```bash
pip install queryweaver
```

Or from a local checkout of this repo:

```bash
pip install -e .
```

## 5. Set environment variables

```bash
export FALKORDB_URL=redis://localhost:6379
export OPENAI_API_KEY=sk-...
```

For Azure OpenAI:

```bash
export AZURE_API_KEY=...
export AZURE_API_BASE=https://<resource>.openai.azure.com/
export AZURE_API_VERSION=2024-12-01-preview
```

Other supported providers: `GEMINI_API_KEY`, `ANTHROPIC_API_KEY`,
`COHERE_API_KEY`. See `api/config.py` for provider detection logic.

## 6. Run the example

```bash
python examples/ecommerce_example.py
```

You will see:
- Connection + schema-load status
- Generated SQL for the natural-language question
- Rows returned by PostgreSQL
- An AI-formatted summary
- A follow-up query that uses chat history (`QueryRequest.chat_history` /
  `result_history`)
- Final cleanup of the loaded schema

## Cleanup

```bash
docker rm -f queryweaver-pg queryweaver-falkor
```

## Sample questions to try

Edit `ecommerce_example.py` (or open a Python REPL) and try:

- "Which products are low on stock across all warehouses?"
- "Show the top 3 suppliers by total cost across all products they supply"
- "Find users who bought a laptop and also reviewed it"
- "List orders whose payment is still pending"
- "Show the category hierarchy" *(self-join on `categories`)*
