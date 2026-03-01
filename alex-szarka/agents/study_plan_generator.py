# Copyright (c) Microsoft. All rights reserved.
"""Study Plan Generator — creates structured study plans from curated learning paths."""

from agents.foundry_agent_executor import FoundryAgentExecutor

AGENT_NAME = "study-plan-generator"
AGENT_VERSION = "3"


def create_study_plan_generator(openai_client) -> FoundryAgentExecutor:
    """Create a study plan generator executor wrapping the Foundry-deployed agent."""
    return FoundryAgentExecutor(
        agent_name=AGENT_NAME,
        agent_version=AGENT_VERSION,
        openai_client=openai_client,
        executor_id="study-plan-generator",
    )

