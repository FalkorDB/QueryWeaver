#!/usr/bin/env python3
"""
Test script for PostgreSQL Loader

This script provides basic tests for the PostgreSQL loader functionality.
"""

import asyncio
import unittest
from unittest.mock import Mock, patch

from api.loaders.postgres_loader import PostgresLoader


class TestPostgreSQLLoader(unittest.TestCase):
    """Test cases for PostgreSQL Loader"""

    def setUp(self):
        """Set up test fixtures"""
        self.test_connection_url = "postgresql://test:test@localhost:5432/testdb"
        self.test_graph_id = "test_graph"

    @patch("api.loaders.postgres_loader.psycopg2.connect")
    @patch("api.loaders.postgres_loader.load_to_graph")
    @unittest.skip("Skipping this test with unittest")
    def test_successful_load(self, mock_load_to_graph, mock_connect):
        """Test successful schema loading"""
        # Mock database connection and cursor
        mock_conn = Mock()
        mock_cursor = Mock()
        mock_connect.return_value = mock_conn
        mock_conn.cursor.return_value = mock_cursor

        # Mock table data
        mock_cursor.fetchall.return_value = [
            ("users", "User information table"),
            ("orders", "Order tracking table"),
        ]

        # Mock successful load_to_graph
        mock_load_to_graph.return_value = None

        # Test the loader
        success, message = asyncio.run(
            PostgresLoader.load(self.test_graph_id, self.test_connection_url)
        )

        # Assertions
        self.assertTrue(success)
        self.assertIn("PostgreSQL schema loaded successfully", message)
        mock_connect.assert_called_once_with(self.test_connection_url)
        mock_load_to_graph.assert_called_once()

    @patch("api.loaders.postgres_loader.psycopg2.connect")
    def test_connection_error(self, mock_connect):
        """Test handling of connection errors"""
        # Mock connection error
        mock_connect.side_effect = Exception("Connection failed")

        # Test the loader
        success, message = asyncio.run(
            PostgresLoader.load(self.test_graph_id, self.test_connection_url)
        )

        # Assertions
        self.assertFalse(success)
        self.assertIn("Error loading PostgreSQL schema", message)

    def test_extract_columns_info(self):
        """Test column information extraction"""
        # Mock cursor with column data
        mock_cursor = Mock()
        mock_cursor.fetchall.side_effect = [
            # First call: column metadata
            [
                ("id", "integer", "NO", None, "PRIMARY KEY", "User ID"),
                ("name", "varchar", "NO", None, "NONE", "User name"),
                ("email", "varchar", "YES", None, "NONE", "User email address"),
            ],
            # Second call: row count for 'id' column
            [(100, 100)],
            # Third call: row count for 'name' column  
            [(100, 50)],
            # Fourth call: row count for 'email' column
            [(100, 80)]
        ]

        # Test the method
        columns_info = PostgresLoader.extract_columns_info(mock_cursor, "users")

        # Assertions
        self.assertEqual(len(columns_info), 3)
        self.assertIn("id", columns_info)
        self.assertIn("name", columns_info)
        self.assertIn("email", columns_info)

        # Check column details
        self.assertEqual(columns_info["id"]["type"], "integer")
        self.assertEqual(columns_info["id"]["key"], "PRIMARY KEY")
        self.assertIn("User ID", columns_info["id"]["description"])

    def test_extract_foreign_keys(self):
        """Test foreign key extraction"""
        # Mock cursor with foreign key data
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            ("fk_user_id", "user_id", "users", "id"),
            ("fk_product_id", "product_id", "products", "id"),
        ]

        # Test the method
        foreign_keys = PostgresLoader.extract_foreign_keys(mock_cursor, "orders")

        # Assertions
        self.assertEqual(len(foreign_keys), 2)
        self.assertEqual(foreign_keys[0]["column"], "user_id")
        self.assertEqual(foreign_keys[0]["referenced_table"], "users")
        self.assertEqual(foreign_keys[0]["referenced_column"], "id")

    def test_extract_relationships(self):
        """Test relationship extraction"""
        # Mock cursor with relationship data
        mock_cursor = Mock()
        mock_cursor.fetchall.return_value = [
            ("orders", "fk_user_id", "user_id", "users", "id"),
            ("orders", "fk_product_id", "product_id", "products", "id"),
        ]

        # Test the method
        relationships = PostgresLoader.extract_relationships(mock_cursor)

        # Assertions
        self.assertEqual(len(relationships), 2)
        self.assertIn("fk_user_id", relationships)
        self.assertIn("fk_product_id", relationships)

        # Check relationship details
        user_rel = relationships["fk_user_id"][0]
        self.assertEqual(user_rel["from"], "orders")
        self.assertEqual(user_rel["to"], "users")
        self.assertEqual(user_rel["source_column"], "user_id")
        self.assertEqual(user_rel["target_column"], "id")


def run_tests():
    """Run all tests"""
    print("Running PostgreSQL Loader Tests")
    print("=" * 40)

    unittest.main(verbosity=2, exit=False)


if __name__ == "__main__":
    run_tests()
