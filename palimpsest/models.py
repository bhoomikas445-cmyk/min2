"""
PALIMPSEST Data Models
All Pydantic v2 models used throughout the system.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class MessageRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class MemoryCategory(str, Enum):
    verbatim = "verbatim"
    summary = "summary"
    discard = "discard"


class MemoryItem(BaseModel):
    """A single unit of memory — one conversation turn or document chunk."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_id: str
    version_id: str
    role: MessageRole
    content: str
    category: MemoryCategory = MemoryCategory.verbatim
    importance_score: float = 0.5
    relevance_score: float = 0.5
    recency_score: float = 1.0
    token_count: int = 0
    topic_tags: list[str] = Field(default_factory=list)
    decision_rationale: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    embedding: list[float] | None = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class VersionNode(BaseModel):
    """A node in the versioned context chain."""

    version_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    parent_version_id: str | None = None
    branch_name: str = "main"
    topic_label: str = ""
    session_id: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)
    memory_item_ids: list[str] = Field(default_factory=list)
    is_merged: bool = False
    merge_source_version_id: str | None = None

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class DecisionRecord(BaseModel):
    """Records a memory management decision with its rationale."""

    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    version_id: str
    memory_item_id: str
    category: MemoryCategory
    rationale: str
    factors: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)

    class Config:
        json_encoders = {datetime: lambda v: v.isoformat()}


class ContextWindow(BaseModel):
    """The reconstructed context to be sent to the LLM."""

    version_id: str
    items: list[MemoryItem] = Field(default_factory=list)
    total_tokens: int = 0
    token_budget: int = 8000
    reconstruction_notes: str = ""


class ClassificationResult(BaseModel):
    """Output of the memory classifier."""

    category: MemoryCategory
    importance_score: float
    relevance_score: float
    topic_tags: list[str]
    rationale: str


class EvaluationReport(BaseModel):
    """Comparison report between baseline and PALIMPSEST."""

    baseline_total_tokens: int = 0
    palimpsest_total_tokens: int = 0
    baseline_estimated_cost_usd: float = 0.0
    palimpsest_estimated_cost_usd: float = 0.0
    baseline_avg_latency_ms: float = 0.0
    palimpsest_avg_latency_ms: float = 0.0
    baseline_quality_score: float = 0.0
    palimpsest_quality_score: float = 0.0
    turns: list[dict] = Field(default_factory=list)
    summary: str = ""
