"""
PALIMPSEST Context Reconstructor
Builds the final context window within a token budget from classified memory items.
"""

from __future__ import annotations

import tiktoken

from config import Config
from palimpsest.models import ContextWindow, MemoryCategory, MemoryItem


class ContextReconstructor:
    """Assembles the context to be sent to the LLM within the token budget."""

    def __init__(self, config: Config):
        self.config = config
        try:
            self._enc = tiktoken.get_encoding("cl100k_base")
        except Exception:
            self._enc = None

    def count_tokens(self, text: str) -> int:
        """Count tokens in a string using tiktoken (cl100k_base)."""
        if self._enc:
            return len(self._enc.encode(text))
        # Fallback: rough approximation
        return len(text) // 4

    def reconstruct(
        self,
        verbatim_items: list[MemoryItem],
        summary_items: list[MemoryItem],
        retrieved_items: list[MemoryItem],
        query: str,
        compressor,
    ) -> ContextWindow:
        """
        Build a ContextWindow within the token budget.
        Priority: verbatim → topic summaries → retrieved items by relevance.
        """
        budget = self.config.token_budget
        used = 0
        included: list[MemoryItem] = []
        notes: list[str] = []

        # 1. Always include verbatim items (mandatory)
        for item in verbatim_items:
            tokens = self.count_tokens(item.content)
            if used + tokens <= budget:
                item.token_count = tokens
                included.append(item)
                used += tokens
            else:
                notes.append(f"Verbatim item truncated (budget exceeded): {item.id[:8]}...")

        notes.append(f"Verbatim: {len(included)} items, {used} tokens used.")

        # 2. Add topic-compressed summaries of summary items
        if summary_items:
            topic_summaries = compressor.compress_by_topic(summary_items)
            from palimpsest.models import MessageRole
            for topic, summary_text in topic_summaries.items():
                tokens = self.count_tokens(summary_text)
                if used + tokens <= budget:
                    synthetic = MemoryItem(
                        id=f"summary-{topic}",
                        session_id=summary_items[0].session_id if summary_items else "",
                        version_id=summary_items[0].version_id if summary_items else "",
                        role=MessageRole.system,
                        content=f"[MEMORY SUMMARY — {topic}]: {summary_text}",
                        category=MemoryCategory.summary,
                        token_count=tokens,
                        topic_tags=[topic],
                        decision_rationale=f"Compressed {len(summary_items)} items about '{topic}'.",
                    )
                    included.append(synthetic)
                    used += tokens
                else:
                    notes.append(f"Summary for topic '{topic}' skipped (budget).")
            notes.append(f"Summaries added. Tokens used: {used}.")

        # 3. Add retrieved items sorted by relevance score (descending)
        retrieved_sorted = sorted(retrieved_items, key=lambda x: x.relevance_score, reverse=True)
        added_retrieved = 0
        seen_ids = {i.id for i in included}
        for item in retrieved_sorted:
            if item.id in seen_ids:
                continue
            tokens = self.count_tokens(item.content)
            if used + tokens <= budget:
                item.token_count = tokens
                included.append(item)
                used += tokens
                added_retrieved += 1
                seen_ids.add(item.id)
            else:
                notes.append(f"Retrieved item {item.id[:8]} skipped (budget).")

        notes.append(f"Retrieved: {added_retrieved} items added. Total tokens: {used}/{budget}.")

        return ContextWindow(
            version_id=verbatim_items[0].version_id if verbatim_items else "",
            items=included,
            total_tokens=used,
            token_budget=budget,
            reconstruction_notes=" | ".join(notes),
        )

    def to_messages(self, window: ContextWindow) -> list[dict]:
        """Convert a ContextWindow to an OpenAI-style messages list."""
        messages = []
        for item in window.items:
            role = item.role.value
            # Map 'tool' role to 'user' for compatibility
            if role == "tool":
                role = "user"
            messages.append({"role": role, "content": item.content})
        return messages
