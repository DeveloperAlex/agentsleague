# Copyright (c) Microsoft. All rights reserved.
"""Student Certification Readiness Multi-Agent System — Entry Point.

Orchestrates a multi-agent workflow using Microsoft Agent Framework:

  Student Input
       │
       ▼
  ┌─────────────┐
  │  Dispatcher  │  Analyzes topics, produces learning brief
  └──────┬──────┘
         ▼
  ┌──────────────────────┐
  │ Learning Path Curator │  Curates paths via Microsoft Learn MCP
  └──────────┬───────────┘
             ▼
  ┌──────────────────────┐
  │ Study Plan Generator  │  Creates structured study plan
  └──────────┬───────────┘
             ▼
  ┌──────────────────────┐
  │  Engagement Agent     │◄─────────────┐  Interacts with student
  └──────────┬───────────┘               │
             ▼                           │
  ┌──────────────────────┐               │
  │  Assessment Gate      │  HITL: "Ready │  to be assessed?"
  └──────────┬───────────┘               │
             ▼                           │
  ┌──────────────────────┐               │
  │ Readiness Assessment  │              │  Evaluates readiness
  └──────────┬───────────┘               │
             ▼                           │
  ┌──────────────────────┐  Not ready    │
  │  Readiness Router     │──────────────┘
  └──────────┬───────────┘
             │ Ready
             ▼
  ┌──────────────────────┐
  │    Exam Planner       │  Plans exam via Microsoft Learn MCP
  └──────────────────────┘

Hosted on port 8088 via the Azure AI AgentServer adapter.
"""

import asyncio
import logging
import os

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

from agent_framework import WorkflowBuilder
from agent_framework._workflows._checkpoint import InMemoryCheckpointStorage
from azure.ai.agentserver.agentframework import from_agent_framework
from azure.ai.agentserver.agentframework.persistence.agent_thread_repository import (
    InMemoryAgentThreadRepository,
)
from azure.ai.agentserver.agentframework.persistence.checkpoint_repository import (
    InMemoryCheckpointRepository,
)

from agents.dispatcher import create_dispatcher
from agents.learning_path_curator import create_learning_path_curator
from agents.study_plan_generator import create_study_plan_generator
from agents.engagement_agent import create_engagement_agent
from agents.assessment_gate import create_assessment_gate
from agents.readiness_assessment import create_readiness_assessment
from agents.exam_planner import create_exam_planner
from agents.readiness_router import create_readiness_router

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Environment
# ---------------------------------------------------------------------------
# load_dotenv(override=False) so Foundry-injected env vars take precedence
load_dotenv(override=False)


def _get_openai_client():
    """Create an OpenAI client from the Foundry project using DefaultAzureCredential."""
    endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT") or os.environ.get(
        "AZURE_EXISTING_AIPROJECT_ENDPOINT"
    )
    if not endpoint:
        raise EnvironmentError(
            "FOUNDRY_PROJECT_ENDPOINT or AZURE_EXISTING_AIPROJECT_ENDPOINT must be set."
        )

    credential = DefaultAzureCredential()
    project_client = AIProjectClient(endpoint=endpoint, credential=credential)
    return project_client.get_openai_client()


def create_workflow_builder():
    """Build the full multi-agent workflow graph.

    Returns a WorkflowBuilder (not yet built) so the hosting adapter can
    manage the lifecycle.
    """
    openai_client = _get_openai_client()

    # --- Create all executors ------------------------------------------------
    dispatcher = create_dispatcher(openai_client)
    learning_path_curator = create_learning_path_curator(openai_client)
    study_plan_generator = create_study_plan_generator(openai_client)
    engagement_agent = create_engagement_agent(openai_client)
    assessment_gate = create_assessment_gate(openai_client)
    readiness_assessment = create_readiness_assessment(openai_client)
    readiness_router = create_readiness_router()
    exam_planner = create_exam_planner(openai_client)

    # --- Wire the workflow graph ---------------------------------------------
    # Sequential: Dispatcher → Learning Path Curator → Study Plan Generator
    #             → Engagement Agent → Assessment Gate (HITL)
    # After HITL:
    #   Assessment Gate (ready=True)  → Readiness Assessment → Router
    #   Assessment Gate (ready=False) → Engagement Agent (loop)
    # Router:
    #   Ready     → Exam Planner (terminal)
    #   Not Ready → Engagement Agent (loop)

    builder = (
        WorkflowBuilder()
        .with_checkpointing(InMemoryCheckpointStorage())
        .set_start_executor(dispatcher)
        # Sequential subworkflow
        .add_edge(dispatcher, learning_path_curator)
        .add_edge(learning_path_curator, study_plan_generator)
        .add_edge(study_plan_generator, engagement_agent)
        .add_edge(engagement_agent, assessment_gate)
        # After HITL → readiness assessment (assessment_gate routes internally)
        .add_edge(assessment_gate, readiness_assessment)
        .add_edge(assessment_gate, engagement_agent)   # loop-back edge
        # Readiness assessment → router → exam planner or engagement agent
        .add_edge(readiness_assessment, readiness_router)
        .add_edge(readiness_router, exam_planner)
        .add_edge(readiness_router, engagement_agent)  # loop-back edge
    )

    return builder


def main():
    """Start the hosted agent workflow on port 8088."""
    logger.info("Building Student Certification Readiness workflow...")
    builder = create_workflow_builder()

    logger.info("Starting hosted agent server on http://0.0.0.0:8088 ...")
    from_agent_framework(
        builder,
        thread_repository=InMemoryAgentThreadRepository(),
        checkpoint_repository=InMemoryCheckpointRepository(),
    ).run()


if __name__ == "__main__":
    main()
