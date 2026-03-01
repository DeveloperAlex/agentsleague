# Copyright (c) Microsoft. All rights reserved.
"""Engagement Agent — interacts with students, provides encouragement and practice."""

from agents.foundry_agent_executor import FoundryAgentExecutor

AGENT_NAME = "engagement-agent"
AGENT_VERSION = "3"


def create_engagement_agent(openai_client) -> FoundryAgentExecutor:
    """Create an engagement agent executor wrapping the Foundry-deployed agent."""
    return FoundryAgentExecutor(
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        openai_client=openai_client,
        executor_id="engagement-agent",
    )

