# Copyright (c) Microsoft. All rights reserved.
"""
Foundry helper utilities.

Common patterns for creating and invoking Foundry agents within
Agent Framework executors.

Uses the AzureOpenAI Responses API directly — no pre-registered agents needed.
Each call passes the model deployment name and inline instructions, so there is
no separate "create agent" REST round-trip.
"""

import logging
import os
from typing import Any

from openai import AzureOpenAI

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal registry: name → {model, instructions, tools}
# ---------------------------------------------------------------------------
_AGENT_REGISTRY: dict[str, dict[str, Any]] = {}


def _get_config() -> tuple[str, str]:
    """Return (resource_endpoint, api_key) from environment.

    The ``FOUNDRY_PROJECT_ENDPOINT`` typically looks like
    ``https://<resource>.services.ai.azure.com/api/projects/<project>``.
    The AzureOpenAI Responses API only works against the *resource-level*
    endpoint (without the ``/api/projects/…`` suffix), so we strip that part.
    """
    raw = os.environ.get(
        "FOUNDRY_PROJECT_ENDPOINT",
        "https://buildathon2026c-resource.services.ai.azure.com/api/projects/buildathon2026c",
    )
    # Strip the project-scoped path so the OpenAI SDK can build its own routes
    idx = raw.find("/api/projects")
    endpoint = raw[:idx] if idx != -1 else raw
    api_key = os.environ.get("FOUNDRY_API_KEY", "")
    return endpoint, api_key


# ---------------------------------------------------------------------------
# Agent "creation" — stores config locally (no REST call)
# ---------------------------------------------------------------------------

def create_foundry_agent(
    *,
    name: str,
    model: str,
    instructions: str,
    tools: list | None = None,
) -> str:
    """
    Register an agent configuration locally and return its **name**.

    No remote call is made.  The stored config (model, instructions, tools)
    is used later by ``invoke_foundry_agent``.
    """
    _AGENT_REGISTRY[name] = {
        "model": model,
        "instructions": instructions,
        "tools": tools or [],
    }
    logger.info("Registered agent config '%s' (model=%s)", name, model)
    return name


# ---------------------------------------------------------------------------
# Agent invocation  (AzureOpenAI Responses API)
# ---------------------------------------------------------------------------

def invoke_foundry_agent(
    agent_name: str,
    input_text: str,
) -> str:
    """
    Invoke a Foundry model via the OpenAI Responses API, using the
    instructions stored in the local registry, and return the assistant's
    text output as a plain string.
    """
    cfg = _AGENT_REGISTRY.get(agent_name)
    if cfg is None:
        raise ValueError(
            f"Agent '{agent_name}' not found in registry. "
            "Call create_foundry_agent() first."
        )

    endpoint, api_key = _get_config()

    # The Responses API requires a non-empty input string
    if not input_text or not input_text.strip():
        logger.warning("invoke_foundry_agent('%s') called with empty input", agent_name)
        return ""

    oai = AzureOpenAI(
        api_key=api_key,
        azure_endpoint=endpoint,
        api_version="2025-03-01-preview",
    )

    kwargs: dict[str, Any] = {
        "model": cfg["model"],
        "instructions": cfg["instructions"],
        "input": input_text,
    }

    # NOTE: MCP tools are NOT passed to the Responses API because the API
    # does not execute them inline.  The model uses its training knowledge
    # instead.  To use MCP tools, register them server-side in Foundry.

    response = oai.responses.create(**kwargs)

    # Prefer the convenience property (available in openai >= 2.x)
    if hasattr(response, "output_text") and response.output_text:
        return response.output_text

    # Fallback: iterate output items manually
    parts: list[str] = []
    for item in getattr(response, "output", []) or []:
        content = getattr(item, "content", None)
        if not content:
            continue
        for block in content:
            text = getattr(block, "text", None)
            if text:
                parts.append(text)
    return "\n".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# MCP tool helper
# ---------------------------------------------------------------------------

def get_mcp_tools(tool_name: str) -> list[dict]:
    """
    Return a list containing an MCP tool dict for the Microsoft Learn MCP server.
    ``tool_name`` is the server label (e.g. "mslearn-mcp-server").
    """
    try:
        tool = {
            "type": "mcp",
            "server_label": tool_name,
            "server_url": "https://learn.microsoft.com/api/mcp",
        }
        logger.info("MCP tool configured: %s", tool_name)
        return [tool]
    except Exception as exc:
        logger.warning(
            "Could not set up MCP tool '%s': %s — agent will work without MCP.",
            tool_name, exc,
        )
        return []
