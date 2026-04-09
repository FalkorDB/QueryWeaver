"""Tests for settings route API key validation."""

from unittest.mock import patch, MagicMock

import pytest

from api.routes.settings import validate_api_key, ValidateKeyRequest, _sanitize_for_log


class TestSanitizeForLog:
    """Tests for log sanitization helper."""

    def test_removes_newlines(self):
        assert _sanitize_for_log("line1\nline2") == "line1line2"

    def test_removes_carriage_returns(self):
        assert _sanitize_for_log("line1\rline2") == "line1line2"

    def test_replaces_tabs_with_space(self):
        assert _sanitize_for_log("col1\tcol2") == "col1 col2"

    def test_combined_control_chars(self):
        assert _sanitize_for_log("a\r\n\tb") == "a b"

    def test_clean_string_unchanged(self):
        assert _sanitize_for_log("openai") == "openai"


class TestValidateKeyRequest:
    """Tests for the request validation model."""

    def test_defaults(self):
        req = ValidateKeyRequest(api_key="sk-test123456")
        assert req.vendor == "openai"
        assert req.model == "gpt-3.5-turbo"

    def test_custom_vendor_and_model(self):
        req = ValidateKeyRequest(api_key="key", vendor="anthropic", model="claude-sonnet-4-5-20250929")
        assert req.vendor == "anthropic"
        assert req.model == "claude-sonnet-4-5-20250929"


class TestValidateApiKeyEndpoint:
    """Tests for the /settings/validate-api-key endpoint logic."""

    @pytest.fixture
    def mock_request(self):
        """Create a mock request with session (simulating authenticated user)."""
        request = MagicMock()
        request.session = {"user": {"id": "test-user"}}
        return request

    @pytest.mark.asyncio
    async def test_empty_api_key(self, mock_request):
        data = ValidateKeyRequest(api_key="   ", vendor="openai")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 400
        body = response.body.decode()
        assert "API key is required" in body

    @pytest.mark.asyncio
    async def test_unsupported_vendor(self, mock_request):
        data = ValidateKeyRequest(api_key="sk-test123456", vendor="unsupported")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 400
        body = response.body.decode()
        assert "Unsupported vendor" in body

    @pytest.mark.asyncio
    async def test_non_validatable_vendor(self, mock_request):
        """Vendors like azure/ollama can't be validated via API key check."""
        data = ValidateKeyRequest(api_key="sk-test123456", vendor="azure")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 400
        body = response.body.decode()
        assert "Unsupported vendor" in body

    @pytest.mark.asyncio
    async def test_empty_model(self, mock_request):
        data = ValidateKeyRequest(api_key="sk-test123456", vendor="openai", model="  ")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 400
        body = response.body.decode()
        assert "Model name is required" in body

    @pytest.mark.asyncio
    async def test_invalid_openai_key_format(self, mock_request):
        data = ValidateKeyRequest(api_key="invalid-key-format", vendor="openai")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 400
        body = response.body.decode()
        assert "Invalid OpenAI API key format" in body

    @pytest.mark.asyncio
    async def test_invalid_anthropic_key_format(self, mock_request):
        data = ValidateKeyRequest(api_key="sk-not-anthropic", vendor="anthropic")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 400
        body = response.body.decode()
        assert "Invalid Anthropic API key format" in body

    @pytest.mark.asyncio
    @patch('api.routes.settings.completion')
    async def test_valid_key_returns_success(self, mock_completion, mock_request):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_completion.return_value = mock_response

        data = ValidateKeyRequest(api_key="sk-validkey123456", vendor="openai")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 200
        body = response.body.decode()
        assert '"valid":true' in body

        mock_completion.assert_called_once_with(
            model="openai/gpt-3.5-turbo",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1,
            api_key="sk-validkey123456",
        )

    @pytest.mark.asyncio
    @patch('api.routes.settings.completion')
    async def test_auth_error_returns_401(self, mock_completion, mock_request):
        mock_completion.side_effect = Exception("AuthenticationError: invalid api key")

        data = ValidateKeyRequest(api_key="sk-invalidkey12345", vendor="openai")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 401
        body = response.body.decode()
        assert "Invalid API key" in body

    @pytest.mark.asyncio
    @patch('api.routes.settings.completion')
    async def test_rate_limit_returns_429(self, mock_completion, mock_request):
        mock_completion.side_effect = Exception("Rate limit exceeded")

        data = ValidateKeyRequest(api_key="sk-validkey123456", vendor="openai")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 429
        body = response.body.decode()
        assert "quota exceeded or rate limited" in body

    @pytest.mark.asyncio
    @patch('api.routes.settings.completion')
    async def test_unknown_error_returns_500(self, mock_completion, mock_request):
        mock_completion.side_effect = Exception("Something unexpected happened")

        data = ValidateKeyRequest(api_key="sk-validkey123456", vendor="openai")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 500
        body = response.body.decode()
        assert "Failed to validate API key" in body

    @pytest.mark.asyncio
    @patch('api.routes.settings.completion')
    async def test_gemini_vendor_accepted(self, mock_completion, mock_request):
        mock_response = MagicMock()
        mock_response.choices = [MagicMock()]
        mock_completion.return_value = mock_response

        data = ValidateKeyRequest(api_key="AIzaSyTest123456", vendor="gemini", model="gemini-pro")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 200

        mock_completion.assert_called_once_with(
            model="gemini/gemini-pro",
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1,
            api_key="AIzaSyTest123456",
        )

    @pytest.mark.asyncio
    @patch('api.routes.settings.completion')
    async def test_no_choices_returns_401(self, mock_completion, mock_request):
        mock_response = MagicMock()
        mock_response.choices = []
        mock_completion.return_value = mock_response

        data = ValidateKeyRequest(api_key="sk-validkey123456", vendor="openai")
        response = await validate_api_key.__wrapped__(mock_request, data)
        assert response.status_code == 401
        body = response.body.decode()
        assert "Invalid API key" in body
