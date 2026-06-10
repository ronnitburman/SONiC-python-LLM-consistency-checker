"""API routes for Step 7 — AI chat and deterministic explanations."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from sonic_consistency_checker.ai.models import (
    ChatRequest,
    ChatResponse,
    ExplainFindingRequest,
    ExplainFindingResponse,
    ExplainPortResponse,
)
from sonic_consistency_checker.ai.chat_agent import get_agent, reset_agent
from sonic_consistency_checker.sonic.ports import PortService

router = APIRouter(prefix="/api/ai", tags=["ai"])


# ── Chat ─────────────────────────────────────────────────────────────


@router.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Send a message to the SONiC AI agent (non-streaming).

    For streaming, use /api/ai/chat/stream instead.
    """
    agent = get_agent()

    if request.conversation_id and request.conversation_id != agent.conversation_id:
        reset_agent()
        agent = get_agent()

    user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content
            break

    if not user_message:
        return ChatResponse(
            response="No user message found in request.",
            conversation_id=agent.conversation_id,
        )

    response, thinking_steps = agent.chat(user_message)

    return ChatResponse(
        response=response,
        conversation_id=agent.conversation_id,
        thinking_steps=thinking_steps,
    )


@router.post("/chat/stream")
async def chat_stream(request: ChatRequest) -> StreamingResponse:
    """Send a message and stream the agent's response via SSE.

    Events:
        event: thinking  → tool execution steps (tool_start / tool_end)
        event: token     → LLM response tokens as they are generated
        event: done      → conversation completed
        event: error     → error occurred
    """
    agent = get_agent()

    if request.conversation_id and request.conversation_id != agent.conversation_id:
        reset_agent()
        agent = get_agent()

    user_message = ""
    for msg in reversed(request.messages):
        if msg.role == "user":
            user_message = msg.content
            break

    if not user_message:
        return StreamingResponse(
            iter(["event: error\ndata: {\"error\":\"No user message found\"}\n\n"]),
            media_type="text/event-stream",
        )

    return StreamingResponse(
        agent.chat_stream(user_message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chat/reset")
async def reset_chat() -> dict:
    """Reset the conversation — start a new chat session."""
    agent = reset_agent()
    return {
        "message": "Conversation reset.",
        "conversation_id": agent.conversation_id,
    }


# ── Deterministic explanations ───────────────────────────────────────


@router.get("/explain-port/{port_name}", response_model=ExplainPortResponse)
async def explain_port(port_name: str) -> ExplainPortResponse:
    """Generate deterministic, template-based explanations for a port's findings."""
    from sonic_consistency_checker.ai.explanation_agent import (
        DeterministicExplanationAgent,
    )

    port_view = PortService().get_port_view(port_name)
    agent = DeterministicExplanationAgent()
    explanations = agent.explain_port(port_view)

    return ExplainPortResponse(
        port_name=port_name,
        explanations=explanations,
    )
