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
import logging

from agent_framework import Executor, WorkflowContext, handler

from .foundry_helpers import create_foundry_agent, invoke_foundry_agent

logger = logging.getLogger(__name__)

QUIZ_GENERATOR_INSTRUCTIONS = """\
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

EVALUATOR_INSTRUCTIONS = """\
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


class ReadinessAssessmentExecutor(Executor):
    """
    Orchestrates quiz generation, delivery (via request_info), and evaluation.
    Emits READY or NOT_READY downstream.
    """

    def __init__(
        self,
        *,
        id: str = "readiness-assessment",
        model: str,
    ) -> None:
        super().__init__(id=id)
        self._model = model
        self._quiz_agent_name: str | None = None
        self._eval_agent_name: str | None = None

    def _ensure_quiz_agent(self) -> str:
        if self._quiz_agent_name is None:
            self._quiz_agent_name = create_foundry_agent(
                name="quiz-generator",
                model=self._model,
                instructions=QUIZ_GENERATOR_INSTRUCTIONS,
            )
        return self._quiz_agent_name

    def _ensure_eval_agent(self) -> str:
        if self._eval_agent_name is None:
            self._eval_agent_name = create_foundry_agent(
                name="readiness-evaluator",
                model=self._model,
                instructions=EVALUATOR_INSTRUCTIONS,
            )
        return self._eval_agent_name

    @handler
    async def assess(self, raw_input: str, ctx: WorkflowContext[str]) -> None:
        PREFIX = "ASSESSMENT_READY: "
        context_text = raw_input[len(PREFIX):] if raw_input.startswith(PREFIX) else raw_input

        # ── Step 1: Generate the quiz ──────────────────────────────────
        quiz_agent_name = self._ensure_quiz_agent()
        quiz_raw = invoke_foundry_agent(
            quiz_agent_name,
            f"Generate a readiness quiz based on this study context:\n\n{context_text}",
        )

        try:
            questions = json.loads(quiz_raw)
        except (json.JSONDecodeError, ValueError):
            questions = []

        if not questions:
            await ctx.send_message(
                "NOT_READY: " + json.dumps({
                    "ready": False, "score": 0,
                    "feedback": "Could not generate quiz. Please try again.",
                    "context": context_text,
                })
            )
            return

        # ── Step 2: Auto-answer for demo (HITL would pause here) ──────
        # In production, use the Agent Framework HITL callback mechanism
        # to present the quiz and collect real student answers.
        student_answers = ", ".join(
            q.get("correct_answer", "A") for q in questions
        )
        logger.info("Readiness assessment: auto-answering quiz for demo")

        # ── Step 3: Evaluate answers ──────────────────────────────────
        eval_agent_name = self._ensure_eval_agent()
        eval_input = (
            f"Quiz questions (JSON):\n{json.dumps(questions, indent=2)}\n\n"
            f"Student answers: {student_answers}"
        )
        eval_raw = invoke_foundry_agent(eval_agent_name, eval_input)

        try:
            result_dict = json.loads(eval_raw)
        except (json.JSONDecodeError, ValueError):
            result_dict = {
                "score": 0,
                "ready": False,
                "feedback": "Could not evaluate answers.",
            }

        ready = bool(result_dict.get("ready", False))
        score = int(result_dict.get("score", 0))
        feedback = str(result_dict.get("feedback", ""))

        prefix = "READY" if ready else "NOT_READY"
        payload = json.dumps({
            "ready": ready,
            "score": score,
            "feedback": feedback,
            "context": context_text,
        })
        await ctx.send_message(f"{prefix}: {payload}")


def _format_quiz_for_display(questions: list[dict]) -> str:
    """Format quiz questions for human-readable display."""
    lines: list[str] = []
    for i, q in enumerate(questions, start=1):
        lines.append(f"**Q{i}.** {q.get('question', '')}")
        for opt in q.get("options", []):
            lines.append(f"   {opt}")
        lines.append("")
    return "\n".join(lines)
