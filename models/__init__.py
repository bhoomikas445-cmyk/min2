"""
PALIMPSEST Database Models
SQLAlchemy ORM models covering projects, messages, memories, decisions,
version control (branches, versions, diff changes), audit logs, and evaluation benchmarks.
"""

import uuid
from datetime import datetime, timezone
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, DateTime,
    ForeignKey, UniqueConstraint
)
from sqlalchemy.orm import relationship

db = SQLAlchemy()


def generate_uuid() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(db.Model):
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    name = Column(String(120), nullable=False)
    description = Column(Text, nullable=True, default="")
    objective = Column(Text, nullable=True, default="General development and context management")
    active_branch_id = Column(String(36), nullable=True)
    token_budget = Column(Integer, default=2048)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    conversations = relationship("Conversation", back_populates="project", cascade="all, delete-orphan")
    branches = relationship("MemoryBranch", back_populates="project", cascade="all, delete-orphan", foreign_keys="MemoryBranch.project_id")
    versions = relationship("MemoryVersion", back_populates="project", cascade="all, delete-orphan", foreign_keys="MemoryVersion.project_id")
    memory_items = relationship("MemoryItem", back_populates="project", cascade="all, delete-orphan")
    audit_logs = relationship("AuditLog", back_populates="project", cascade="all, delete-orphan")
    evaluation_runs = relationship("EvaluationRun", back_populates="project", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "objective": self.objective,
            "active_branch_id": self.active_branch_id,
            "token_budget": self.token_budget,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "conversation_count": len(self.conversations),
            "memory_item_count": len(self.memory_items),
            "version_count": len(self.versions),
            "branch_count": len(self.branches),
        }


class Conversation(db.Model):
    __tablename__ = "conversations"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    title = Column(String(200), nullable=False, default="Default Session")
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    project = relationship("Project", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": len(self.messages),
        }


