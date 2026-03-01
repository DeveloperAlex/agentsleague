# Copyright (c) Microsoft. All rights reserved.
"""
Dispatcher — entry point of the workflow.

Receives the raw student input (topics they wish to learn) and uses an LLM
to extract a clean, structured message that is forwarded to the sequential
Student Readiness Subworkflow.
"""
import json
import os

from agent_framework import Executor, WorkflowContext, handler
from agent_framework.azure import AzureOpenAIChatClient


DISPATCHER_INSTRUCTIONS = """
You are an intelligent dispatcher for a student certification readiness system.

Your job is to parse the student's free-text input and return a concise, structured
summary of:
1. The Microsoft technologies / topics the student wants to learn.
2. Any stated experience level (beginner / intermediate / advanced). Default to "beginner"
   if not mentioned.
3. Any stated time-frame or deadline (e.g. "in 3 months"). Default to "flexible" if not
   mentioned.

Respond ONLY with a JSON object in this exact format (no markdown, no extra text):
{
  "topics": ["<topic1>", "<topic2>"],
  "experience_level": "<beginner|intermediate|advanced>",
  "timeframe": "<timeframe or 'flexible'>"
}
"""


class DispatcherExecutor(Executor):
    """
    Receives a raw string from the student, extracts structured topics,
    and forwards a formatted message downstream to the subworkflow.
    """

    def __init__(self, *, id: str = "dispatcher") -> None:
        super().__init__(id=id)
        self._client: AzureOpenAIChatClient | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _get_client(self) -> AzureOpenAIChatClient:
        if self._client is None:
            from azure.identity import DefaultAzureCredential, get_bearer_token_provider

            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            self._client = AzureOpenAIChatClient(ad_token_provider=token_provider)
        return self._client

    # ------------------------------------------------------------------
    # Handler
    # ------------------------------------------------------------------
    @handler
    async def dispatch(self, text: str, ctx: WorkflowContext[str]) -> None:
        """
        Parse the student's raw input and emit a structured prompt for the
        downstream sequential subworkflow.

        Handles two input shapes:
        - Plain string: initial student input (topics to learn)
        - "REVISIT: <hint>" prefix: loopback after failed assessment or HITL gate decline
        - "NOT_READY: <json>" prefix: loopback after failed readiness quiz
        """
        # ── Normalise loopback inputs ──────────────────────────────────
        if text.startswith("REVISIT: "):
            # Student declined at HITL gate — use their follow-up as the topic
            text = text[len("REVISIT: "):]
        elif text.startswith("NOT_READY: "):
            # Student failed assessment — extract feedback and use as context
            import json as _json
            try:
                data = _json.loads(text[len("NOT_READY: "):])
                feedback = data.get("feedback", "")
                text = (
                    f"The student did not pass the previous assessment. "
                    f"Assessment feedback: {feedback}. "
                    f"Please help them revisit and strengthen their knowledge."
                )
            except Exception:
                text = "The student needs to revisit their study topics."
        client = self._get_client()
        agent = client.create_agent(
            name="dispatcher",
            instructions=DISPATCHER_INSTRUCTIONS,
        )

        response = await agent.run(text)
        raw = response.messages[-1].text if response.messages else "{}"

        # Attempt to parse; fall back gracefully
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
