"""
Integration test for QueryWeaver library API.

This test verifies that the library can be imported and basic functionality works.
Note: This test requires a running FalkorDB instance and valid API keys.
"""

import os
import pytest
from unittest.mock import patch


def test_library_import():
    """Test that the library can be imported successfully."""
    try:
        from queryweaver import QueryWeaverClient, create_client
        assert QueryWeaverClient is not None
        assert create_client is not None
    except ImportError as e:
        pytest.fail(f"Failed to import QueryWeaver library: {e}")


@patch('falkordb.FalkorDB')
def test_client_initialization(mock_falkordb):
    """Test basic client initialization without external dependencies."""
    mock_falkordb.return_value.ping.return_value = True
    
    from queryweaver import QueryWeaverClient
    
    client = QueryWeaverClient(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="test-key"
    )
    
    assert client is not None
    assert client.falkordb_url == "redis://localhost:6379/0"
    assert client._user_id == "library_user"


@patch('falkordb.FalkorDB')
def test_convenience_function(mock_falkordb):
    """Test the convenience function for creating clients."""
    mock_falkordb.return_value.ping.return_value = True
    
    from queryweaver import create_client
    
    client = create_client(
        falkordb_url="redis://localhost:6379/0",
        openai_api_key="test-key"
    )
    
    assert client is not None


@pytest.mark.skipif(
    not os.getenv("FALKORDB_URL") or not (os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_API_KEY")),
    reason="Requires FALKORDB_URL and either OPENAI_API_KEY or AZURE_API_KEY environment variables"
)
def test_real_connection():
    """Test real connection to FalkorDB (only runs with proper environment setup)."""
    from queryweaver import QueryWeaverClient
    
    client = QueryWeaverClient(
        falkordb_url=os.environ["FALKORDB_URL"],
        openai_api_key=os.environ.get("OPENAI_API_KEY"),
        azure_api_key=os.environ.get("AZURE_API_KEY")
    )
    
    # Test basic functionality
    databases = client.list_loaded_databases()
    assert isinstance(databases, list)


if __name__ == "__main__":
    # Run tests
    test_library_import()
    print("✓ Library import test passed")
    
    test_client_initialization()
    print("✓ Client initialization test passed")
    
    test_convenience_function()
    print("✓ Convenience function test passed")
    
    # Only run real connection test if environment is set up
    if os.getenv("FALKORDB_URL") and (os.getenv("OPENAI_API_KEY") or os.getenv("AZURE_API_KEY")):
        try:
            test_real_connection()
            print("✓ Real connection test passed")
        except Exception as e:
            print(f"✗ Real connection test failed: {e}")
    else:
        print("⚠ Skipping real connection test (missing environment variables)")
    
    print("\nAll available tests completed!")