"""
Test fixtures and sample data for E2E tests.
"""
# pylint: disable=consider-using-with
import json
import tempfile
import os


class TestDataFixtures:
    """Test data fixtures for E2E testing."""

    @staticmethod
    def create_sample_csv():
        """Create a sample CSV file for testing uploads."""
        csv_content = """name,age,city
John Doe,30,New York
Jane Smith,25,Los Angeles
Bob Johnson,35,Chicago"""

        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.csv', delete=False)
        temp_file.write(csv_content)
        temp_file.close()
        return temp_file.name

    @staticmethod
    def create_sample_json():
        """Create a sample JSON file for testing uploads."""
        json_data = {
            "users": [
                {"id": 1, "name": "John Doe", "email": "john@example.com"},
                {"id": 2, "name": "Jane Smith", "email": "jane@example.com"}
            ]
        }

        temp_file = tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False)
        json.dump(json_data, temp_file, indent=2)
        temp_file.close()
        return temp_file.name

    @staticmethod
    def cleanup_temp_file(file_path):
        """Clean up temporary test files."""
        if os.path.exists(file_path):
            os.unlink(file_path)

    @staticmethod
    def get_sample_queries():
        """Get sample queries for testing."""
        return [
            "Show me all users",
            "How many records are there?",
            "What is the average age?",
            "List users from New York"
        ]
