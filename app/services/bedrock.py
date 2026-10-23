"""Shared Amazon Bedrock plumbing for the MCP tools.

Two tools call Bedrock: `ingest_receipt_items` extracts structured items from
a receipt photo, and `generate_and_adapt_recipe` reasons about what to cook.
Both hit the same three Converse behaviours, so the handling lives here once.

1. Converse has no structured-output mode, so JSON is requested in prose and
   validated afterwards by a Pydantic model with `extra="forbid"`.
2. The model wraps JSON in a ``` fence even when told to return bare JSON,
   so `parse_json_response` strips the fence before parsing.
3. `boto3` has no async client, so callers must offload the blocking call
   with `asyncio.to_thread` to avoid stalling other MCP sessions.
"""
from __future__ import annotations

import json
from typing import Any, TypeVar

import boto3
from botocore.config import Config
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings

ModelT = TypeVar("ModelT", bound=BaseModel)


# A receipt extraction is a vision call and the slowest thing the server does;
# measured round trips sit around 6 seconds for text alone. The caller that
# matters is the Next.js proxy, which aborts `tools/call` after 120 seconds, so
# the budget here is sized to stay inside that: two attempts of 50 seconds
# leaves room for a retry after a throttle without ever outlasting the client.
# botocore would otherwise default to a 60 second read with legacy retries,
# which can run past the client and strand a call nobody is still waiting for.
BEDROCK_CONNECT_TIMEOUT = 10
BEDROCK_READ_TIMEOUT = 50
# `total_max_attempts` rather than `max_attempts`: botocore reads the latter as
# a retry count and silently resolves it to one attempt more than asked for.
BEDROCK_TOTAL_MAX_ATTEMPTS = 2


def get_client() -> Any:
    """Return a `bedrock-runtime` client for the configured region."""
    settings = get_settings()
    return boto3.client(
        "bedrock-runtime",
        region_name=settings.aws_region,
        config=Config(
            connect_timeout=BEDROCK_CONNECT_TIMEOUT,
            read_timeout=BEDROCK_READ_TIMEOUT,
            retries={
                "mode": "standard",
                "total_max_attempts": BEDROCK_TOTAL_MAX_ATTEMPTS,
            },
        ),
    )


def response_text(response: dict[str, Any]) -> str:
    """Join the text blocks of a Converse response into one string."""
    content = response.get("output", {}).get("message", {}).get("content", [])
    return "\n".join(
        block["text"] for block in content if isinstance(block.get("text"), str)
    ).strip()


def strip_code_fence(text: str) -> str:
    """Remove a surrounding ``` fence, with or without a `json` language tag.

    Converse adds one despite an explicit instruction not to, which is why
    this exists rather than parsing the reply directly.
    """
    stripped = text.strip()
    if stripped.startswith("```") and stripped.endswith("```"):
        stripped = stripped[3:-3].strip()
        if stripped.startswith("json"):
            stripped = stripped[4:].strip()
    return stripped


def parse_json_response(
    response: dict[str, Any], model: type[ModelT], what: str
) -> ModelT:
    """Validate a Converse reply against `model`.

    `what` names the payload in the error messages, so a failure says which
    tool produced it rather than just "invalid JSON".
    """
    text = strip_code_fence(response_text(response))
    if not text:
        raise ValueError(f"Bedrock returned no JSON content for {what}.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(f"Bedrock returned invalid {what} JSON.") from error
    try:
        return model.model_validate(payload)
    except ValidationError as error:
        raise ValueError(f"Bedrock returned invalid {what} JSON.") from error
