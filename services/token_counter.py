"""
PALIMPSEST Token Counter Service
Provides precise token estimation using tiktoken (cl100k_base / o200k_base)
with a documented deterministic character/word-ratio fallback estimator.
"""

from typing import Tuple

try:
    import tiktoken
    _TIKTOKEN_AVAILABLE = True
    try:
        _ENCODER = tiktoken.get_encoding("cl100k_base")
    except Exception:
        _ENCODER = None
except ImportError:
    _TIKTOKEN_AVAILABLE = False
    _ENCODER = None


class TokenCounter:
    """Estimates and counts tokens with clear provenance of the counting method."""

    @staticmethod
    def count_tokens(text: str) -> Tuple[int, str]:
        """
        Count tokens for a given string.
        Returns:
            (token_count, method_name)
        """
        if not text:
            return 0, "empty"

        if _TIKTOKEN_AVAILABLE and _ENCODER is not None:
            try:
                tokens = _ENCODER.encode(text)
                return len(tokens), "tiktoken:cl100k_base"
            except Exception:
                pass

        # Documented Fallback Estimator:
        # Standard OpenAI rule-of-thumb: ~4 characters per token in English,
        # or ~0.75 words per token (1.33 tokens per word).
        # We blend character length and word count for robust estimation.
        words = text.split()
        char_estimate = len(text) / 4.0
        word_estimate = len(words) * 1.3
        estimated = int(round((char_estimate * 0.6) + (word_estimate * 0.4)))
        return max(1, estimated), "fallback:heuristic_char_word_ratio"

    @staticmethod
    def truncate_to_budget(text: str, budget: int) -> Tuple[str, int]:
        """Truncate text to fit within a given token budget."""
        if budget <= 0:
            return "", 0

        count, _ = TokenCounter.count_tokens(text)
        if count <= budget:
            return text, count

        if _TIKTOKEN_AVAILABLE and _ENCODER is not None:
            try:
                tokens = _ENCODER.encode(text)
                truncated_tokens = tokens[:budget]
                decoded = _ENCODER.decode(truncated_tokens)
                return decoded, len(truncated_tokens)
            except Exception:
                pass

        # Fallback truncation based on character ratio (4 chars/token)
        max_chars = budget * 4
        truncated_text = text[:max_chars].rsplit(" ", 1)[0]
        c, _ = TokenCounter.count_tokens(truncated_text)
        return truncated_text, c
