"""
PALIMPSEST Baseline Agent
A simple rolling-window agent with no classification, versioning, or rationales.
Used as the comparison baseline in evaluation.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from config import Config


def _build_llm_client(config: Config) -> Any:
    if config.mock_mode:
        return None
    if config.model_provider == "openai" and config.openai_api_key:
        from openai import OpenAI
        return OpenAI(api_key=config.openai_api_key)
    if config.model_provider == "anthropic" and config.anthropic_api_key:
        import anthropic
        return anthropic.Anthropic(api_key=config.anthropic_api_key)
    return None


class BaselineAgent:
    """
    Baseline agent: keeps all conversation history in a rolling window.
    When token budget is exceeded, oldest messages are truncated (no classification).
    """

    def __init__(self, config: Config | None = None):
        self.config = config or Config()
        self._llm = _build_llm_client(self.config)
        self._history: list[dict] = []
        self._objective: str = ""
        self._session_id: str = ""

        # Metrics
        self.total_tokens: int = 0
        self.total_latency_ms: float = 0.0
        self.turn_count: int = 0

    def start_session(self, session_id: str | None = None, objective: str = ""):
        self._session_id = session_id or str(uuid.uuid4())
        self._objective = objective
        self._history = []
        if objective:
            self._history.append({
                "role": "system",
                "content": f"Objective: {objective}",
            })

    def chat(self, user_message: str) -> str:
        t0 = time.time()
        self._history.append({"role": "user", "content": user_message})

        # Truncate if over budget (remove oldest non-system messages)
        self._truncate_to_budget()

        response = self._call_llm(self._history)
        latency = (time.time() - t0) * 1000

        self._history.append({"role": "assistant", "content": response})
        tokens = self._count_tokens_approx(user_message + response)
        self.total_tokens += tokens
        self.total_latency_ms += latency
        self.turn_count += 1
        return response

    def _truncate_to_budget(self):
        """Remove oldest non-system messages until within token budget."""
        while True:
            total = sum(self._count_tokens_approx(m["content"]) for m in self._history)
            if total <= self.config.token_budget:
                break
            # Find first non-system message to remove
            for i, msg in enumerate(self._history):
                if msg["role"] != "system":
                    self._history.pop(i)
                    break
            else:
                break  # Only system messages remain

    def _count_tokens_approx(self, text: str) -> int:
        try:
            import tiktoken
            enc = tiktoken.get_encoding("cl100k_base")
            return len(enc.encode(text))
        except Exception:
            return len(text) // 4

    def _call_llm(self, messages: list[dict]) -> str:
        if self.config.mock_mode or self._llm is None:
            last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
            return f"[BASELINE MOCK] Response to: '{last[:80]}'"
        try:
            if self.config.model_provider == "openai":
                resp = self._llm.chat.completions.create(
                    model=self.config.model_name,
                    messages=messages,
                    temperature=0.7,
                    max_tokens=1000,
                )
                return resp.choices[0].message.content or ""
            elif self.config.model_provider == "anthropic":
                sys_msg = next((m["content"] for m in messages if m["role"] == "system"), "")
                user_msgs = [m for m in messages if m["role"] != "system"]
                resp = self._llm.messages.create(
                    model=self.config.model_name,
                    max_tokens=1000,
                    system=sys_msg,
                    messages=user_msgs,
                )
                return resp.content[0].text
        except Exception as e:
            return f"[Error: {e}]"
        return ""

    def get_metrics(self) -> dict:
        return {
            "total_tokens": self.total_tokens,
            "estimated_cost_usd": self.total_tokens * 0.15 / 1_000_000,
            "avg_latency_ms": self.total_latency_ms / max(self.turn_count, 1),
            "turn_count": self.turn_count,
        }
