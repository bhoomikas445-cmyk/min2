"""
PALIMPSEST Compression Service
Produces compact, information-dense summaries for memory items classified as 'SUMMARIZE'.
Preserves key entities, numbers, technical constraints, and actionable decisions while
reducing token footprint.
"""

import re
from typing import Tuple, Dict, Any, Optional
from services.token_counter import TokenCounter
from services.llm_provider import LLMProvider


class CompressionService:
    """Handles text summarization with fallback and token measurement."""

    def __init__(self, llm_provider: Optional[LLMProvider] = None):
        self.llm_provider = llm_provider or LLMProvider()

    def summarize(self, text: str, objective: str = "") -> Tuple[str, int, str]:
        """
        Summarize the given text.
        Returns:
            (summary_text, stored_token_count, compression_method)
        """
        if not text or len(text.strip()) == 0:
            return "", 0, "empty"

        orig_tokens, _ = TokenCounter.count_tokens(text)

        # If already very brief (< 25 tokens), summarization is not needed
        if orig_tokens < 25:
            return text.strip(), orig_tokens, "as_is"

        # Try LLM if configured
        if self.llm_provider.is_configured:
            sys_prompt = (
                "You are an expert context compression engine. Summarize the provided text into a compact, "
                "dense factual summary. Retain all key technical terms, constraints, architecture choices, "
                "and decisions. Strip all conversational pleasantries, repetition, and filler."
            )
            user_prompt = f"Objective: {objective}\nContent to summarize:\n{text}"
            res = self.llm_provider.generate_chat_response(sys_prompt, user_prompt, temperature=0.0)
            if not res.get("is_fallback") and res.get("content"):
                summary = res["content"].strip()
                tokens, _ = TokenCounter.count_tokens(summary)
                return summary, tokens, "llm_compression"

        # Deterministic Extractive / Heuristic Summarization Fallback
        summary, method = self._heuristic_compress(text)
        tokens, _ = TokenCounter.count_tokens(summary)
        return summary, tokens, method

    def _heuristic_compress(self, text: str) -> Tuple[str, str]:
        """
        Deterministic, sentence-ranked extractive compression:
        Identifies key informative sentences, extracts core statements, removes conversational fluff.
        """
        lines = [line.strip() for line in re.split(r"[.\n;]+", text) if line.strip()]
        if not lines:
            return text[:120], "heuristic_truncate"

        # Keywords that denote high factual content or decisions
        high_value_keywords = {
            "use", "using", "require", "required", "database", "api", "framework",
            "model", "postgres", "fastapi", "react", "token", "auth", "jwt",
            "docker", "deploy", "port", "test", "coverage", "always", "never",
            "should", "must", "decided", "chose", "configured", "setup"
        }

        # Filter and rank sentences
        ranked = []
        for line in lines:
            words = set(re.findall(r"\b\w+\b", line.lower()))
            score = len(words.intersection(high_value_keywords))
            # Penalize conversational fluff
            if any(fluff in line.lower() for fluff in ["hello", "how are you", "sounds good", "thanks", "sure thing"]):
                score -= 3
            ranked.append((score, line))

        # Select top sentences
        ranked.sort(key=lambda x: x[0], reverse=True)
        selected = [item[1] for item in ranked[:3] if item[0] >= 0]

        if not selected:
            selected = lines[:2]

        # Combine cleanly
        compressed = ". ".join(selected) + "."
        # Clean extra spaces
        compressed = re.sub(r"\s+", " ", compressed).strip()
        return compressed, "deterministic_extractive_heuristic"