class Message(db.Model):
    __tablename__ = "messages"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    conversation_id = Column(String(36), ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False, default="user")  # 'user', 'assistant', 'system', 'tool'
    content = Column(Text, nullable=False)
    token_count = Column(Integer, default=0)
    is_processed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utc_now)

    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    memory_items = relationship("MemoryItem", back_populates="source_message")

    def to_dict(self):
        return {
            "id": self.id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "token_count": self.token_count,
            "is_processed": self.is_processed,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MemoryBranch(db.Model):
    __tablename__ = "memory_branches"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(80), nullable=False)
    created_from_version_id = Column(String(36), ForeignKey("memory_versions.id", ondelete="SET NULL"), nullable=True)
    current_head_version_id = Column(String(36), ForeignKey("memory_versions.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)

    __table_args__ = (
        UniqueConstraint("project_id", "name", name="uq_project_branch_name"),
    )

    project = relationship("Project", back_populates="branches", foreign_keys=[project_id])
    versions = relationship("MemoryVersion", back_populates="branch", foreign_keys="MemoryVersion.branch_id")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "created_from_version_id": self.created_from_version_id,
            "current_head_version_id": self.current_head_version_id,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "version_count": len(self.versions),
        }


class MemoryVersion(db.Model):
    __tablename__ = "memory_versions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    branch_id = Column(String(36), ForeignKey("memory_branches.id", ondelete="SET NULL"), nullable=True)
    version_number = Column(Integer, default=1)
    version_hash = Column(String(40), nullable=False)
    label = Column(String(150), nullable=False)
    summary = Column(Text, nullable=True, default="")
    parent_version_id = Column(String(36), ForeignKey("memory_versions.id", ondelete="SET NULL"), nullable=True)
    is_restoration = Column(Boolean, default=False)
    is_merge = Column(Boolean, default=False)
    merge_source_version_id = Column(String(36), ForeignKey("memory_versions.id", ondelete="SET NULL"), nullable=True)
    total_items_count = Column(Integer, default=0)
    verbatim_count = Column(Integer, default=0)
    summary_count = Column(Integer, default=0)
    discard_count = Column(Integer, default=0)
    active_token_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=utc_now)

    # Self-referential relationship
    parent = relationship("MemoryVersion", remote_side=[id], backref="children", foreign_keys=[parent_version_id])
    project = relationship("Project", back_populates="versions", foreign_keys=[project_id])
    branch = relationship("MemoryBranch", back_populates="versions", foreign_keys=[branch_id])
    changes = relationship("VersionChange", back_populates="version", cascade="all, delete-orphan")
    decisions = relationship("MemoryDecision", back_populates="version", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "branch_id": self.branch_id,
            "branch_name": self.branch.name if self.branch else "main",
            "version_number": self.version_number,
            "version_hash": self.version_hash,
            "short_hash": self.version_hash[:8] if self.version_hash else self.id[:8],
            "label": self.label,
            "summary": self.summary,
            "parent_version_id": self.parent_version_id,
            "is_restoration": self.is_restoration,
            "is_merge": self.is_merge,
            "merge_source_version_id": self.merge_source_version_id,
            "total_items_count": self.total_items_count,
            "verbatim_count": self.verbatim_count,
            "summary_count": self.summary_count,
            "discard_count": self.discard_count,
            "active_token_count": self.active_token_count,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class MemoryItem(db.Model):
    __tablename__ = "memory_items"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    source_message_id = Column(String(36), ForeignKey("messages.id", ondelete="SET NULL"), nullable=True)
    source_document = Column(String(255), nullable=True)
    content = Column(Text, nullable=False)
    summary_content = Column(Text, nullable=True)
    category = Column(String(20), nullable=False, default="KEEP VERBATIM")  # 'KEEP VERBATIM', 'SUMMARIZE', 'DISCARD'
    importance_score = Column(Float, default=0.5)
    relevance_score = Column(Float, default=0.5)
    recency_score = Column(Float, default=1.0)
    redundancy_score = Column(Float, default=0.0)
    is_instruction_or_constraint = Column(Boolean, default=False)
    topic_tags = Column(String(255), default="general")
    original_token_count = Column(Integer, default=0)
    stored_token_count = Column(Integer, default=0)
    current_version_id = Column(String(36), ForeignKey("memory_versions.id", ondelete="SET NULL"), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=utc_now)
    updated_at = Column(DateTime, default=utc_now, onupdate=utc_now)

    # Relationships
    project = relationship("Project", back_populates="memory_items")
    source_message = relationship("Message", back_populates="memory_items")
    decisions = relationship("MemoryDecision", back_populates="memory_item", cascade="all, delete-orphan", order_by="MemoryDecision.timestamp.desc()")
    audit_logs = relationship("AuditLog", back_populates="memory_item")

    def to_dict(self):
        latest_decision = self.decisions[0] if self.decisions else None
        return {
            "id": self.id,
            "project_id": self.project_id,
            "source_message_id": self.source_message_id,
            "source_document": self.source_document,
            "content": self.content,
            "summary_content": self.summary_content,
            "category": self.category,
            "importance_score": round(self.importance_score, 2),
            "relevance_score": round(self.relevance_score, 2),
            "recency_score": round(self.recency_score, 2),
            "redundancy_score": round(self.redundancy_score, 2),
            "is_instruction_or_constraint": self.is_instruction_or_constraint,
            "topic_tags": [t.strip() for t in self.topic_tags.split(",") if t.strip()] if self.topic_tags else [],
            "original_token_count": self.original_token_count,
            "stored_token_count": self.stored_token_count,
            "token_savings": max(0, self.original_token_count - self.stored_token_count),
            "current_version_id": self.current_version_id,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "explanation": latest_decision.explanation if latest_decision else "Initial decision",
            "processing_method": latest_decision.processing_method if latest_decision else "rule_based",
        }


class MemoryDecision(db.Model):
    __tablename__ = "memory_decisions"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    memory_item_id = Column(String(36), ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False)
    version_id = Column(String(36), ForeignKey("memory_versions.id", ondelete="SET NULL"), nullable=True)
    action = Column(String(20), nullable=False)  # 'KEEP VERBATIM', 'SUMMARIZE', 'DISCARD'
    explanation = Column(Text, nullable=False)
    importance_score = Column(Float, default=0.5)
    relevance_score = Column(Float, default=0.5)
    original_token_count = Column(Integer, default=0)
    stored_token_count = Column(Integer, default=0)
    processing_method = Column(String(50), default="rule_based")  # 'rule_based', 'llm', 'manual_override'
    timestamp = Column(DateTime, default=utc_now)

    # Relationships
    memory_item = relationship("MemoryItem", back_populates="decisions")
    version = relationship("MemoryVersion", back_populates="decisions")

    def to_dict(self):
        return {
            "id": self.id,
            "memory_item_id": self.memory_item_id,
            "version_id": self.version_id,
            "action": self.action,
            "explanation": self.explanation,
            "importance_score": round(self.importance_score, 2),
            "relevance_score": round(self.relevance_score, 2),
            "original_token_count": self.original_token_count,
            "stored_token_count": self.stored_token_count,
            "processing_method": self.processing_method,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class VersionChange(db.Model):
    __tablename__ = "version_changes"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    version_id = Column(String(36), ForeignKey("memory_versions.id", ondelete="CASCADE"), nullable=False)
    memory_item_id = Column(String(36), ForeignKey("memory_items.id", ondelete="CASCADE"), nullable=False)
    change_type = Column(String(20), nullable=False)  # 'ADDED', 'MODIFIED', 'DELETED', 'RESTORED', 'MERGED'
    old_category = Column(String(20), nullable=True)
    new_category = Column(String(20), nullable=False)
    diff_summary = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now)

    version = relationship("MemoryVersion", back_populates="changes")
    memory_item = relationship("MemoryItem")

    def to_dict(self):
        return {
            "id": self.id,
            "version_id": self.version_id,
            "memory_item_id": self.memory_item_id,
            "change_type": self.change_type,
            "old_category": self.old_category,
            "new_category": self.new_category,
            "diff_summary": self.diff_summary,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    memory_item_id = Column(String(36), ForeignKey("memory_items.id", ondelete="SET NULL"), nullable=True)
    version_id = Column(String(36), ForeignKey("memory_versions.id", ondelete="SET NULL"), nullable=True)
    previous_action = Column(String(20), nullable=True)
    new_action = Column(String(20), nullable=False)
    reason = Column(Text, nullable=False)
    source = Column(String(30), nullable=False)  # 'rule_based', 'llm', 'manual', 'restoration', 'merge'
    timestamp = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="audit_logs")
    memory_item = relationship("MemoryItem", back_populates="audit_logs")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "memory_item_id": self.memory_item_id,
            "version_id": self.version_id,
            "previous_action": self.previous_action,
            "new_action": self.new_action,
            "reason": self.reason,
            "source": self.source,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
        }


