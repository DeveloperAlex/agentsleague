# Copyright (c) Microsoft. All rights reserved.
"""
Student Certification Readiness — Multi-Agent System
=====================================================

Architecture (see reasoning-agents-architecture.png):

  [Student input]
       │
  DispatcherExecutor              ← extract structured topics
       │
  ─── Sequential Student Readiness Subworkflow ───────────────────────────────
  │  LearningPathCuratorAgent     ← queries Microsoft Learn MCP               │
  │       │                                                                    │
  │  StudyPlanGeneratorAgent      ← builds week-by-week study plan             │
  │       │                                                                    │
  │  EngagementAgent              ← creates reminders & schedule               │
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

Dependencies: agent-framework, azure-ai-agentserver-agentframework, azure-identity, python-dotenv
Run locally : python main.py        (starts HTTP server on port 8088)
Environment : copy .env.example → .env and fill in FOUNDRY_PROJECT_ENDPOINT, FOUNDRY_MODEL_DEPLOYMENT_NAME
"""

import json
import os

from dotenv import load_dotenv

# Load .env BEFORE importing Azure identity so env vars are available
load_dotenv(override=False)

from azure.identity import DefaultAzureCredential, get_bearer_token_provider  # noqa: E402
from agent_framework import Executor, WorkflowBuilder, WorkflowContext, handler  # noqa: E402
from azure.ai.agentserver.agentframework import from_agent_framework  # noqa: E402

from agents.dispatcher import DispatcherExecutor  # noqa: E402
from agents.learning_path_curator import create_learning_path_curator  # noqa: E402
from agents.study_plan_generator import create_study_plan_generator  # noqa: E402
from agents.engagement_agent import create_engagement_agent  # noqa: E402
from agents.assessment_gate import AssessmentGateExecutor  # noqa: E402
from agents.readiness_assessment_agent import ReadinessAssessmentExecutor  # noqa: E402
from agents.exam_planner import create_exam_planner  # noqa: E402


# ── Shared token provider (refreshes automatically in long-running servers) ────

_credential = DefaultAzureCredential()
_token_provider = get_bearer_token_provider(
    _credential, "https://cognitiveservices.azure.com/.default"
)


# ── Agent-wrapping helper ──────────────────────────────────────────────────────

def make_agent_executor(agent, executor_id: str) -> Executor:
    """
    Wrap a `create_agent()` / `as_agent()` agent as a simple str-in / str-out
    Executor so that it plays nicely with the str-typed custom executors in this
    workflow.  The agent's full text response becomes the output string.
    """

    class _AgentWrapperExecutor(Executor):
        def __init__(self) -> None:
            super().__init__(id=executor_id)
            self._agent = agent

        @handler
        async def run_agent(self, context: str, ctx: WorkflowContext[str]) -> None:
            response = await self._agent.run(context)
            text = response.messages[-1].text if response.messages else ""
            await ctx.send_message(text)

    return _AgentWrapperExecutor()


# ── Exam-planner executor (strips READY prefix, calls exam planner) ────────────

class ExamPlannerExecutor(Executor):
    """
    Receives "READY: {json}" from ReadinessAssessmentExecutor, extracts the
    study context, and invokes the Exam Planner agent (with MS Learn MCP).
    """

    def __init__(self, token_provider, *, id: str = "exam-planner") -> None:
        super().__init__(id=id)
        self._token_provider = token_provider
        self._agent = None  # lazy-init avoids credential issues at import time

    def _get_agent(self):
        if self._agent is None:
            self._agent = create_exam_planner(self._token_provider)
        return self._agent

    @handler
    async def plan_exam(self, raw_input: str, ctx: WorkflowContext[str]) -> None:
        # Strip routing prefix
        PREFIX = "READY: "
        content = raw_input[len(PREFIX):] if raw_input.startswith(PREFIX) else raw_input

        # Parse JSON payload emitted by ReadinessAssessmentExecutor
        context_text = content
        feedback = ""
        score = 0
        try:
            data = json.loads(content)
            context_text = data.get("context", content)
            feedback = data.get("feedback", "")
            score = data.get("score", 0)
        except (json.JSONDecodeError, ValueError):
            pass

        prompt = (
            f"The student has passed their readiness assessment with a score of {score}/5.\n"
            f"Assessment feedback: {feedback}\n\n"
            f"Study context summary:\n{context_text[:1000]}\n\n"
            f"Please provide a comprehensive exam planning report, including the recommended "
            f"Microsoft certification exam, registration steps, and a final preparation checklist."
        )

        agent = self._get_agent()
        response = await agent.run(prompt)
        text = response.messages[-1].text if response.messages else ""
        await ctx.send_message(text)


