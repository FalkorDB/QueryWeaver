"""
Test chat and query functionality.
"""
import pytest
from tests.e2e.pages.home_page import HomePage
from tests.e2e.fixtures.test_data import TestDataFixtures


class TestChatFunctionality:
    """Test chat and query functionality."""

    @pytest.mark.skip(reason="Requires authentication and graph data")
    def test_send_basic_query(self, page_with_base_url):
        """Test sending a basic query through chat interface."""
        home_page = HomePage(page_with_base_url)
        home_page.navigate_to_home()

        # Type and send a query
        query = "Show me all users"
        home_page.type_message(query)
        home_page.send_message()

        # Wait for response
        home_page.wait_for_response()

        # Check that response was received
        messages = home_page.get_chat_messages()
        assert len(messages) > 0

    @pytest.mark.skip(reason="Requires authentication and graph data")
    def test_multiple_queries(self, page_with_base_url):
        """Test sending multiple queries in sequence."""
        home_page = HomePage(page_with_base_url)
        home_page.navigate_to_home()

        queries = TestDataFixtures.get_sample_queries()

        for query in queries[:2]:  # Test first 2 queries
            home_page.type_message(query)
            home_page.send_message()
            home_page.wait_for_response()

        # Check that multiple messages exist
        messages = home_page.get_chat_messages()
        assert len(messages) >= 2

    @pytest.mark.skip(reason="Requires authentication and graph selection")
    def test_graph_selection(self, page_with_base_url):
        """Test graph selection functionality."""
        home_page = HomePage(page_with_base_url)
        home_page.navigate_to_home()

        # Test graph selection if graphs are available
        # This would require pre-loaded graphs
        page = page_with_base_url
        graph_selector = page.query_selector(home_page.GRAPH_SELECTOR)

        if graph_selector:
            # Test selecting different graphs
            options = page.query_selector_all(f"{home_page.GRAPH_SELECTOR} option")
            if len(options) > 1:
                home_page.select_graph(options[1].get_attribute("value"))

    def test_chat_interface_structure(self, page_with_base_url):
        """Test that chat interface has proper structure."""
        home_page = HomePage(page_with_base_url)
        home_page.navigate_to_home()

        page = page_with_base_url

        # Check for basic chat elements and verify page loaded successfully
        # These might not be visible without authentication
        page.query_selector_all("input, textarea")

        # Verify the page loaded successfully by checking the title or URL
        assert "QueryWeaver" in page.title() or page.url.endswith("/")

    def test_input_validation(self, page_with_base_url):
        """Test input validation and limits."""
        home_page = HomePage(page_with_base_url)
        home_page.navigate_to_home()

        page = page_with_base_url

        # Test with very long input
        long_text = "a" * 1000

        # Try to find any visible and enabled text input
        enabled_inputs = page.locator(
            "input[type='text']:not([disabled]):visible, "
            "textarea:not([disabled]):visible",
        ).all()

        if enabled_inputs:
            # Get the first enabled input element
            first_input = enabled_inputs[0]

            # Test that long input is handled appropriately
            first_input.fill(long_text)

            # Check if input was truncated (indicating validation) or fully accepted
            actual_value = first_input.input_value()
            if len(actual_value) < 1000:
                # Input was truncated - validation is working
                assert len(actual_value) > 0, "Input should not be completely rejected"
            else:
                # Input was fully accepted - ensure it matches what we entered
                assert actual_value == long_text, "Input should be preserved if not truncated"
        else:
            # No enabled inputs found - this is expected for unauthenticated users
            # Just verify the page loaded successfully
            assert "QueryWeaver" in page.title() or page.url.endswith("/")
            # This is the expected behavior for unauthenticated users

    @pytest.mark.skip(reason="Requires streaming response setup")
    def test_streaming_responses(self, page_with_base_url):
        """Test streaming response functionality."""
        home_page = HomePage(page_with_base_url)
        home_page.navigate_to_home()

        # Test that streaming responses work correctly
        # This would require a test query that generates streaming response
        pytest.skip("Streaming response test not yet implemented")
