"""
PALIMPSEST Main Agent
Ties all modules together: classify, compress, retrieve, reconstruct, version, and chat.
"""

from __future__ import annotations

import time
import uuid
from datetime import datetime
from typing import Any

from config import Config
from palimpsest.classifier import MemoryClassifier
from palimpsest.compressor import MemoryCompressor
from palimpsest.models import (
    DecisionRecord,
    MemoryCategory,
    MemoryItem,
    MessageRole,
    VersionNode,
)
from palimpsest.reconstructor import ContextReconstructor
from palimpsest.retrieval import RetrievalEngine
from palimpsest.store import MemoryStore
from palimpsest.version_control import VersionController


def _build_llm_client(config: Config) -> Any:
    """Factory: returns an OpenAI or Anthropic client, or None in mock mode."""
    if config.mock_mode:
        return None
    if config.model_provider == "openai" and config.openai_api_key:
        from openai import OpenAI
        return OpenAI(api_key=config.openai_api_key)
    if config.model_provider == "anthropic" and config.anthropic_api_key:
        import anthropic
        return anthropic.Anthropic(api_key=config.anthropic_api_key)
    return None


class PalimpsestAgent:
    """
    The PALIMPSEST agent: transparent, versioned context memory for long-running AI agents.
    """

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self._llm = _build_llm_client(self.config)
        self.store = MemoryStore(self.config.db_path)
        self.classifier = MemoryClassifier(self.config, self._llm)
        self.compressor = MemoryCompressor(self.config, self._llm)
        self.retrieval = RetrievalEngine(self.config)
        self.reconstructor = ContextReconstructor(self.config)
        self.version_controller = VersionController(self.store)

        # Active state
        self._active_session: str | None = None
        self._active_version_id: str | None = None
        self._active_objective: str = ""

        # Metrics tracking
        self.total_tokens_used: int = 0
        self.total_latency_ms: float = 0.0
        self.turn_count: int = 0

    # ── Session Management ────────────────────────────────────────────────────

    def start_session(self, session_id: str | None = None, objective: str = "") -> str:
        """Start a new session and create an initial version. Returns the version_id."""
        self._active_session = session_id or str(uuid.uuid4())
        self._active_objective = objective

        # Check for existing tip on main branch
        existing_tip = self.version_controller.get_branch_tip("main")
        parent_id = existing_tip.version_id if existing_tip else None

        version = self.version_controller.create_version(
            session_id=self._active_session,
            topic_label=f"Session start: {objective[:60] or 'New session'}",
            parent_version_id=parent_id,
            branch_name="main",
        )
        self._active_version_id = version.version_id

        # Build retrieval index from all existing non-discard items
        if existing_tip:
            all_items = self.store.get_items_by_version(existing_tip.version_id)
            indexable = [i for i in all_items if i.embedding and i.category != MemoryCategory.discard]
            self.retrieval.build_index(indexable)

        return version.version_id

    # ── Chat ─────────────────────────────────────────────────────────────────

    def chat(self, user_message: str, session_id: str | None = None) -> str:
        """
        Main conversation method.
        1. Retrieve relevant memory.
        2. Reconstruct context within token budget.
        3. Call LLM.
        4. Classify and store new items.
        5. Return response.
        """
        if not self._active_version_id:
            self.start_session(session_id, "General conversation")

        t0 = time.time()

        # Retrieve relevant prior memory
        retrieved = self.retrieval.retrieve(user_message, top_k=12)

        # Get verbatim and summary items from current version
        version_items = self.store.get_items_by_version(self._active_version_id)
        verbatim_items = [i for i in version_items if i.category == MemoryCategory.verbatim]
        summary_items = [i for i in version_items if i.category == MemoryCategory.summary]

        # Reconstruct context
        window = self.reconstructor.reconstruct(
            verbatim_items=verbatim_items,
            summary_items=summary_items,
            retrieved_items=retrieved,
            query=user_message,
            compressor=self.compressor,
        )

        # Build messages list for LLM
        messages = self.reconstructor.to_messages(window)
        if self._active_objective:
            messages.insert(0, {
                "role": "system",
                "content": f"You are a helpful assistant. Current objective: {self._active_objective}",
            })
        messages.append({"role": "user", "content": user_message})

        # LLM call
        response_text = self._make_llm_call(messages)
        latency_ms = (time.time() - t0) * 1000

        # Update metrics
        self.total_tokens_used += window.total_tokens + self.reconstructor.count_tokens(response_text)
        self.total_latency_ms += latency_ms
        self.turn_count += 1

        # Classify and store new items
        session_summary = f"Objective: {self._active_objective}"
        user_result = self.classifier.classify(
            user_message, "user", self._active_objective, session_summary
        )
        asst_result = self.classifier.classify(
            response_text, "assistant", self._active_objective, session_summary
        )

        user_item = self._build_item(user_message, MessageRole.user, user_result)
        asst_item = self._build_item(response_text, MessageRole.assistant, asst_result)

        self.version_controller.commit(self._active_version_id, [user_item, asst_item])

        # Record decisions
        for item, result in [(user_item, user_result), (asst_item, asst_result)]:
            decision = DecisionRecord(
                version_id=self._active_version_id,
                memory_item_id=item.id,
                category=result.category,
                rationale=result.rationale,
                factors={
                    "importance": result.importance_score,
                    "relevance": result.relevance_score,
                    "topic_tags": result.topic_tags,
                },
            )
            self.store.save_decision(decision)

        # Update retrieval index with new verbatim items
        if user_item.category != MemoryCategory.discard:
            embedding = self.retrieval.embed(user_message)
            user_item.embedding = embedding
            self.retrieval.update_index(user_item)
        if asst_item.category != MemoryCategory.discard:
            embedding = self.retrieval.embed(response_text)
            asst_item.embedding = embedding
            self.retrieval.update_index(asst_item)

        return response_text

    # ── Inspection ────────────────────────────────────────────────────────────

    def get_memory_summary(self, version_id: str | None = None) -> dict:
        """Return memory stats for a version."""
        vid = version_id or self._active_version_id or ""
        items = self.store.get_items_by_version(vid)
        topic_counts: dict[str, int] = {}
        for item in items:
            for tag in item.topic_tags:
                topic_counts[tag] = topic_counts.get(tag, 0) + 1
        return {
            "version_id": vid,
            "total_items": len(items),
            "verbatim_count": sum(1 for i in items if i.category == MemoryCategory.verbatim),
            "summary_count": sum(1 for i in items if i.category == MemoryCategory.summary),
            "discard_count": sum(1 for i in items if i.category == MemoryCategory.discard),
            "total_tokens": sum(i.token_count for i in items),
            "topics": topic_counts,
            "recent_decisions": [
                d.rationale for d in self.store.get_decisions_for_version(vid)[-5:]
            ],
        }

    def inspect_decisions(self, version_id: str | None = None) -> list[DecisionRecord]:
        """Return all decision records for a version."""
        vid = version_id or self._active_version_id or ""
        return self.store.get_decisions_for_version(vid)

    def get_version_history(self) -> dict:
        """Return the full version tree."""
        return self.version_controller.get_version_tree()

    # ── Version Operations ────────────────────────────────────────────────────

    def rollback(self, version_id: str) -> str:
        """Restore context from an earlier version. Returns new session_id."""
        new_session_id = str(uuid.uuid4())
        new_version = self.version_controller.restart_from(version_id, new_session_id)
        self._active_session = new_session_id
        self._active_version_id = new_version.version_id
        # Rebuild retrieval index
        items = self.store.get_items_by_version(new_version.version_id)
        self.retrieval.build_index([i for i in items if i.embedding])
        return new_session_id

    def branch_session(self, version_id: str, branch_name: str, topic_label: str) -> str:
        """Create a branch. Returns new session_id."""
        new_version = self.version_controller.branch(version_id, branch_name, topic_label)
        new_session_id = str(uuid.uuid4())
        self._active_session = new_session_id
        self._active_version_id = new_version.version_id
        return new_session_id

    def merge_sessions(
        self, source_version_id: str, target_version_id: str, strategy: str = "union"
    ) -> str:
        """Merge two versions. Returns the new merged version_id."""
        merged = self.version_controller.merge(source_version_id, target_version_id, strategy)
        self._active_version_id = merged.version_id
        return merged.version_id

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_item(self, content: str, role: MessageRole, result) -> MemoryItem:
        item = MemoryItem(
            session_id=self._active_session or "",
            version_id=self._active_version_id or "",
            role=role,
            content=content,
            category=result.category,
            importance_score=result.importance_score,
            relevance_score=result.relevance_score,
            recency_score=1.0,
            token_count=self.reconstructor.count_tokens(content),
            topic_tags=result.topic_tags,
            decision_rationale=result.rationale,
            created_at=datetime.utcnow(),
        )
        return item

    def _make_llm_call(self, messages: list[dict]) -> str:
        """Call the configured LLM and return the response text."""
        if self.config.mock_mode or self._llm is None:
            return self._mock_response(messages)
        try:
            if self.config.model_provider == "openai":
                response = self._llm.chat.completions.create(
                    model=self.config.model_name,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000,
                )
                return response.choices[0].message.content or ""
            elif self.config.model_provider == "anthropic":
                sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
                user_msgs = [m for m in messages if m["role"] != "system"]
                response = self._llm.messages.create(
                    model=self.config.model_name,
                    max_tokens=1000,
                    system=sys_msg,
                    messages=user_msgs,
                )
                return response.content[0].text
        except Exception as e:
            return f"[LLM Error: {e}]"
        return "[No response]"

    def _mock_response(self, messages: list[dict]) -> str:
        last_user = next(
            (m["content"] for m in reversed(messages) if m["role"] == "user"), ""
        )
        return (
            f"[MOCK RESPONSE] I received your message: '{last_user[:80]}'. "
            "In a real run, the configured LLM would respond here. "
            "PALIMPSEST has classified and stored this exchange in the versioned memory store."
        )
