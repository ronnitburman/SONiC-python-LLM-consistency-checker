"""LangGraph conversational agent for SONiC diagnostics.

Uses a StateGraph with two nodes:
- agent_node: calls the LLM (which may request tool calls)
- tool_node: executes the requested tools and returns results

The agent can load SONiC skills on demand and call MCP diagnostic tools.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Annotated, Any, AsyncGenerator

from langchain_core.messages import (
    AIMessage,
    BaseMessage,
    HumanMessage,
    SystemMessage,
    ToolMessage,
)
from langgraph.graph import StateGraph, END, add_messages
from langgraph.prebuilt import ToolNode
from typing_extensions import TypedDict

from sonic_consistency_checker.ai.model_provider import get_llm
from sonic_consistency_checker.ai.prompt_templates import SYSTEM_PROMPT
from sonic_consistency_checker.ai.tools import ALL_TOOLS

logger = logging.getLogger(__name__)


# ── State ────────────────────────────────────────────────────────────


class AgentState(TypedDict):
    """State passed between agent and tool nodes.

    The ``Annotated[list, add_messages]`` annotation tells LangGraph to
    APPEND new messages rather than REPLACE the list.  Without this,
    each node's return would wipe out the conversation history.
    """

    messages: Annotated[list[Any], add_messages]


# ── Node functions ───────────────────────────────────────────────────


def _agent_node(state: AgentState) -> dict:
    """Call the LLM with the current conversation state.

    The LLM may return a text response or request tool calls.
    """
    llm = get_llm()
    llm_with_tools = llm.bind_tools(ALL_TOOLS)

    messages = state["messages"]
    model_name = getattr(llm, "model_name", "unknown")

    # Info-level: what LLM is being called and with how many messages
    n_tool_msgs = sum(1 for m in messages if isinstance(m, ToolMessage))
    n_ai_msgs = sum(1 for m in messages if isinstance(m, AIMessage))
    logger.info(
        "→ LLM call: model=%s  msgs=%d (sys=1, human=~%d, ai=%d, tool=%d)",
        model_name,
        len(messages),
        len(messages) - n_ai_msgs - n_tool_msgs - 1,  # approx human count
        n_ai_msgs,
        n_tool_msgs,
    )

    response = llm_with_tools.invoke(messages)

    n_tc = len(getattr(response, "tool_calls", []) or [])
    if n_tc:
        tc_names = [tc.get("name", "?") for tc in response.tool_calls]
        logger.info("← LLM response: %d tool call(s) → %s", n_tc, ", ".join(tc_names))
    else:
        content_len = len(str(response.content)) if response.content else 0
        logger.info("← LLM response: text (%d chars)", content_len)

    return {"messages": [response]}


# ── Routing ──────────────────────────────────────────────────────────


def _should_continue(state: AgentState) -> str:
    """Decide whether to call tools or end the conversation.

    Returns:
        "tools" if the last message contains tool calls.
        END otherwise.
    """
    messages = state["messages"]
    last_message = messages[-1]

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return END


# ── Graph builder ────────────────────────────────────────────────────


def build_agent() -> StateGraph:
    """Build and compile the LangGraph agent."""
    tool_node = ToolNode(tools=ALL_TOOLS)

    graph = StateGraph(AgentState)

    graph.add_node("agent", _agent_node)
    graph.add_node("tools", tool_node)

    graph.set_entry_point("agent")

    graph.add_conditional_edges(
        "agent",
        _should_continue,
        {"tools": "tools", END: END},
    )
    graph.add_edge("tools", "agent")

    return graph.compile()


# ── Chat runner ──────────────────────────────────────────────────────


class ChatAgent:
    """High-level chat agent wrapping the LangGraph state graph.

    Usage::

        agent = ChatAgent()
        response = agent.chat("Why is Ethernet0 down?")
        print(response)

        # Multi-turn:
        response = agent.chat("What about Ethernet4?")
    """

    def __init__(self, debug: bool = False) -> None:
        self._graph = build_agent()
        self._conversation_id = uuid.uuid4().hex[:12]
        self._messages: list[Any] = [SystemMessage(content=SYSTEM_PROMPT)]
        self._thinking_steps: list[dict[str, Any]] = []
        if debug:
            logging.basicConfig(
                level=logging.DEBUG,
                format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
                datefmt="%H:%M:%S",
            )
            logger.setLevel(logging.DEBUG)
            logging.getLogger("sonic_consistency_checker.ai.mcp_bridge").setLevel(logging.DEBUG)

    def chat(self, user_message: str) -> tuple[str, list[dict[str, Any]]]:
        """Send a user message and get the agent's response.

        Args:
            user_message: The user's question or command.

        Returns:
            A tuple of (response_text, thinking_steps) where
            thinking_steps is a list of tool calls with their results.
        """
        self._messages.append(HumanMessage(content=user_message))

        state: AgentState = {"messages": list(self._messages)}

        logger.debug("chat: invoking graph with %d messages", len(state["messages"]))
        for i, msg in enumerate(state["messages"]):
            logger.debug("  pre[%d] type=%s", i, type(msg).__name__)

        try:
            result = self._graph.invoke(state, config={"recursion_limit": 15})
            new_messages = result["messages"]

            logger.debug("chat: graph returned %d messages", len(new_messages))
            for i, msg in enumerate(new_messages):
                logger.debug("  post[%d] type=%s", i, type(msg).__name__)

            # Build thinking steps from the message history
            thinking_steps: list[dict[str, Any]] = []
            for msg in new_messages:
                if isinstance(msg, AIMessage) and msg.tool_calls:
                    for tc in msg.tool_calls:
                        thinking_steps.append({
                            "type": "tool_call",
                            "tool": tc.get("name", "unknown"),
                            "args": tc.get("args", {}),
                        })
                elif isinstance(msg, ToolMessage):
                    # Find the matching step and add the result
                    tid = getattr(msg, "tool_call_id", "")
                    for step in reversed(thinking_steps):
                        if step.get("tool_call_id") == tid or step["type"] == "tool_call":
                            step["result"] = msg.content[:2000]  # truncate large results
                            step["result_full_len"] = len(str(msg.content))
                            break

            # Replace internal state with the full conversation
            self._messages = list(new_messages)

            # Extract the final AI response
            final_response = ""
            for msg in reversed(new_messages):
                if isinstance(msg, AIMessage) and msg.content:
                    final_response = str(msg.content)
                    break

            if not final_response:
                final_response = "Agent completed but produced no text response."

            return final_response, thinking_steps

        except Exception as exc:
            logger.error("Agent invocation failed: %s", exc, exc_info=True)
            return f"ERROR: Agent failed — {exc}", []

    async def chat_stream(
        self, user_message: str
    ) -> AsyncGenerator[str, None]:
        """Stream the agent's response as SSE events.

        Yields SSE-formatted strings:
            event: thinking  → tool calls as they execute
            event: token     → LLM response tokens
            event: done      → conversation_id

        Usage::

            async for event in agent.chat_stream("show me dbs"):
                print(event)  # "event: thinking\\ndata: {...}\\n\\n"
        """
        import json as _json

        self._messages.append(HumanMessage(content=user_message))
        state: AgentState = {"messages": list(self._messages)}

        try:
            # Use astream_events for real-time streaming from LangGraph
            async for event in self._graph.astream_events(
                state,
                config={"recursion_limit": 15},
                version="v2",
            ):
                kind = event.get("event", "")
                name = event.get("name", "")

                # ── Tool execution events ──────────────────────────
                if kind == "on_tool_start":
                    tool_input = event.get("data", {}).get("input", {})
                    payload = {
                        "type": "tool_start",
                        "tool": name,
                        "args": tool_input if isinstance(tool_input, dict) else {},
                    }
                    yield f"event: thinking\ndata: {_json.dumps(payload)}\n\n"

                elif kind == "on_tool_end":
                    output = event.get("data", {}).get("output", "")
                    output_str = str(output)
                    payload = {
                        "type": "tool_end",
                        "tool": name,
                        "result": output_str[:2000],
                        "result_full_len": len(output_str),
                    }
                    yield f"event: thinking\ndata: {_json.dumps(payload)}\n\n"

                # ── LLM token streaming ────────────────────────────
                elif kind == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk", None)
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        payload = {"token": chunk.content}
                        yield f"event: token\ndata: {_json.dumps(payload)}\n\n"

            # Signal completion IMMEDIATELY so the UI spinner stops.
            yield f"event: done\ndata: {_json.dumps({'conversation_id': self._conversation_id})}\n\n"

            # Update state AFTER yielding done (this can take seconds
            # with slow models; the UI already has the full response).
            final_state = await self._graph.ainvoke(state, config={"recursion_limit": 15})
            self._messages = list(final_state.get("messages", self._messages))

        except Exception as exc:
            logger.error("Agent stream failed: %s", exc, exc_info=True)
            error_payload = {"error": str(exc)}
            yield f"event: error\ndata: {_json.dumps(error_payload)}\n\n"

    def reset(self) -> None:
        """Reset the conversation (keeps only the system prompt)."""
        self._conversation_id = uuid.uuid4().hex[:12]
        self._messages = [SystemMessage(content=SYSTEM_PROMPT)]

    @property
    def conversation_id(self) -> str:
        return self._conversation_id

    @property
    def message_count(self) -> int:
        return len(self._messages)


# ── Module-level singleton ───────────────────────────────────────────

_agent: ChatAgent | None = None


def get_agent() -> ChatAgent:
    """Get or create the module-level chat agent singleton."""
    global _agent
    if _agent is None:
        _agent = ChatAgent()
    return _agent


def reset_agent() -> ChatAgent:
    """Reset and return a fresh agent."""
    global _agent
    _agent = ChatAgent()
    return _agent