# ── Routing functions ──────────────────────────────────────────────────────────

def route_after_gate(message: str, target_ids: list[str]) -> list[str]:
    """
    After AssessmentGateExecutor:
    - "ASSESSMENT_READY: ..." → ReadinessAssessmentExecutor
    - "REVISIT: ..."           → DispatcherExecutor (loop)
    """
    if message.startswith("ASSESSMENT_READY:"):
        return [t for t in target_ids if t == "readiness-assessment"]
    # default: loop back
    return [t for t in target_ids if t == "dispatcher"]


def route_after_assessment(message: str, target_ids: list[str]) -> list[str]:
    """
    After ReadinessAssessmentExecutor:
    - "READY: ..."     → ExamPlannerExecutor
    - "NOT_READY: ..." → DispatcherExecutor (loop)
    """
    if message.startswith("READY:"):
        return [t for t in target_ids if t == "exam-planner"]
    return [t for t in target_ids if t == "dispatcher"]


# ── Workflow factory ───────────────────────────────────────────────────────────

def build_workflow() -> object:
    """Assemble and return the full multi-agent certification readiness workflow."""

    # ── Instantiate all executors ────────────────────────────────────────────
    dispatcher = DispatcherExecutor(id="dispatcher")

    curator_exec = make_agent_executor(
        create_learning_path_curator(_token_provider), "learning-path-curator"
    )
    study_plan_exec = make_agent_executor(
        create_study_plan_generator(_token_provider), "study-plan-generator"
    )
    engagement_exec = make_agent_executor(
        create_engagement_agent(_token_provider), "engagement-agent"
    )

    hitl_gate = AssessmentGateExecutor(id="assessment-gate")
    assessment = ReadinessAssessmentExecutor(id="readiness-assessment")
    exam_planner = ExamPlannerExecutor(_token_provider, id="exam-planner")

    # ── Wire the workflow graph ──────────────────────────────────────────────
    #
    #   dispatcher
    #       ↓
    #   learning-path-curator (MS Learn MCP)
    #       ↓
    #   study-plan-generator
    #       ↓
    #   engagement-agent
    #       ↓
    #   assessment-gate  ──REVISIT──► dispatcher  (loop)
    #       │ASSESSMENT_READY
    #       ↓
    #   readiness-assessment  ──NOT_READY──► dispatcher  (loop)
    #       │READY
    #       ↓
    #   exam-planner (MS Learn MCP)
    #
    workflow = (
        WorkflowBuilder(start_executor=dispatcher, max_iterations=20)
        # Sequential student readiness subworkflow
        .add_chain([dispatcher, curator_exec, study_plan_exec, engagement_exec])
        # HITL gate with conditional routing
        .add_multi_selection_edge_group(
            engagement_exec,
            targets=[hitl_gate, dispatcher],
            selection_func=lambda msg, ids: [t for t in ids if t == "assessment-gate"],
        )
        # Assessment gate → assessment OR back to dispatcher
        .add_multi_selection_edge_group(
            hitl_gate,
            targets=[assessment, dispatcher],
            selection_func=route_after_gate,
        )
        # Assessment result → exam planner OR back to dispatcher
        .add_multi_selection_edge_group(
            assessment,
            targets=[exam_planner, dispatcher],
            selection_func=route_after_assessment,
        )
        .build()
    )
    return workflow


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    """Start the agent HTTP server (compatible with Foundry hosted agent deployment)."""
    workflow = build_workflow()
    print("🎓 Student Certification Readiness Agent starting on http://localhost:8088")
    from_agent_framework(workflow).run()


if __name__ == "__main__":
    main()

