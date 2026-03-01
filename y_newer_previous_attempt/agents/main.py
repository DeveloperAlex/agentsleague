# Copyright (c) Microsoft. All rights reserved.
"""
Student Certification Readiness — Multi-Agent System
=====================================================

Architecture (see reasoning-agents-architecture.png):

  [Student input]
       │
  DispatcherExecutor              ← extract structured topics (Foundry agent)
       │
  ─── Sequential Student Readiness Subworkflow ───────────────────────────────
  │  LearningPathCuratorExecutor  ← queries MS Learn MCP (Foundry agent)      │
  │       │                                                                    │
  │  StudyPlanGeneratorExecutor   ← builds week-by-week study plan             │
  │       │                                                                    │
  │  EngagementExecutor           ← creates reminders & schedule               │
  ────────────────────────────────────────────────────────────────────────────
       │
  AssessmentGateExecutor          ← HITL: "Ready to be assessed?" (yes/no)
       │
  ReadinessAssessmentExecutor     ← generates quiz, scores, emits READY/NOT_READY
       │                │
  ExamPlannerExecutor   └──── NOT_READY ──→ DispatcherExecutor (loop)
  (MS Learn MCP)
       │
  [Exam planning output]

All agents are created in Microsoft Foundry via AIProjectClient and are visible
in the Foundry portal.  The workflow is orchestrated locally using the Microsoft
Agent Framework and served as an HTTP endpoint via the hosting adapter.

Run:  python main.py       (starts HTTP server on port 8088)
Env:  copy .env.example → .env and fill in values
"""

import asyncio
import logging
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv(override=False)

from agent_framework import WorkflowBuilder
from azure.ai.agentserver.core import FoundryCBAgent, AgentRunContext
from azure.ai.agentserver.core.models.projects._models import (
    Response,
    ResponsesAssistantMessageItemResource,
    ItemContentOutputText,
)

from agents.dispatcher import DispatcherExecutor
from agents.learning_path_curator import LearningPathCuratorExecutor
from agents.study_plan_generator import StudyPlanGeneratorExecutor
from agents.engagement_agent import EngagementExecutor
from agents.assessment_gate import AssessmentGateExecutor
from agents.readiness_assessment import ReadinessAssessmentExecutor
from agents.exam_planner import ExamPlannerExecutor

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)

# Suppress noisy INFO logs from azure.identity (irrelevant when using API key)
logging.getLogger("azure.identity").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
PROJECT_ENDPOINT = os.environ.get(
    "FOUNDRY_PROJECT_ENDPOINT",
    "https://buildathon2026c-resource.services.ai.azure.com/api/projects/buildathon2026c",
)
MODEL = os.environ.get("FOUNDRY_MODEL_DEPLOYMENT_NAME", "gpt-5-nano")


# ---------------------------------------------------------------------------
# Routing helpers
# ---------------------------------------------------------------------------

def route_after_gate(message: str, target_ids: list[str]) -> list[str]:
    """After the HITL gate: ASSESSMENT_READY → assessment, else → dispatcher."""
    if message.startswith("ASSESSMENT_READY:"):
        return [t for t in target_ids if t == "readiness-assessment"]
    return [t for t in target_ids if t == "dispatcher"]


def route_after_assessment(message: str, target_ids: list[str]) -> list[str]:
    """After assessment: READY → exam-planner, NOT_READY → dispatcher."""
    if message.startswith("READY:"):
        return [t for t in target_ids if t == "exam-planner"]
    return [t for t in target_ids if t == "dispatcher"]


# ---------------------------------------------------------------------------
# Workflow builder
# ---------------------------------------------------------------------------