class EvaluationRun(db.Model):
    __tablename__ = "evaluation_runs"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    project_id = Column(String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(150), nullable=False)
    model_name = Column(String(80), nullable=False, default="gpt-4o-mini (simulated)")
    token_estimator = Column(String(50), nullable=False, default="tiktoken / heuristic fallback")
    dataset_name = Column(String(100), nullable=False, default="Standard Architectural Memory Bench")
    test_conditions = Column(Text, nullable=True, default="")
    baseline_tokens = Column(Integer, default=0)
    palimpsest_tokens = Column(Integer, default=0)
    token_reduction_pct = Column(Float, default=0.0)
    baseline_cost_usd = Column(Float, default=0.0)
    palimpsest_cost_usd = Column(Float, default=0.0)
    baseline_latency_ms = Column(Float, default=0.0)
    palimpsest_latency_ms = Column(Float, default=0.0)
    retention_accuracy = Column(Float, default=0.0)
    precision_score = Column(Float, default=0.0)
    recall_score = Column(Float, default=0.0)
    drift_recovery_rate = Column(Float, default=0.0)
    created_at = Column(DateTime, default=utc_now)

    project = relationship("Project", back_populates="evaluation_runs")
    results = relationship("EvaluationResult", back_populates="evaluation_run", cascade="all, delete-orphan")

    def to_dict(self):
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "model_name": self.model_name,
            "token_estimator": self.token_estimator,
            "dataset_name": self.dataset_name,
            "test_conditions": self.test_conditions,
            "baseline_tokens": self.baseline_tokens,
            "palimpsest_tokens": self.palimpsest_tokens,
            "token_reduction_pct": round(self.token_reduction_pct, 1),
            "baseline_cost_usd": round(self.baseline_cost_usd, 6),
            "palimpsest_cost_usd": round(self.palimpsest_cost_usd, 6),
            "baseline_latency_ms": round(self.baseline_latency_ms, 1),
            "palimpsest_latency_ms": round(self.palimpsest_latency_ms, 1),
            "retention_accuracy": round(self.retention_accuracy * 100, 1),
            "precision_score": round(self.precision_score * 100, 1),
            "recall_score": round(self.recall_score * 100, 1),
            "drift_recovery_rate": round(self.drift_recovery_rate * 100, 1),
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "result_count": len(self.results),
        }


class EvaluationResult(db.Model):
    __tablename__ = "evaluation_results"

    id = Column(String(36), primary_key=True, default=generate_uuid)
    evaluation_run_id = Column(String(36), ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False)
    question_id = Column(String(50), nullable=False)
    query = Column(Text, nullable=False)
    expected_answer = Column(Text, nullable=False)
    baseline_response = Column(Text, nullable=True)
    palimpsest_response = Column(Text, nullable=True)
    baseline_recalled = Column(Boolean, default=False)
    palimpsest_recalled = Column(Boolean, default=False)
    precision = Column(Float, default=0.0)
    recall = Column(Float, default=0.0)
    passed = Column(Boolean, default=False)
    details = Column(Text, nullable=True)

    evaluation_run = relationship("EvaluationRun", back_populates="results")

    def to_dict(self):
        return {
            "id": self.id,
            "evaluation_run_id": self.evaluation_run_id,
            "question_id": self.question_id,
            "query": self.query,
            "expected_answer": self.expected_answer,
            "baseline_response": self.baseline_response,
            "palimpsest_response": self.palimpsest_response,
            "baseline_recalled": self.baseline_recalled,
            "palimpsest_recalled": self.palimpsest_recalled,
            "precision": round(self.precision, 2),
            "recall": round(self.recall, 2),
            "passed": self.passed,
            "details": self.details,
        }
