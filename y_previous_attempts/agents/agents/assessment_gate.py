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

from agent_framework import Executor, WorkflowContext, handler


class AssessmentGateExecutor(Executor):
    """
    Human-in-the-loop gate between the study subworkflow and the assessment.
    Uses request_info to pause and wait for student confirmation.
    """

    def __init__(self, *, id: str = "assessment-gate") -> None:
        super().__init__(id=id)

    @handler
    async def gate(self, context_text: str, ctx: WorkflowContext[str]) -> None:
        """
        Show the student a summary of their preparation materials and ask if
        they feel ready to be assessed. Route appropriately based on their answer.
        """
        # Trim the context to a brief preview for the prompt
        preview = context_text[:600].strip() + ("..." if len(context_text) > 600 else "")

        response = await ctx.request_info(
            message=(
                "✅ **Your preparation materials are ready!**\n\n"
                f"Here is a preview of what was prepared for you:\n\n"
                f"{preview}\n\n"
                "---\n"
                "🎯 **Are you ready to take the readiness assessment?**\n"
                "Type **yes** to proceed to the quiz, or **no** to go back and "
                "review additional topics."
            )
        )

        answer = (response or "").strip().lower()
        if answer in ("yes", "y", "sure", "ready", "ok", "yep", "1", "proceed"):
            # Student is ready — forward full context to assessment
            await ctx.send_message(f"ASSESSMENT_READY: {context_text}")
        else:
            # Student wants more time — ask what they want to study next
            follow_up = await ctx.request_info(
                message=(
                    "No problem! 📚 Take all the time you need.\n\n"
                    "What additional topics would you like to study? "
                    "Describe them below and we will generate a new study plan for you."
                )
            )
            await ctx.send_message(f"REVISIT: {follow_up or 'I need more time to study.'}")
