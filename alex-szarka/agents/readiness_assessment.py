# Copyright (c) Microsoft. All rights reserved.
"""Readiness Assessment — evaluates student readiness for certification exam."""

from agents.foundry_agent_executor import FoundryAgentExecutor

AGENT_NAME = "readiness-assessment"
AGENT_VERSION = "3"


def create_readiness_assessment(openai_client) -> FoundryAgentExecutor:
    """Create a readiness assessment executor wrapping the Foundry-deployed agent."""
    return FoundryAgentExecutor(
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        openai_client=openai_client,
        executor_id="readiness-assessment",
    )

