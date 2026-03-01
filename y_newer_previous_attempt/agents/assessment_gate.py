# Copyright (c) Microsoft. All rights reserved.
"""
Assessment Gate — Human-in-the-Loop checkpoint.

After the sequential subworkflow completes, this executor:
- Presents a summary of the engagement package to the student.
- Asks "Are you ready to be assessed?"
- Prefixes the outbound message so the routing selector can decide:
    "ASSESSMENT_READY: <context>"  → proceed to ReadinessAssessmentExecutor
    "REVISIT: <hint>"              → loop back to DispatcherExecutor
"""

import logging

from agent_framework import Executor, WorkflowContext, handler

logger = logging.getLogger(__name__)


class AssessmentGateExecutor(Executor):
    """
    Human-in-the-loop gate between the study subworkflow and the assessment.
    Uses ``request_info`` to pause and wait for student confirmation.
    """

    def __init__(self, *, id: str = "assessment-gate") -> None:
        super().__init__(id=id)

    @handler
    async def gate(self, context_text: str, ctx: WorkflowContext[str]) -> None:
        # For demo: auto-approve the assessment gate.
        # In production, use the Agent Framework HITL callback mechanism
        # to pause here and wait for human confirmation.
        logger.info("Assessment gate: auto-approving for demo")
        await ctx.send_message(f"ASSESSMENT_READY: {context_text}")
