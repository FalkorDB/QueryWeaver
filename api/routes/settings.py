"""Settings and configuration routes for the text2sql API."""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from litellm import completion

settings_router = APIRouter(tags=["Settings"])


def _sanitize_for_log(value: str) -> str:
    """Remove control characters that could enable log injection."""
    return str(value).replace("\r", "").replace("\n", "").replace("\t", " ")


class ValidateKeyRequest(BaseModel):
    """Request model for API key validation."""
    api_key: str
    vendor: str = "openai"
    model: str = "gpt-3.5-turbo"


@settings_router.post("/validate-api-key")
async def validate_api_key(request: Request, data: ValidateKeyRequest):  # pylint: disable=too-many-return-statements
    """
    Validate an AI provider API key by making a simple test request.
    This endpoint does not store the key, it only validates it.
    Supports: openai, google, anthropic
    """
    _ = request
    api_key = data.api_key.strip()
    vendor = data.vendor.lower()
    model = data.model

    if not api_key:
        return JSONResponse(
            content={"valid": False, "error": "API key is required"},
            status_code=400
        )

    # Validate vendor is supported
    supported_vendors = (
        "openai", "anthropic", "gemini", "azure", "ollama", "cohere",
    )
    if vendor not in supported_vendors:
        allowed = ", ".join(supported_vendors)
        return JSONResponse(
            content={"valid": False, "error": f"Unsupported vendor. Supported: {allowed}"},
            status_code=400
        )

    # Validate model is not empty
    if not model or not model.strip():
        return JSONResponse(
            content={"valid": False, "error": "Model name is required"},
            status_code=400
        )

    # Validate key format based on vendor
    if vendor == "openai" and not api_key.startswith('sk-'):
        return JSONResponse(
            content={"valid": False, "error": "Invalid OpenAI API key format"},
            status_code=400
        )
    if vendor == "anthropic" and not api_key.startswith('sk-ant-'):
        return JSONResponse(
            content={"valid": False, "error": "Invalid Anthropic API key format"},
            status_code=400
        )

    try:
        # Construct model name for LiteLLM (vendor/model format)
        full_model_name = f"{vendor}/{model}"

        test_response = completion(
            model=full_model_name,
            messages=[{"role": "user", "content": "test"}],
            max_tokens=1,
            api_key=api_key,
        )

        # If we get here without exception, the key is valid
        if test_response and test_response.choices:
            return JSONResponse(
                content={"valid": True},
                status_code=200
            )
        return JSONResponse(
            content={"valid": False, "error": "Invalid API key"},
            status_code=401
        )

    except Exception as e:  # pylint: disable=broad-except
        error_lower = str(e).lower()
        logging.warning("API key validation failed for vendor=%s",
                        _sanitize_for_log(vendor))

        # Return generic messages — never expose exception details
        if "invalid" in error_lower or "authentication" in error_lower:
            return JSONResponse(
                content={"valid": False, "error": "Invalid API key"},
                status_code=401
            )
        if "quota" in error_lower or "rate" in error_lower:
            return JSONResponse(
                content={"valid": False, "error": "API quota exceeded or rate limited"},
                status_code=429
            )
        return JSONResponse(
            content={"valid": False, "error": "Failed to validate API key"},
            status_code=500
        )
