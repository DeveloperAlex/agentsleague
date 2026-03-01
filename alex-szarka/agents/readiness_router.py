# Copyright (c) Microsoft. All rights reserved.
"""Readiness Router — deterministic executor that routes based on assessment verdict.

Parses the readiness-assessment agent's output and routes to either:
- exam-planner (if the student is ready)
- engagement-agent (if the student is not ready, creating a loop)
"""

import logging

from agent_framework import Executor, WorkflowContext, handler
from agents.foundry_agent_executor import AgentOutput

logger = logging.getLogger(__name__)


def create_readiness_router() -> "ReadinessRouterExecutor":
    """Create the readiness router executor."""
    return ReadinessRouterExecutor()


class ReadinessRouterExecutor(Executor):
    """Deterministic router — no LLM call, just keyword-based routing."""

    def __init__(self) -> None:
        super().__init__(id="readiness-router")

    @handler
    async def route(self, input_data: AgentOutput, ctx: WorkflowContext[AgentOutput]) -> None:
        """Parse readiness assessment output and route accordingly."""
        text_lower = input_data.text.lower()
        logger.info(f"[readiness-router] Evaluating assessment: {input_data.text[:100]}...")

        # Check for explicit "not ready" signals first
        not_ready_signals = [
            "not yet ready", "not prepared",
            "insufficient preparation", "recommend additional study",
            "significant gaps", "weak areas remain",
        ]
        has_not_ready = any(s in text_lower for s in not_ready_signals)

        # Check for positive readiness signals (explicit verdict)
        ready_signals = [
            "ready for the exam", "student is ready", "prepared for the exam",
            "recommend proceeding", "cleared for the exam", "ready to sit",
            "confident in readiness", "meets the criteria", "sufficient preparation",
            "well-prepared", "demonstrates readiness", "ready to take",
        ]
        has_ready = any(s in text_lower for s in ready_signals)

        # Also detect structured assessment output (quiz questions from the
        # Foundry readiness-assessment agent).  If the agent produced a full
        # assessment (JSON questions with options), the evaluation was completed
        # successfully — treat as the student being ready to proceed.
        has_structured_assessment = (
            '"question"' in text_lower and '"options"' in text_lower
        )

        # Ready if: structured assessment was produced (quiz with questions/options
        # indicates the Foundry readiness-assessment agent completed its evaluation),
        # OR an explicit positive signal was found without contradiction.
        # Structured assessment takes priority — quiz answer options may contain
        # "not ready" keywords that would otherwise trigger a false negative.
        is_ready = has_structured_assessment or (has_ready and not has_not_ready)
        logger.info(
            f"[readiness-router] Decision: is_ready={is_ready} "
            f"(ready_signal={has_ready}, structured_assessment={has_structured_assessment}, "
            f"not_ready_signal={has_not_ready})"
        )

        if is_ready:
            logger.info("[readiness-router] Student IS ready → routing to exam-planner.")
            await ctx.send_message(
                AgentOutput(
                    text=(
                        f"The student has been assessed and is READY for the exam.\n\n"
                        f"Assessment details:\n{input_data.text}\n\n"
                        f"Please help plan the exam logistics and preparation."
                    ),
                    agent_name="readiness-router",
                ),
                target_id="exam-planner",
            )
        else:
            logger.info("[readiness-router] Student NOT ready → routing back to engagement-agent.")
            await ctx.send_message(
                AgentOutput(
                    text=(
                        f"The student has been assessed and is NOT YET READY.\n\n"
                        f"Assessment details:\n{input_data.text}\n\n"
                        f"Please continue helping the student strengthen their weak areas."
                    ),
                    agent_name="readiness-router",
                ),
                target_id="engagement-agent",
            )
