# Copyright (c) Microsoft. All rights reserved.
"""Learning Path Curator — curates learning paths via Microsoft Learn MCP.

This agent is deployed in Foundry with MicrosoftLearnMCPserver2 tool attached.
"""

from agents.foundry_agent_executor import FoundryAgentExecutor

AGENT_NAME = "learning-path-curator"
AGENT_VERSION = "6"


def create_learning_path_curator(openai_client) -> FoundryAgentExecutor:
    """Create a learning path curator executor wrapping the Foundry-deployed agent."""
    return FoundryAgentExecutor(
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        openai_client=openai_client,
        executor_id="learning-path-curator",
    )

