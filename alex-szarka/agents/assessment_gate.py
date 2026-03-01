# Copyright (c) Microsoft. All rights reserved.
"""Assessment Gate — Human-in-the-Loop checkpoint.

Calls the Foundry assessment-gate agent to summarize student progress,
then pauses the workflow via ctx.request_info() to ask the student
whether they are ready to be assessed.
"""

import json
import logging
from dataclasses import dataclass

from agent_framework import Executor, WorkflowContext, handler, response_handler
from agents.foundry_agent_executor import AgentOutput

logger = logging.getLogger(__name__)

AGENT_NAME = "assessment-gate"
AGENT_VERSION = "3"


@dataclass
class AssessmentGateRequest:
    """HITL request payload — sent to the student for a readiness decision."""
    summary: str
    question: str = "Based on the study material above, do you feel ready to be assessed? (yes/no)"

    def convert_to_payload(self) -> str:
        return json.dumps({
            "summary": self.summary,
            "question": self.question,
        })


@dataclass
class AssessmentGateResponse:
    """HITL response payload — student's answer."""
    ready: bool
    feedback: str = ""

    @staticmethod
    def convert_from_payload(payload: str) -> "AssessmentGateResponse":
        data = json.loads(payload)
        return AssessmentGateResponse(
            ready=data.get("ready", False),
            feedback=data.get("feedback", ""),
        )


def create_assessment_gate(openai_client) -> "AssessmentGateExecutor":
    """Create the assessment gate HITL executor."""
    return AssessmentGateExecutor(openai_client=openai_client)


class AssessmentGateExecutor(Executor):
    """Executor that gates the workflow with a human-in-the-loop readiness check.

    Flow:
    1. Receives output from the Engagement Agent
    2. Calls the Foundry assessment-gate agent to produce a progress summary
    3. Pauses workflow via ctx.request_info(), exposing the summary + question
       as a function_call to the client
    4. When the student responds, routes to either:
       - readiness-assessment (if ready=True)
       - engagement-agent (if ready=False, loop back)
    """

    def __init__(self, openai_client) -> None:
        super().__init__(id="assessment-gate")
        self._openai_client = openai_client

    @handler
    async def handle_engagement_output(
        self, input_data: AgentOutput, ctx: WorkflowContext[AgentOutput]
    ) -> None:
        """Receive engagement agent output, summarize progress, ask student."""
        logger.info("[assessment-gate] Received engagement output, calling Foundry agent...")

        # Call the Foundry assessment-gate agent to summarize progress
        response = self._openai_client.responses.create(
            input=[{"role": "user", "content": input_data.text}],
            extra_body={
                "agent": {
                    "name": AGENT_NAME,
                    "version": AGENT_VERSION,
                    "type": "agent_reference",
                }
            },
        )

        summary = response.output_text
        logger.info(f"[assessment-gate] Progress summary: {summary[:100]}...")

        # Pause the workflow — HITL: ask the student if they're ready
        await ctx.request_info(
            request_data=AssessmentGateRequest(summary=summary),
            response_type=AssessmentGateResponse,
        )

    @response_handler
    async def handle_student_response(
        self,
        original_request: AssessmentGateRequest,
        response: AssessmentGateResponse,
        ctx: WorkflowContext[AgentOutput],
    ) -> None:
        """Process the student's readiness decision and route accordingly."""
        logger.info(
            f"[assessment-gate] Student response: ready={response.ready}, "
            f"feedback='{response.feedback}'"
        )

        if response.ready:
            # Student is ready — forward summary to readiness-assessment
            logger.info("[assessment-gate] Student is ready. Routing to readiness-assessment.")
            assessment_prompt = (
                f"The student has indicated they feel ready for their certification exam. "
                f"Based on the progress summary below, conduct a readiness assessment. "
                f"After your assessment, include a clear verdict: "
                f"either 'The student is ready for the exam' or "
                f"'The student is not yet ready for the exam'.\n\n"
                f"Student progress summary:\n{original_request.summary}"
            )
            await ctx.send_message(
                AgentOutput(
                    text=assessment_prompt,
                    agent_name="assessment-gate",
                ),
                target_id="readiness-assessment",
            )
        else:
            # Student is not ready — loop back to engagement-agent with feedback
            feedback_text = response.feedback or "The student needs more study time."
            logger.info("[assessment-gate] Not ready. Routing back to engagement-agent.")
            await ctx.send_message(
                AgentOutput(
                    text=(
                        f"The student is not yet ready for assessment. "
                        f"Feedback: {feedback_text}\n\n"
                        f"Previous progress summary:\n{original_request.summary}\n\n"
                        f"Please continue helping the student prepare."
                    ),
                    agent_name="assessment-gate",
                ),
                target_id="engagement-agent",
            )

