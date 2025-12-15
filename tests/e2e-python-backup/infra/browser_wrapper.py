"""
Browser wrapper utilities for E2E tests.
Provides a wrapper around Playwright browser functionality.
"""
from typing import Optional
from playwright.sync_api import Page, Browser, BrowserContext


class BrowserWrapper:
    """Wrapper for browser functionality in E2E tests."""

    def __init__(self, browser: Optional[Browser] = None, 
                 context: Optional[BrowserContext] = None,
                 page: Optional[Page] = None):
        """Initialize browser wrapper with optional browser, context, and page."""
        self.browser = browser
        self.context = context
        self.page = page

    def set_page(self, page: Page):
        """Set the page object."""
        self.page = page

    def get_page(self) -> Optional[Page]:
        """Get the current page object."""
        return self.page

    def set_context(self, context: BrowserContext):
        """Set the browser context."""
        self.context = context

    def get_context(self) -> Optional[BrowserContext]:
        """Get the browser context."""
        return self.context

    def set_browser(self, browser: Browser):
        """Set the browser object."""
        self.browser = browser

    def get_browser(self) -> Optional[Browser]:
        """Get the browser object."""
        return self.browser

    def navigate_to(self, url: str):
        """Navigate to a URL."""
        if not self.page:
            raise RuntimeError("Page not initialized")
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)

    def wait_for_page_load(self):
        """Wait for page to be fully loaded."""
        if not self.page:
            raise RuntimeError("Page not initialized")
        self.page.wait_for_load_state("networkidle")

    def set_viewport_size(self, width: int, height: int):
        """Set viewport size."""
        if not self.page:
            raise RuntimeError("Page not initialized")
        self.page.set_viewport_size({"width": width, "height": height})

    def refresh_page(self):
        """Refresh the current page."""
        if not self.page:
            raise RuntimeError("Page not initialized")
        self.page.reload(wait_until="networkidle")

    def get_current_url(self) -> str:
        """Get the current page URL."""
        if not self.page:
            raise RuntimeError("Page not initialized")
        return self.page.url
