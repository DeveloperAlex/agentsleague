# Copyright (c) Microsoft. All rights reserved.
"""
Exam Planner agent.

Triggered when the student passes the Readiness Assessment (ready=True).

Uses a Foundry agent with the Microsoft Learn MCP server tool to find the
most relevant Microsoft certification exam and returns a detailed exam
preparation and registration plan.
"""

import json
import logging
import os

from agent_framework import Executor, WorkflowContext, handler

from .foundry_helpers import create_foundry_agent, get_mcp_tools, invoke_foundry_agent

logger = logging.getLogger(__name__)

EXAM_PLANNER_INSTRUCTIONS = """\
You are a Microsoft Certification Exam Planning specialist.

You have access to the Microsoft Learn MCP server. Use it to look up the
most relevant Microsoft certification exam(s) for the student's studied topics.

Your output must cover:

## 🎓 Exam Planning Report

### Recommended Certification(s)
For each recommended certification:
- **Exam code & name**: e.g. AZ-900: Microsoft Azure Fundamentals
- **Official exam page**: <learn.microsoft.com URL>
- **Why it fits**: <one sentence>
- **Prerequisites**: <any required experience or prior certs>

### Exam Registration Steps
1. Create / log in to your Microsoft account at https://learn.microsoft.com
2. Go to the certification page linked above
3. Click "Schedule exam" and select Pearson VUE or Certiport
4. Choose online or in-person proctoring
5. Register and pay (check for Microsoft discount vouchers or ESI vouchers)

### Final Preparation Checklist (2 weeks before exam)
- [ ] Complete all learning paths in your study plan
- [ ] Take the official Microsoft practice assessment (free on Learn)
- [ ] Review the skills measured document on the exam page
- [ ] Join the Microsoft Learn community for last-minute tips
- [ ] Get a good night's sleep before the exam!

### Useful Links (retrieved via Microsoft Learn)
(Use the MCP server to find 2–3 additional relevant pages: e.g. study guide,
practice test, community forum.)

Keep the tone confident and encouraging. The student has passed their readiness
assessment — they are ready!
"""


class ExamPlannerExecutor(Executor):
    """Recommends certification exams and provides registration guidance."""

    def __init__(
        self,
        *,
        id: str = "exam-planner",
        model: str,
    ) -> None:
        super().__init__(id=id)
        self._model = model
        self._agent_name: str | None = None

    def _ensure_agent(self) -> str:
        if self._agent_name is None:
            mcp_tool_name = os.environ.get("MCP_TOOL_NAME", "mslearn-mcp-server")
            tools = get_mcp_tools(mcp_tool_name)
            self._agent_name = create_foundry_agent(
                name="exam-planner",
                model=self._model,
                instructions=EXAM_PLANNER_INSTRUCTIONS,
                tools=tools or None,
            )
        return self._agent_name

    @handler
    async def plan_exam(self, raw_input: str, ctx: WorkflowContext[str]) -> None:
        PREFIX = "READY: "
        content = raw_input[len(PREFIX):] if raw_input.startswith(PREFIX) else raw_input

        # Parse the assessment result payload
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
            f"Study context summary:\n{context_text[:2000]}\n\n"
            f"Please provide a comprehensive exam planning report, including the recommended "
            f"Microsoft certification exam, registration steps, and a final preparation checklist."
        )

        agent_name = self._ensure_agent()
        result = invoke_foundry_agent(agent_name, prompt)
        await ctx.send_message(result)
