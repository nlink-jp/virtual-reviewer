"""Vertex AI LLM client.

Thin wrapper around the google-genai SDK. All modules use this to call Gemini.
Authentication is via ADC (Application Default Credentials).
"""

from __future__ import annotations

import mimetypes
import os
import time
from pathlib import Path

from google import genai
from google.genai import types

from virtual_reviewer import log as vr_log

# Default model names — override via environment variables
DEFAULT_MODELS = {
    "intake": "gemini-2.5-pro",
    "compiler": "gemini-2.5-pro",
    "orchestrator": "gemini-2.5-flash",
    "expert": "gemini-2.5-pro",
    "brain": "gemini-2.5-pro",
}

_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is not None:
        return _client
    project = os.environ.get("VR_PROJECT_ID") or os.environ.get(
        "GOOGLE_CLOUD_PROJECT"
    )
    location = os.environ.get("VR_LOCATION", "asia-northeast1")
    if not project:
        raise RuntimeError(
            "Set VR_PROJECT_ID or GOOGLE_CLOUD_PROJECT environment variable"
        )
    _client = genai.Client(
        vertexai=True,
        project=project,
        location=location,
    )
    return _client


def get_model_name(module: str) -> str:
    """Get the model name for a module, respecting env var overrides."""
    env_key = f"VR_MODEL_{module.upper()}"
    return os.environ.get(env_key, DEFAULT_MODELS.get(module, DEFAULT_MODELS["expert"]))


def generate(
    module: str,
    system_prompt: str,
    user_prompt: str,
    *,
    parts: list[types.Part] | None = None,
    temperature: float = 0.2,
    response_mime_type: str = "application/json",
    response_schema: type | None = None,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> str:
    """Call Gemini and return the response text.

    Args:
        module: Module name (for model selection and logging).
        system_prompt: System instruction.
        user_prompt: User message text.
        parts: Additional multimodal parts (images, PDFs, etc.).
        temperature: Sampling temperature.
        response_mime_type: Expected response format.
        response_schema: Pydantic model to enforce output schema.
        max_retries: Max retries on rate limit errors.
        base_delay: Base delay for exponential backoff.

    Returns:
        Raw response text from the model.
    """
    client = _get_client()
    model_name = get_model_name(module)

    contents: list[types.Part] = []
    if parts:
        contents.extend(parts)
    contents.append(types.Part.from_text(text=user_prompt))

    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        temperature=temperature,
        response_mime_type=response_mime_type,
        response_schema=response_schema,
    )

    vr_log.info(
        module,
        "llm_request",
        f"Calling {model_name}",
        model=model_name,
        temperature=temperature,
    )

    for attempt in range(max_retries + 1):
        try:
            response = client.models.generate_content(
                model=model_name,
                contents=contents,
                config=config,
            )
            text = response.text or ""
            vr_log.info(
                module,
                "llm_response",
                f"Received response ({len(text)} chars)",
                model=model_name,
                response_length=len(text),
            )
            return text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str and attempt < max_retries:
                delay = base_delay * (2**attempt)
                vr_log.warn(
                    module,
                    "rate_limit",
                    f"Rate limited, retrying in {delay}s (attempt {attempt + 1}/{max_retries})",
                )
                time.sleep(delay)
                continue
            raise

    raise RuntimeError("Unreachable")


def load_file_as_part(file_path: str) -> types.Part:
    """Load a file and return it as a Part for multimodal input."""
    path = Path(file_path)
    mime_type = mimetypes.guess_type(str(path))[0] or "application/octet-stream"
    data = path.read_bytes()
    return types.Part.from_bytes(data=data, mime_type=mime_type)
