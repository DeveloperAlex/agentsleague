# Copyright (c) Microsoft. All rights reserved.
"""Exam Planner — plans exam logistics via Microsoft Learn MCP.

This agent is deployed in Foundry with MicrosoftLearnMCPserver2 tool attached.
"""

from agents.foundry_agent_executor import FoundryAgentExecutor

AGENT_NAME = "exam-planner"
AGENT_VERSION = "3"


def create_exam_planner(openai_client) -> FoundryAgentExecutor:
    """Create an exam planner executor wrapping the Foundry-deployed agent."""
    return FoundryAgentExecutor(
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        openai_client=openai_client,
        executor_id="exam-planner",
        terminal=True,
    )

