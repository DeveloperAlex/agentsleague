# Copyright (c) Microsoft. All rights reserved.
"""Dispatcher agent — analyzes student topics and routes to the learning subworkflow."""

from agents.foundry_agent_executor import FoundryAgentExecutor

AGENT_NAME = "dispatcher"
AGENT_VERSION = "3"


def create_dispatcher(openai_client) -> FoundryAgentExecutor:
    """Create a dispatcher executor wrapping the Foundry-deployed dispatcher agent."""
    return FoundryAgentExecutor(
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        openai_client=openai_client,
        executor_id="dispatcher",
    )

