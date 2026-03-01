# Copyright (c) Microsoft. All rights reserved.
"""
Engagement Agent.

Receives the study plan and produces motivational reminder messages,
a study schedule summary, and a getting-started checklist the student
can use to stay on track.
"""

import logging

from agent_framework import Executor, WorkflowContext, handler

from .foundry_helpers import create_foundry_agent, invoke_foundry_agent

logger = logging.getLogger(__name__)

ENGAGEMENT_AGENT_INSTRUCTIONS = """\
You are an enthusiastic student engagement coach specialising in Microsoft
certification preparation.

You will receive a detailed study plan. Your job is to create a set of
motivational reminders and a concise schedule summary.

Your output must include:

## Engagement Package

### Weekly Reminder Messages
For each week of the study plan, write one short motivational reminder
(2–3 sentences) that the student can save as a calendar reminder or email.
Format each as:

**Week N Reminder:**
> <message>

### Study Schedule Summary (plain text, calendar-friendly)
A plain-text version of the weekly schedule suitable for pasting into a
calendar description or email:

```
Week 1: <brief summary>
Week 2: <brief summary>
...
```

### Getting Started Checklist
- [ ] Bookmark your first learning path
- [ ] Block study time in your calendar
- [ ] Join the relevant Microsoft Learn community
- [ ] Set a target exam date
- [ ] ...

Keep the tone encouraging and practical. Personalise using the topics from
the study plan.
"""


class EngagementExecutor(Executor):
    """Creates motivational reminders, schedule summaries, and checklists."""

    def __init__(
        self,
        *,
        id: str = "engagement-agent",
        model: str,
    ) -> None:
        super().__init__(id=id)
        self._model = model
        self._agent_name: str | None = None

    def _ensure_agent(self) -> str:
        if self._agent_name is None:
            self._agent_name = create_foundry_agent(
                name="engagement-agent",
                model=self._model,
                instructions=ENGAGEMENT_AGENT_INSTRUCTIONS,
            )
        return self._agent_name

    @handler
    async def engage(self, context: str, ctx: WorkflowContext[str]) -> None:
        agent_name = self._ensure_agent()
        result = invoke_foundry_agent(agent_name, context)
        await ctx.send_message(result)
