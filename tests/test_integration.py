"""
Integration test for QueryWeaver library API.

This test verifies that the library can be imported and basic functionality works.
Note: This test requires a running FalkorDB instance and valid API keys.
"""

import os
from unittest.mock import patch

import pytest

# Ensure src is on sys.path for tests to import local package
import sys
from pathlib import Path
import socket
from urllib.parse import urlparse
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from queryweaver import QueryWeaverClient, create_client  # pylint: disable=import-error


def _is_falkordb_reachable(url: str) -> bool:
    """Quick TCP reachability check for the FalkorDB host:port."""
    try:
        parsed = urlparse(url)
        host = parsed.hostname or "localhost"
        port = parsed.port or 6379
        with socket.create_connection((host, port), timeout=1):
            return True
    except Exception:
        return False


def test_library_import():
    """Test that the library can be imported successfully."""
    assert QueryWeaverClient is not None
    assert create_client is not None


@patch('falkordb.FalkorDB')
def test_client_initialization(mock_falkordb):
    """Test basic client initialization without external dependencies."""
    mock_falkordb.return_value.ping.return_value = True

    client = QueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="test-key"
    )

    assert client is not None
    assert client.falkordb_url == "redis://localhost:6379/0"
    assert client._user_id == "library_user"  # pylint: disable=protected-access


@patch('falkordb.FalkorDB')
def test_convenience_function(mock_falkordb):
    """Test the convenience function for creating clients."""
    mock_falkordb.return_value.ping.return_value = True

    client = create_client(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="test-key"
    )

    assert client is not None


FALKORDB_URL_ENV = os.getenv("FALKORDB_URL")
RUN_REAL_INTEGRATION = os.getenv("RUN_REAL_INTEGRATION", "false").lower() in ("1", "true", "yes")


@pytest.mark.skipif(
    not RUN_REAL_INTEGRATION or
    not FALKORDB_URL_ENV or
    not _is_falkordb_reachable(FALKORDB_URL_ENV) or
    not (os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_API_KEY")),
    reason=("Set RUN_REAL_INTEGRATION=true and provide reachable FALKORDB_URL plus API keys to run this test")
)
def test_real_connection():
    """Test real connection to FalkorDB (only runs with proper environment setup)."""
    client = QueryWeaverClient(
        falkordb_url=os.environ["FALKORDB_URL"],
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        azure_api_key=os.environ.get("AZURE_API_KEY")
    )

    # Test basic functionality
    databases = client.list_loaded_databases()
    assert isinstance(databases, list)
