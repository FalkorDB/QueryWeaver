"""
Integration test for QueryWeaver library API.

This test verifies that the library can be imported and basic functionality works.
Note: This test requires a running FalkorDB instance and valid API keys.
"""

import os
from unittest.mock import patch

import pytest

from queryweaver import QueryWeaverClient, create_client


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


@pytest.mark.skipif(
    not os.getenv("FALKORDB_URL") or not (os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_API_KEY")),
    reason=("Requires FALKORDB_URL and either OPENAI_API_KEY or "
            "AZURE_API_KEY environment variables")
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