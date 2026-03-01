# Copyright (c) Microsoft. All rights reserved.
"""
Readiness Assessment Agent (Executor).

After the student signals they are ready, this executor:
1. Generates a short quiz (5 questions) grounded in the study plan topics.
2. Asks the questions interactively via the human-in-the-loop mechanism.
3. Evaluates the answers and produces a readiness verdict.

The verdict is forwarded downstream as a structured dict:
    {"ready": True/False, "score": N, "feedback": "..."}

If ready=True  → Exam Planner is invoked.
If ready=False → Loop back to the Dispatcher subworkflow.
"""
import json
from dataclasses import dataclass
from typing import Any

from agent_framework import Executor, WorkflowContext, handler
from agent_framework.azure import AzureOpenAIChatClient


QUIZ_GENERATOR_INSTRUCTIONS = """
You are a Microsoft certification readiness assessor.

You will receive the student's study plan context. Generate exactly 5 multiple-choice
questions that test understanding of the core concepts from that study plan.

Respond ONLY with a JSON array in this format (no markdown, no extra text):
[
  {
    "question": "<question text>",
    "options": ["A) ...", "B) ...", "C) ...", "D) ..."],
    "correct_answer": "A"
  },
  ...
]
"""

EVALUATOR_INSTRUCTIONS = """
You are a strict but fair Microsoft certification readiness evaluator.

You will receive:
1. The original quiz questions (JSON).
2. The student's answers (one letter per question, comma-separated).

Evaluate each answer, compute the score out of 5, and respond ONLY with JSON:
{
  "score": <0-5>,
  "ready": <true if score >= 3, false otherwise>,
  "per_question": [
    {"question": "...", "correct": "A", "student_answer": "B", "passed": false},
    ...
  ],
  "feedback": "<2-3 sentence motivational summary>"
}
"""


@dataclass
class AssessmentResult:
    ready: bool
    score: int
    feedback: str
    raw: dict[str, Any]


class ReadinessAssessmentExecutor(Executor):
    """
    Orchestrates quiz generation, delivery (via request_info), and evaluation.
    Emits a structured AssessmentResult downstream.
    """

    def __init__(self, *, id: str = "readiness-assessment") -> None:
        super().__init__(id=id)

    def _get_client(self) -> AzureOpenAIChatClient:
        from azure.identity import DefaultAzureCredential, get_bearer_token_provider

        credential = DefaultAzureCredential()
        token_provider = get_bearer_token_provider(
            credential, "https://cognitiveservices.azure.com/.default"
        )
        return AzureOpenAIChatClient(ad_token_provider=token_provider)

    # ------------------------------------------------------------------
    # Handler: receives the prefixed string from AssessmentGateExecutor
    # ------------------------------------------------------------------
    @handler
    async def assess(self, raw_input: str, ctx: WorkflowContext[str]) -> None:
        # Strip the routing prefix added by AssessmentGateExecutor
        PREFIX = "ASSESSMENT_READY: "
        context_text = raw_input[len(PREFIX):] if raw_input.startswith(PREFIX) else raw_input
        client = self._get_client()

        # ── Step 1: Generate the quiz ──────────────────────────────────
        quiz_agent = client.create_agent(
            name="quiz-generator",
            instructions=QUIZ_GENERATOR_INSTRUCTIONS,
        )
        quiz_response = await quiz_agent.run(
            f"Generate a readiness quiz based on this study context:\n\n{context_text}"
        )
        quiz_raw = quiz_response.messages[-1].text if quiz_response.messages else "[]"

        try:
            questions = json.loads(quiz_raw)
        except (json.JSONDecodeError, ValueError):
            questions = []

        # ── Step 2: Present the quiz to the student (HITL request_info) ─
        quiz_display = _format_quiz_for_display(questions)
        student_answers = await ctx.request_info(
            message=(
                "📝 **Readiness Assessment**\n\n"
                "Please answer the following questions by providing your answers "
                "as a comma-separated list (e.g. A, B, C, D, A).\n\n"
                + quiz_display
            )
        )

        # ── Step 3: Evaluate answers ───────────────────────────────────
        eval_agent = client.create_agent(
            name="readiness-evaluator",
            instructions=EVALUATOR_INSTRUCTIONS,
        )
        eval_input = (
            f"Quiz questions (JSON):\n{json.dumps(questions, indent=2)}\n\n"
            f"Student answers: {student_answers}"
        )
        eval_response = await eval_agent.run(eval_input)
        eval_raw = eval_response.messages[-1].text if eval_response.messages else "{}"

        try:
            result_dict = json.loads(eval_raw)
        except (json.JSONDecodeError, ValueError):
            result_dict = {"score": 0, "ready": False, "feedback": "Could not evaluate answers."}

        result = AssessmentResult(
            ready=bool(result_dict.get("ready", False)),
            score=int(result_dict.get("score", 0)),
            feedback=str(result_dict.get("feedback", "")),
            raw=result_dict,
        )

        # Emit a JSON string so the WorkflowBuilder routing selector can parse it.
        # Format: READY: <json>  or  NOT_READY: <json>
        prefix = "READY" if result.ready else "NOT_READY"
        payload = json.dumps(
            {
                "ready": result.ready,
                "score": result.score,
                "feedback": result.feedback,
                "context": context_text,
            }
        )
        await ctx.send_message(f"{prefix}: {payload}")


# ── Helpers ────────────────────────────────────────────────────────────────────

def _format_quiz_for_display(questions: list[dict]) -> str:
    lines = []
    for i, q in enumerate(questions, start=1):
        lines.append(f"**Q{i}.** {q.get('question', '')}")
        for opt in q.get("options", []):
            lines.append(f"   {opt}")
        lines.append("")
    return "\n".join(lines)