def build_workflow():
    """Construct the full multi-agent workflow."""
    common = {"model": MODEL}

    # ── Executors ──────────────────────────────────────────────────────
    dispatcher = DispatcherExecutor(id="dispatcher", **common)
    curator = LearningPathCuratorExecutor(id="learning-path-curator", **common)
    study_plan = StudyPlanGeneratorExecutor(id="study-plan-generator", **common)
    engagement = EngagementExecutor(id="engagement-agent", **common)
    hitl_gate = AssessmentGateExecutor(id="assessment-gate")
    assessment = ReadinessAssessmentExecutor(id="readiness-assessment", **common)
    exam_planner = ExamPlannerExecutor(id="exam-planner", **common)

    # ── Wire the workflow ──────────────────────────────────────────────
    workflow = (
        WorkflowBuilder(start_executor=dispatcher, max_iterations=20)
        # Sequential subworkflow: dispatcher → curator → study_plan → engagement
        .add_chain([dispatcher, curator, study_plan, engagement])
        # engagement → HITL gate (always)
        .add_multi_selection_edge_group(
            engagement,
            targets=[hitl_gate, dispatcher],
            selection_func=lambda msg, ids: [t for t in ids if t == "assessment-gate"],
        )
        # HITL gate → assessment OR dispatcher (loopback)
        .add_multi_selection_edge_group(
            hitl_gate,
            targets=[assessment, dispatcher],
            selection_func=route_after_gate,
        )
        # assessment → exam-planner OR dispatcher (loopback)
        .add_multi_selection_edge_group(
            assessment,
            targets=[exam_planner, dispatcher],
            selection_func=route_after_assessment,
        )
        .build()
    )

    logger.info("Workflow built successfully with %d executors", 7)
    logger.info("Foundry project: %s", PROJECT_ENDPOINT)
    logger.info("Model deployment: %s", MODEL)
    return workflow


# ---------------------------------------------------------------------------
# Foundry hosting adapter (wraps Agent Framework workflow as HTTP endpoint)
# ---------------------------------------------------------------------------

class StudentCertAgent(FoundryCBAgent):
    """Wraps the multi-agent workflow so it can be served via the
    Foundry Responses API on port 8088."""

    def __init__(self):
        super().__init__()
        self._workflow = build_workflow()

    async def agent_run(self, context: AgentRunContext) -> Response:
        """Handle a single /responses request."""
        # Extract the user's input text from the Responses payload
        request = context.request
        raw_input = request.get("input", "")
        if isinstance(raw_input, list):
            # Responses API may send structured input items
            parts = []
            for item in raw_input:
                if isinstance(item, dict):
                    parts.append(item.get("text", str(item)))
                else:
                    parts.append(str(item))
            input_text = "\n".join(parts)
        else:
            input_text = str(raw_input)

        logger.info("Received input: %s", input_text[:200])

        # Run the Agent Framework workflow
        result = await self._workflow.run(message=input_text, stream=False)

        # Collect meaningful outputs from workflow events.
        # "get_outputs()" only returns terminal-executor output, which may be
        # empty.  Walk all events instead and gather executor_completed data.
        sections: list[str] = []
        for event in result:
            etype = getattr(event, "type", "")
            if etype == "executor_completed":
                eid = getattr(event, "executor_id", "")
                data = getattr(event, "data", None)
                if isinstance(data, list):
                    texts = [str(d) for d in data if d]
                elif data:
                    texts = [str(data)]
                else:
                    texts = []
                for t in texts:
                    if t.strip():
                        sections.append(f"### {eid}\n{t}")

        if sections:
            output_text = "\n\n---\n\n".join(sections)
        else:
            output_text = "Workflow completed but produced no text output."

        # Build a Responses-compatible Response object
        response = Response(
            id=f"resp_{uuid.uuid4().hex[:12]}",
            output=[
                ResponsesAssistantMessageItemResource(
                    type="message",
                    role="assistant",
                    content=[
                        ItemContentOutputText(
                            text=output_text,
                            type="output_text",
                        )
                    ],
                    id=f"msg_{uuid.uuid4().hex[:12]}",
                    status="completed",
                )
            ],
            status="completed",
        )
        return response


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    print(
        "\n🎓 Student Certification Readiness Agent\n"
        "   Serving on http://localhost:8022\n"
        "   POST http://localhost:8022/responses  "
        '{"input": "I want to learn Azure fundamentals"}\n'
    )
    agent = StudentCertAgent()
    agent.run(port=8022)


if __name__ == "__main__":
    main()
