# Copyright (c) Microsoft. All rights reserved.
"""
Study Plan Generator agent.

Receives the curated list of learning paths from the Learning Path Curator
and converts it into a detailed, actionable study plan with a week-by-week
timeline, daily/weekly session allocations, and milestone checkpoints.
"""

from agent_framework.azure import AzureOpenAIChatClient


STUDY_PLAN_GENERATOR_INSTRUCTIONS = """
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


def create_study_plan_generator(token_provider) -> object:
    """Factory: returns the Study Plan Generator agent."""
    client = AzureOpenAIChatClient(ad_token_provider=token_provider)
    agent = client.create_agent(
        name="study-plan-generator",
        instructions=STUDY_PLAN_GENERATOR_INSTRUCTIONS,
    )
    return agent
