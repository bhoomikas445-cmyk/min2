"""
PALIMPSEST Memory Compressor
Summarizes memory items marked as 'summary' using an LLM.
"""

from typing import Any

from config import Config
from palimpsest.models import MemoryItem


COMPRESS_SYSTEM = """You are a memory compression assistant. Your task is to produce a concise, 
accurate summary of the provided conversation content. Preserve all key facts, decisions, 
preferences, and instructions. Remove redundancy and filler. Be as brief as possible while 
retaining all important information."""


class MemoryCompressor:
    """Compresses memory items into shorter summaries."""

    def __init__(self, config: Config, llm_client: Any):
        self.config = config
        self.llm_client = llm_client

    def compress(self, items: list[MemoryItem]) -> str:
        """Summarize a list of memory items into one summary string."""
        if not items:
            return ""
        if self.config.mock_mode:
            return self._mock_compress(items)
        combined = "\n\n".join(
            f"[{item.role.value.upper()}]: {item.content}" for item in items
        )
        prompt = f"Summarize the following conversation content concisely:\n\n{combined}"
        return self._call_llm(prompt)

    def compress_single(self, item: MemoryItem) -> str:
        """Summarize a single memory item."""
        if self.config.mock_mode:
            return self._mock_compress([item])
        prompt = f"Summarize the following message concisely:\n\n[{item.role.value.upper()}]: {item.content}"
        return self._call_llm(prompt)

    def compress_by_topic(self, items: list[MemoryItem]) -> dict[str, str]:
        """Group items by topic tags and summarize each group."""
        groups: dict[str, list[MemoryItem]] = {}
        for item in items:
            for tag in (item.topic_tags or ["general"]):
                groups.setdefault(tag, []).append(item)
        return {tag: self.compress(group) for tag, group in groups.items()}

    def _call_llm(self, user_prompt: str) -> str:
        try:
            if self.config.model_provider == "openai":
                response = self.llm_client.chat.completions.create(
                    model=self.config.model_name,
                    messages=[
                        {"role": "system", "content": COMPRESS_SYSTEM},
                        {"role": "user", "content": user_prompt[:4000]},
                    ],
                    temperature=0.2,
                    max_tokens=400,
                )
                return response.choices[0].message.content or ""
            elif self.config.model_provider == "anthropic":
                response = self.llm_client.messages.create(
                    model=self.config.model_name,
                    max_tokens=400,
                    system=COMPRESS_SYSTEM,
                    messages=[{"role": "user", "content": user_prompt[:4000]}],
                )
                return response.content[0].text
        except Exception as e:
            return f"[Summary unavailable: {e}]"
        return ""

    def _mock_compress(self, items: list[MemoryItem]) -> str:
        parts = [f"[{i.role.value}] {i.content[:80]}..." for i in items]
        return "SUMMARY: " + " | ".join(parts)
