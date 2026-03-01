# Copyright (c) Microsoft. All rights reserved.
"""
Learning Path Curator agent.

Uses a Foundry agent with the Microsoft Learn MCP server tool to query
official learning paths relevant to the student's requested topics, then
returns a curated list with titles, URLs, and estimated completion times.
"""

import logging
import os

from agent_framework import Executor, WorkflowContext, handler

from .foundry_helpers import create_foundry_agent, get_mcp_tools, invoke_foundry_agent

logger = logging.getLogger(__name__)

LEARNING_PATH_CURATOR_INSTRUCTIONS = """\
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


class LearningPathCuratorExecutor(Executor):
    """Queries Microsoft Learn for relevant learning paths via Foundry + MCP."""

    def __init__(
        self,
        *,
        id: str = "learning-path-curator",
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
                name="learning-path-curator",
                model=self._model,
                instructions=LEARNING_PATH_CURATOR_INSTRUCTIONS,
                tools=tools or None,
            )
        return self._agent_name

    @handler
    async def curate(self, context: str, ctx: WorkflowContext[str]) -> None:
        agent_name = self._ensure_agent()
        result = invoke_foundry_agent(agent_name, context)
        await ctx.send_message(result)
