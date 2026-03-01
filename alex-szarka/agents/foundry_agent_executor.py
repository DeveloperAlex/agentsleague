# Copyright (c) Microsoft. All rights reserved.
"""Reusable executor that wraps a pre-deployed Foundry agent via agent_reference."""

import logging
from dataclasses import dataclass

from agent_framework import ChatMessage, Executor, WorkflowContext, handler

logger = logging.getLogger(__name__)


@dataclass
class AgentInput:
    """Input message passed between executors in the workflow."""
    text: str
    role: str = "user"


@dataclass
class AgentOutput:
    """Output message produced by a Foundry agent executor."""
    text: str
    agent_name: str


class FoundryAgentExecutor(Executor):
    """Executor that delegates to a pre-deployed Foundry agent via agent_reference.

    Each instance wraps a specific agent (by name and version) already deployed
    in Azure AI Foundry. The agent's instructions, tools (including MCP), and
    configuration are all managed server-side in Foundry.
    """

    MAX_MCP_APPROVAL_ROUNDS = 10  # safety limit for MCP approval loops

    def __init__(
        self,
        agent_name: str,
        agent_version: str,
        openai_client,
        executor_id: str | None = None,
        terminal: bool = False,
    ) -> None:
        super().__init__(id=executor_id or agent_name)
        self._agent_name = agent_name
        self._agent_version = agent_version
        self._openai_client = openai_client
        self._terminal = terminal

    def _call_foundry_agent(self, messages: list[dict]) -> object:
        """Call the Foundry agent and auto-approve any MCP tool requests.

        Returns the final response after all MCP approval rounds complete.
        """
        agent_body = {
            "agent": {
                "name": self._agent_name,
                "version": self._agent_version,
                "type": "agent_reference",
            }
        }

        response = self._openai_client.responses.create(
            input=messages,
            extra_body=agent_body,
        )

        # MCP approval loop: auto-approve tool calls and continue
        for round_num in range(self.MAX_MCP_APPROVAL_ROUNDS):
            approval_requests = [
                item for item in response.output
                if getattr(item, "type", None) == "mcp_approval_request"
            ]
            if not approval_requests:
                break  # No more MCP approvals needed

            logger.info(
                f"[{self._agent_name}] MCP approval round {round_num + 1}: "
                f"approving {len(approval_requests)} tool call(s)"
            )

            # Build approval responses
            approvals = [
                {
                    "type": "mcp_approval_response",
                    "approval_request_id": req.id,
                    "approve": True,
                }
                for req in approval_requests
            ]

            response = self._openai_client.responses.create(
                input=approvals,
                previous_response_id=response.id,
                extra_body=agent_body,
            )
        else:
            logger.warning(
                f"[{self._agent_name}] Hit max MCP approval rounds "
                f"({self.MAX_MCP_APPROVAL_ROUNDS})"
            )

        return response

    def _extract_response_text(self, response) -> str:
        """Extract text from a Foundry agent response, handling MCP tool outputs."""
        # First try the simple output_text property
        text = response.output_text or ""
        if text.strip():
            return text

        # If output_text is empty, inspect the output items for content
        parts: list[str] = []
        for item in response.output:
            if item.type == "message":
                for content in getattr(item, "content", []):
                    if hasattr(content, "text") and content.text:
                        parts.append(content.text)
            elif hasattr(item, "text") and item.text:
                parts.append(item.text)
            elif hasattr(item, "output") and isinstance(item.output, str) and item.output.strip():
                parts.append(item.output)
        if parts:
            return "\n".join(parts)

        # Last resort: stringify the whole output
        logger.warning(f"[{self._agent_name}] Could not extract text; raw output: {response.output}")
        return str(response.output) if response.output else "(No output)"

    async def _emit(self, output_text: str, ctx: WorkflowContext) -> None:
        """Send output downstream or yield it as workflow output (terminal executor)."""
        if self._terminal:
            logger.info(f"[{self._agent_name}] Yielding terminal output ({len(output_text)} chars)")
            await ctx.yield_output(output_text)
        else:
            await ctx.send_message(
                AgentOutput(text=output_text, agent_name=self._agent_name)
            )

    @handler
    async def handle_input(self, input_data: AgentInput, ctx: WorkflowContext[AgentOutput]) -> None:
        """Receive input, call the Foundry agent, and forward the response."""
        logger.info(f"[{self._agent_name}] Received input: {input_data.text[:100]}...")

        response = self._call_foundry_agent(
            [{"role": input_data.role, "content": input_data.text}]
        )

        output_text = self._extract_response_text(response)
        logger.info(f"[{self._agent_name}] Response: {output_text[:200]}...")

        await self._emit(output_text, ctx)

    @handler
    async def handle_agent_output(self, input_data: AgentOutput, ctx: WorkflowContext[AgentOutput]) -> None:
        """Receive output from a previous agent and forward it to the Foundry agent."""
        logger.info(
            f"[{self._agent_name}] Received output from {input_data.agent_name}: "
            f"{input_data.text[:100]}..."
        )

        response = self._call_foundry_agent(
            [{"role": "user", "content": input_data.text}]
        )

        output_text = self._extract_response_text(response)
        logger.info(f"[{self._agent_name}] Response: {output_text[:200]}...")

        await self._emit(output_text, ctx)

    @handler
    async def handle_string_input(self, input_data: str, ctx: WorkflowContext[AgentOutput]) -> None:
        """Handle raw string input (e.g., from the workflow entry point)."""
        logger.info(f"[{self._agent_name}] Received string input: {input_data[:100]}...")

        response = self._call_foundry_agent(
            [{"role": "user", "content": input_data}]
        )

        output_text = self._extract_response_text(response)
        logger.info(f"[{self._agent_name}] Response: {output_text[:200]}...")

        await self._emit(output_text, ctx)

    @handler
    async def handle_chat_messages(
        self, input_data: list[ChatMessage], ctx: WorkflowContext[AgentOutput]
    ) -> None:
        """Handle list[ChatMessage] from the hosting adapter entry point."""
        # Convert ChatMessage list to OpenAI-compatible message dicts
        messages = []
        for msg in input_data:
            text = ""
            if msg.contents:
                parts = []
                for part in msg.contents:
                    if isinstance(part, str):
                        parts.append(part)
                    elif hasattr(part, "text"):
                        parts.append(part.text)
                    else:
                        parts.append(str(part))
                text = " ".join(parts)
            messages.append({"role": str(msg.role), "content": text})

        combined_text = messages[-1]["content"] if messages else ""
        logger.info(
            f"[{self._agent_name}] Received {len(messages)} ChatMessage(s): "
            f"{combined_text[:100]}..."
        )

        response = self._call_foundry_agent(messages)

        output_text = self._extract_response_text(response)
        logger.info(f"[{self._agent_name}] Response: {output_text[:200]}...")

        await self._emit(output_text, ctx)
