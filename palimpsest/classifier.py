"""
PALIMPSEST Memory Classifier
Uses an LLM to classify each memory item as verbatim, summary, or discard,
and records the rationale for each decision.
"""

import json
import re
from typing import Any

from config import Config
from palimpsest.models import ClassificationResult, MemoryCategory


CLASSIFIER_SYSTEM_PROMPT = """You are a Memory Classifier for an AI agent memory system called PALIMPSEST.
Your job is to evaluate a piece of conversation content and decide how it should be stored in long-term memory.

Categories:
- verbatim: Keep the exact content. Use for critical instructions, user preferences, key decisions, code snippets, facts that must not be paraphrased.
- summary: Compress this content. Use for useful but verbose content that can be shortened without loss of meaning.
- discard: Do not keep. Use for greetings, filler, already-covered redundant information, or content irrelevant to the current objective.

Always respond ONLY with valid JSON in the exact format shown. Do not include any explanation outside the JSON."""

CLASSIFIER_USER_TEMPLATE = """Evaluate this memory item and return a JSON classification.

CURRENT OBJECTIVE: {objective}

SESSION CONTEXT (brief): {context}

CONTENT TO CLASSIFY:
Role: {role}
Text: {content}

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "category": "verbatim" | "summary" | "discard",
  "importance_score": <float 0.0-1.0>,
  "relevance_score": <float 0.0-1.0>,
  "topic_tags": ["<tag1>", "<tag2>"],
  "rationale": "<one sentence explaining the decision>"
}}"""


class MemoryClassifier:
    """Classifies memory items using an LLM and configured thresholds."""

    def __init__(self, config: Config, llm_client: Any):
        self.config = config
        self.llm_client = llm_client

    def classify(
        self,
        item_content: str,
        role: str,
        current_objective: str,
        session_history_summary: str = "",
    ) -> ClassificationResult:
        """Classify a single memory item."""
        if self.config.mock_mode:
            return self._mock_classify(item_content)

        prompt = CLASSIFIER_USER_TEMPLATE.format(
            objective=current_objective or "General conversation",
            context=session_history_summary[:300] if session_history_summary else "No prior context.",
            role=role,
            content=item_content[:1500],
        )

        try:
            raw = self._call_llm(prompt)
            data = self._parse_json(raw)
            category = self._apply_thresholds(data)
            return ClassificationResult(
                category=category,
                importance_score=float(data.get("importance_score", 0.5)),
                relevance_score=float(data.get("relevance_score", 0.5)),
                topic_tags=data.get("topic_tags", ["general"]),
                rationale=data.get("rationale", "No rationale provided."),
            )
        except Exception as e:
            # Safe fallback: keep verbatim if classification fails
            return ClassificationResult(
                category=MemoryCategory.verbatim,
                importance_score=0.5,
                relevance_score=0.5,
                topic_tags=["unclassified"],
                rationale=f"Classification failed ({e}); defaulting to verbatim.",
            )

    def classify_batch(
        self, items: list[dict], current_objective: str
    ) -> list[ClassificationResult]:
        """Classify a batch of items."""
        return [
            self.classify(
                item_content=item.get("content", ""),
                role=item.get("role", "user"),
                current_objective=current_objective,
            )
            for item in items
        ]

    def _call_llm(self, user_prompt: str) -> str:
        if self.config.model_provider == "openai":
            response = self.llm_client.chat.completions.create(
                model=self.config.model_name,
                messages=[
                    {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.0,
                max_tokens=300,
            )
            return response.choices[0].message.content or ""
        elif self.config.model_provider == "anthropic":
            response = self.llm_client.messages.create(
                model=self.config.model_name,
                max_tokens=300,
                system=CLASSIFIER_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
            )
            return response.content[0].text
        return "{}"

    def _parse_json(self, raw: str) -> dict:
        raw = raw.strip()
        # Strip markdown code fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
        return json.loads(raw)

    def _apply_thresholds(self, data: dict) -> MemoryCategory:
        """Override LLM category based on importance score thresholds."""
        importance = float(data.get("importance_score", 0.5))
        llm_category = data.get("category", "verbatim")

        if importance >= self.config.verbatim_threshold:
            return MemoryCategory.verbatim
        if importance <= self.config.discard_threshold:
            return MemoryCategory.discard
        # Mid-range: trust LLM category but clamp to summary
        if llm_category == "discard" and importance > self.config.discard_threshold:
            return MemoryCategory.summary
        return MemoryCategory(llm_category) if llm_category in ("verbatim", "summary", "discard") else MemoryCategory.summary

    def _mock_classify(self, content: str) -> ClassificationResult:
        """Deterministic mock classifier for testing without an API key."""
        lower = content.lower()
        # Heuristics for mock mode
        if any(kw in lower for kw in ["important", "always", "must", "never", "remember", "preference", "def ", "class ", "```"]):
            return ClassificationResult(
                category=MemoryCategory.verbatim,
                importance_score=0.9,
                relevance_score=0.8,
                topic_tags=["key-instruction"],
                rationale="Mock: content contains high-importance keywords.",
            )
        if any(kw in lower for kw in ["hello", "hi ", "thanks", "okay", "sure", "got it"]):
            return ClassificationResult(
                category=MemoryCategory.discard,
                importance_score=0.1,
                relevance_score=0.1,
                topic_tags=["filler"],
                rationale="Mock: content is conversational filler.",
            )
        return ClassificationResult(
            category=MemoryCategory.summary,
            importance_score=0.5,
            relevance_score=0.5,
            topic_tags=["general"],
            rationale="Mock: content is moderately important; marked for summarization.",
        )
