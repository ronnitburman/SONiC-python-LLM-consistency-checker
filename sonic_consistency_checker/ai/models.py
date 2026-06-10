"""AI models for chat, explanations, and tool interactions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


# ── Chat models ──────────────────────────────────────────────────────


class ChatMessage(BaseModel):
    """A single message in a chat conversation."""

    role: Literal["user", "assistant", "system", "tool"]
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] | None = None


class ChatRequest(BaseModel):
    """Request body for the chat endpoint."""

    messages: list[ChatMessage]
    conversation_id: str | None = None


class ChatResponse(BaseModel):
    """Response from the chat agent."""

    response: str
    conversation_id: str
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    findings_referenced: list[str] = Field(default_factory=list)
    thinking_steps: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Tool calls made during agent reasoning, with results",
    )


# ── Explanation models (from original Step 7) ────────────────────────


class FindingExplanation(BaseModel):
    finding_id: str
    title: str
    plain_english_summary: str
    dbs_involved: list[str] = Field(default_factory=list)
    sonic_layers_involved: list[str] = Field(default_factory=list)
    why_it_matters: str
    possible_causes: list[str] = Field(default_factory=list)
    suggested_commands: list[str] = Field(default_factory=list)
    interview_explanation: str
    confidence_notes: str
    raw_evidence: dict[str, Any] = Field(default_factory=dict)


class ExplainFindingRequest(BaseModel):
    finding_id: str
    port_name: str | None = None


class ExplainFindingResponse(BaseModel):
    explanation: FindingExplanation


class ExplainPortResponse(BaseModel):
    port_name: str
    explanations: list[FindingExplanation]


# ── Skill models ─────────────────────────────────────────────────────


class SkillInfo(BaseModel):
    name: str
    path: str
    size: int
