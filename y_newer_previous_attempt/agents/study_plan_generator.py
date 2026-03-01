# Copyright (c) Microsoft. All rights reserved.
"""
Study Plan Generator agent.

Receives the curated list of learning paths from the Learning Path Curator
and converts it into a detailed, actionable study plan with a week-by-week
timeline, daily/weekly session allocations, and milestone checkpoints.
"""

import logging

from agent_framework import Executor, WorkflowContext, handler

from .foundry_helpers import create_foundry_agent, invoke_foundry_agent

logger = logging.getLogger(__name__)

STUDY_PLAN_GENERATOR_INSTRUCTIONS = """\
You are an expert study plan creator specialising in Microsoft technology certifications.

You will receive a curated list of Microsoft Learn learning paths. Your job is to
convert them into a realistic, structured study plan.

Your output must follow this structure:

## Study Plan

### Overview
- Total estimated duration: <X weeks>
- Recommended daily study time: <X–Y hours>
- Key milestone dates (relative, e.g. "Week 2 checkpoint")

### Week-by-Week Schedule

#### Week 1 — <theme>
| Day | Topic | Resource | Duration |
|-----|-------|----------|----------|
| Mon | ...   | ...      | ...      |
...

(Repeat for each week)

### Milestones & Checkpoints
- Week N: Complete <module>, self-assess with practice questions
- ...

### Tips for Success
- ...

Keep the plan realistic. If the timeframe is "flexible", assume a comfortable
8–10 week schedule. Adjust if a specific timeframe was given.
"""


class StudyPlanGeneratorExecutor(Executor):
    """Converts curated learning paths into a week-by-week study plan."""

    def __init__(
        self,
        *,
        id: str = "study-plan-generator",
        model: str,
    ) -> None:
        super().__init__(id=id)
        self._model = model
        self._agent_name: str | None = None

    def _ensure_agent(self) -> str:
        if self._agent_name is None:
            self._agent_name = create_foundry_agent(
                name="study-plan-generator",
                model=self._model,
                instructions=STUDY_PLAN_GENERATOR_INSTRUCTIONS,
            )
        return self._agent_name

    @handler
    async def generate(self, context: str, ctx: WorkflowContext[str]) -> None:
        agent_name = self._ensure_agent()
        result = invoke_foundry_agent(agent_name, context)
        await ctx.send_message(result)
