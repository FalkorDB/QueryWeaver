"""
Home Page Object for QueryWeaver application.
"""
# pylint: disable=broad-exception-caught
from tests.e2e.logic.pom.base_page import BasePage


class HomePage(BasePage):
    """Home page object for the QueryWeaver chat interface."""

    # Selectors
    LOGIN_BUTTON = "a[href*='login']"
    CHAT_CONTAINER = ".chat-container"
    MESSAGE_INPUT = "input[type='text'], textarea"
    SEND_BUTTON = "button[type='submit']"
    GRAPH_SELECTOR = "select[name='graph']"
    FILE_UPLOAD = "#schema-upload"  # Updated to use correct ID from UI analysis
    LOADING_INDICATOR = ".loading"

    def navigate_to_home(self):
        """Navigate to the home page."""
        self.navigate_to("/")
        # Wait for the page content to be loaded, not all resources
        self.page.wait_for_load_state("domcontentloaded", timeout=30000)

    def is_authenticated(self):
        """Check if user is authenticated."""
        # If login button is visible, user is not authenticated
        try:
            self.page.wait_for_selector(self.LOGIN_BUTTON, timeout=2000)
            return False
        except Exception:
            return True

    def click_login(self):
        """Click the login button."""
        # Wait for the login button to be visible before clicking
        self.page.wait_for_selector(self.LOGIN_BUTTON, state="visible", timeout=5000)
        self.page.click(self.LOGIN_BUTTON)

    def has_chat_interface(self):
        """Check if chat interface is present."""
        try:
            self.page.wait_for_selector(self.CHAT_CONTAINER, timeout=5000)
            return True
        except Exception:
            return False

    def type_message(self, message):
        """Type a message in the chat input."""
        self.page.fill(self.MESSAGE_INPUT, message)

    def send_message(self):
        """Send the typed message."""
        self.page.click(self.SEND_BUTTON)

    def upload_file(self, file_path):
        """Upload a file."""
        # The file input might not be visible, but we can still set files on it
        file_input = self.page.query_selector(self.FILE_UPLOAD)
        if not file_input:
            raise Exception("File upload input not found") # pylint: disable=broad-exception-raised

        # Set the file even if input is not visible (common for file inputs)
        self.page.set_input_files(self.FILE_UPLOAD, file_path)

    def select_graph(self, graph_name):
        """Select a graph from dropdown."""
        self.page.select_option(self.GRAPH_SELECTOR, graph_name)

    def wait_for_response(self, timeout=10000):
        """Wait for response to load."""
        # Wait for loading indicator to disappear
        try:
            self.page.wait_for_selector(self.LOADING_INDICATOR, state="hidden", timeout=timeout)
        except Exception:
            pass  # Loading indicator might not be present

    def get_chat_messages(self):
        """Get all chat messages."""
        return self.page.query_selector_all(".message")
