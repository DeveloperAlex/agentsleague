# Copyright (c) Microsoft. All rights reserved.
"""
Dispatcher — entry point of the workflow.

Receives the raw student input (topics they wish to learn) and uses a
Foundry LLM agent to extract a clean, structured message that is forwarded
to the sequential Student Readiness Subworkflow.
"""

import json
import logging

from agent_framework import Executor, WorkflowContext, handler

from .foundry_helpers import create_foundry_agent, invoke_foundry_agent

logger = logging.getLogger(__name__)

DISPATCHER_INSTRUCTIONS = """\
You are an intelligent dispatcher for a student certification readiness system.

Your job is to parse the student's free-text input and return a concise, structured
summary of:
1. The Microsoft technologies / topics the student wants to learn.
2. Any stated experience level (beginner / intermediate / advanced). Default to
   "beginner" if not mentioned.
3. Any stated time-frame or deadline (e.g. "in 3 months"). Default to "flexible"
   if not mentioned.

Respond ONLY with a JSON object in this exact format (no markdown, no extra text):
{
  "topics": ["<topic1>", "<topic2>"],
  "experience_level": "<beginner|intermediate|advanced>",
  "timeframe": "<timeframe or 'flexible'>"
}
"""


class DispatcherExecutor(Executor):
    """
    Receives a raw string from the student, extracts structured topics via a
    Foundry agent, and forwards a formatted message downstream.
    """

    def __init__(
        self,
        *,
        id: str = "dispatcher",
        model: str,
    ) -> None:
        super().__init__(id=id)
        self._model = model
        self._agent_name: str | None = None

    def _ensure_agent(self) -> str:
        if self._agent_name is None:
            self._agent_name = create_foundry_agent(
                name="dispatcher",
                model=self._model,
                instructions=DISPATCHER_INSTRUCTIONS,
            )
        return self._agent_name

    @handler
    async def dispatch(self, text: str, ctx: WorkflowContext[str]) -> None:
        """
        Parse the student's raw input and emit a structured prompt.

        Handles loopback prefixes:
        - "REVISIT: <hint>"      → user wants to revisit topics
        - "NOT_READY: <json>"    → failed readiness assessment
        """
        # ── Normalise loopback inputs ──────────────────────────────────
        if text.startswith("REVISIT: "):
            text = text[len("REVISIT: "):]
        elif text.startswith("NOT_READY: "):
            try:
                data = json.loads(text[len("NOT_READY: "):])
                feedback = data.get("feedback", "")
                text = (
                    f"The student did not pass the previous assessment. "
                    f"Assessment feedback: {feedback}. "
                    f"Please help them revisit and strengthen their knowledge."
                )
            except Exception:
                text = "The student needs to revisit their study topics."

        # ── Invoke Foundry agent ───────────────────────────────────────
        agent_name = self._ensure_agent()
        raw = invoke_foundry_agent(agent_name, text)

        try:
            parsed = json.loads(raw)
            topics = parsed.get("topics", [text])
            level = parsed.get("experience_level", "beginner")
            timeframe = parsed.get("timeframe", "flexible")
        except (json.JSONDecodeError, AttributeError):
            topics = [text]
            level = "beginner"
            timeframe = "flexible"

        structured_prompt = (
            f"Student learning request:\n"
            f"- Topics: {', '.join(topics)}\n"
            f"- Experience level: {level}\n"
            f"- Timeframe: {timeframe}\n\n"
            f"Please begin the student readiness workflow."
        )
        await ctx.send_message(structured_prompt)
