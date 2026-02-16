"""Test fixtures for QueryWeaver SDK integration tests."""

import os
import pytest
from urllib.parse import urlparse


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "requires_llm: mark test as requiring LLM API key"
    )
    config.addinivalue_line(
        "markers", "requires_postgres: mark test as requiring PostgreSQL"
    )
    config.addinivalue_line(
        "markers", "requires_mysql: mark test as requiring MySQL"
    )


@pytest.fixture(scope="session")
def falkordb_url():
    """Provide FalkorDB connection URL.

    Expects FalkorDB running (via `make docker-test-services` or CI service).
    """
    url = os.getenv("FALKORDB_URL", "redis://localhost:6379")

    # Verify connection
    from falkordb import FalkorDB
    try:
        db = FalkorDB.from_url(url)
        db.connection.ping()
    except Exception as e:
        pytest.skip(f"FalkorDB not available at {url}: {e}")

    return url


@pytest.fixture(scope="session")
def postgres_url():
    """Provide PostgreSQL connection URL with test database.

    Expects PostgreSQL running (via `make docker-test-services` or CI service).
    """
    url = os.getenv("TEST_POSTGRES_URL", "postgresql://postgres:postgres@localhost:5432/testdb")

    # Verify connection and create test schema
    try:
        import psycopg2
        conn = psycopg2.connect(url)
        cursor = conn.cursor()

        # Create test tables (DROP + CREATE ensures a clean slate)
        cursor.execute("""
            DROP TABLE IF EXISTS orders CASCADE;
            DROP TABLE IF EXISTS customers CASCADE;

            CREATE TABLE customers (
                id SERIAL PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                email VARCHAR(100) UNIQUE,
                city VARCHAR(100)
            );

            CREATE TABLE orders (
                id SERIAL PRIMARY KEY,
                customer_id INTEGER REFERENCES customers(id),
                product VARCHAR(100),
                amount DECIMAL(10,2),
                order_date DATE
            );

            -- Insert test data (UNIQUE on email allows ON CONFLICT)
            INSERT INTO customers (name, email, city) VALUES
                ('Alice Smith', 'alice@example.com', 'New York'),
                ('Bob Jones', 'bob@example.com', 'Los Angeles'),
                ('Carol White', 'carol@example.com', 'New York')
            ON CONFLICT (email) DO NOTHING;

            INSERT INTO orders (customer_id, product, amount, order_date) VALUES
                (1, 'Widget', 29.99, '2024-01-15'),
                (1, 'Gadget', 49.99, '2024-01-20'),
                (2, 'Widget', 29.99, '2024-02-01');
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        pytest.skip(f"PostgreSQL not available: {e}")

    return url


@pytest.fixture(scope="session")
def mysql_url():
    """Provide MySQL connection URL with test database.

    Expects MySQL running (via `make docker-test-services` or CI service).
    """
    url = os.getenv("TEST_MYSQL_URL", "mysql://root:root@localhost:3306/testdb")

    # Parse connection parameters from the URL
    parsed = urlparse(url)
    host = parsed.hostname or "localhost"
    port = parsed.port or 3306
    user = parsed.username or "root"
    password = parsed.password or "root"
    database = parsed.path.lstrip("/") or "testdb"

    # Verify connection and create test schema
    try:
        import pymysql
        conn = pymysql.connect(
            host=host,
            port=port,
            user=user,
            password=password,
            database=database,
        )
        cursor = conn.cursor()

        # Create test tables
        cursor.execute("DROP TABLE IF EXISTS products")
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                category VARCHAR(50),
                price DECIMAL(10,2)
            )
        """)

        cursor.execute("""
            INSERT INTO products (name, category, price) VALUES
                ('Laptop', 'Electronics', 999.99),
                ('Mouse', 'Electronics', 29.99),
                ('Desk', 'Furniture', 199.99)
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        pytest.skip(f"MySQL not available: {e}")

    return url


@pytest.fixture
async def queryweaver(falkordb_url):
    """Provide initialized QueryWeaver instance with proper teardown."""
    from queryweaver_sdk import QueryWeaver

    qw = QueryWeaver(falkordb_url=falkordb_url, user_id="test_user")
    yield qw
    await qw.close()


@pytest.fixture
def has_llm_key():
    """Check if LLM API key is available."""
    if not os.getenv("OPENAI_API_KEY") and not os.getenv("AZURE_API_KEY"):
        pytest.skip("LLM API key required (OPENAI_API_KEY or AZURE_API_KEY)")
    return True
