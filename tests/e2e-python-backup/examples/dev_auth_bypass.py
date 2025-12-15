"""
Example implementation of development auth bypass.
This would need to be added to the actual QueryWeaver codebase.
"""
import os
from fastapi import Request
from typing import Any, Dict, Optional, Tuple # pylint: disable=wrong-import-order

# In api/auth/user_management.py, add this function:

async def get_test_user_for_development():
    """
    Return a test user for development/testing environments only.
    NEVER enable this in production!
    """
    if os.getenv("APP_ENV") != "development" or not os.getenv("ENABLE_TEST_AUTH"):
        return None

    return {
        "email": "test@example.com",
        "name": "Test User",
        "picture": "https://example.com/test-avatar.jpg"
    }

# In api/routes/auth.py, modify the validate_user function:

async def validate_user(request: Request) -> Tuple[Optional[Dict[str, Any]], bool]: # pylint: disable=unused-argument
    """Validate user authentication."""

    # Development bypass for testing
    if os.getenv("ENABLE_TEST_AUTH") == "true":
        test_user = await get_test_user_for_development()
        if test_user:
            return test_user, True

    # ... existing OAuth validation code ...
