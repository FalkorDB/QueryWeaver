"""Settings and configuration routes for the text2sql API."""

import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from litellm import completion

settings_router = APIRouter(tags=["Settings"])


class ValidateKeyRequest(BaseModel):
    """Request model for API key validation."""
    api_key: str
    vendor: str = "openai"
    model: str = "gpt-3.5-turbo"


@settings_router.post("/validate-api-key")
async def validate_api_key(request: Request, data: ValidateKeyRequest):
    """
    Validate an AI provider API key by making a simple test request.
    This endpoint does not store the key, it only validates it.
    Supports: openai, google, anthropic
    """
    api_key = data.api_key.strip()
    vendor = data.vendor.lower()
    model = data.model
    
    if not api_key:
        return JSONResponse(
            content={"valid": False, "error": "API key is required"},
            status_code=400
        )
    
    # Validate key format based on vendor
    if vendor == "openai" and not api_key.startswith('sk-'):
        return JSONResponse(
            content={"valid": False, "error": "Invalid OpenAI API key format"},
            status_code=400
        )
    elif vendor == "anthropic" and not api_key.startswith('sk-ant-'):
        return JSONResponse(
            content={"valid": False, "error": "Invalid Anthropic API key format"},
            status_code=400
        )
    # Note: 'gemini' is accepted as vendor (Google's LiteLLM prefix)
    
    try:
        # Construct model name for LiteLLM (vendor/model format)
        full_model_name = f"{vendor}/{model}"
        
        # Make a minimal test request to validate the key
        # We'll use a very short completion to minimize cost
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
        else:
            return JSONResponse(
                content={"valid": False, "error": "Invalid API key"},
                status_code=401
            )
            
    except Exception as e:  # pylint: disable=broad-except
        error_msg = str(e)
        logging.warning("%s API key validation failed: %s", vendor.capitalize(), error_msg)
        
        # Check for common error messages
        if "invalid" in error_msg.lower() or "authentication" in error_msg.lower():
            return JSONResponse(
                content={"valid": False, "error": "Invalid API key"},
                status_code=401
            )
        elif "quota" in error_msg.lower() or "rate" in error_msg.lower():
            return JSONResponse(
                content={"valid": False, "error": "API quota exceeded or rate limited"},
                status_code=429
            )
        else:
            return JSONResponse(
                content={"valid": False, "error": f"Failed to validate API key: {error_msg}"},
                status_code=500
            )
