# Copyright (c) Microsoft. All rights reserved.
"""
Learning Path Curator agent.

Uses the Microsoft Learn MCP server to query official learning paths that are
relevant to the student's requested topics, then returns a curated list with
titles, URLs, and estimated completion times.
"""
import os

from agent_framework import MCPStreamableHTTPTool
from agent_framework.azure import AzureOpenAIChatClient


MICROSOFT_LEARN_MCP_URL = os.environ.get(
    "MICROSOFT_LEARN_MCP_URL", "https://learn.microsoft.com/api/mcp"
)

LEARNING_PATH_CURATOR_INSTRUCTIONS = """
You are an expert Microsoft Learning Path Curator.

You have access to the Microsoft Learn MCP server. Use it to search for
official Microsoft Learn modules and learning paths that are directly relevant
to the student's requested topics and experience level.

Your output must be a structured list of recommended resources:

## Recommended Learning Paths

For each recommended path, provide:
- **Title**: <learning path title>
- **URL**: <full learn.microsoft.com URL>
- **Level**: <beginner / intermediate / advanced>
- **Estimated duration**: <e.g. "4 hours">
- **Why relevant**: <one sentence>

Aim for 3–6 highly relevant learning paths. Prioritise official Microsoft Learn
content. If a relevant certification learning path exists, include it.
"""


def create_learning_path_curator(token_provider) -> object:
    """
    Factory: returns an agent equipped with the Microsoft Learn MCP tool.
    The agent is created fresh each time so credentials are always current.
    """
    client = AzureOpenAIChatClient(ad_token_provider=token_provider)
    agent = client.create_agent(
        name="learning-path-curator",
        instructions=LEARNING_PATH_CURATOR_INSTRUCTIONS,
        tools=MCPStreamableHTTPTool(
            name="MicrosoftLearn",
            url=MICROSOFT_LEARN_MCP_URL,
        ),
    )
    return agent
