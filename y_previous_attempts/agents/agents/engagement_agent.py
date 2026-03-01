# Copyright (c) Microsoft. All rights reserved.
"""
Engagement Agent.

Receives the study plan and produces a set of motivational reminder messages
and a study schedule summary that the student can use to stay on track
(e.g. copy into a calendar, email to themselves, or share with a coach).
"""

from agent_framework.azure import AzureOpenAIChatClient


ENGAGEMENT_AGENT_INSTRUCTIONS = """
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


def create_engagement_agent(token_provider) -> object:
    """Factory: returns the Engagement Agent."""
    client = AzureOpenAIChatClient(ad_token_provider=token_provider)
    agent = client.create_agent(
        name="engagement-agent",
        instructions=ENGAGEMENT_AGENT_INSTRUCTIONS,
    )
    return agent
