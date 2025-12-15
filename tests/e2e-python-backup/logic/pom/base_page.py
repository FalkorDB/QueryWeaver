"""
Base Page Object for common functionality.
"""


class BasePage:
    """Base page object with common functionality."""

    def __init__(self, page):
        """Initialize base page with playwright page object."""
        self.page = page

    def navigate_to(self, path=""):
        """Navigate to a specific path."""
        url = f"{self.page.app_url}{path}"
        # Use domcontentloaded instead of load
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

    def wait_for_page_load(self):
        """Wait for page to be fully loaded."""
        self.page.wait_for_load_state("networkidle")

    def get_page_title(self):
        """Get the page title."""
        return self.page.title()

    def screenshot(self, name):
        """Take a screenshot for debugging."""
        self.page.screenshot(path=f"tests/e2e/screenshots/{name}.png")
