"""
PALIMPSEST Model-Independent LLM Provider Service
Provides a unified abstraction over external LLMs (OpenAI, Anthropic)
with a deterministic rule-based fallback provider.
Crucially, never masks fallback results as LLM-generated: all responses explicitly
declare their generation source ("llm" vs "rule_based_fallback").
"""

import json
import re
from typing import Dict, Any, Optional
from config import Config


class LLMProvider:
    """Unified LLM service layer with transparent fallback."""

    def __init__(self, config: Optional[Config] = None):
        self.config = config or Config()
        self.is_configured = self.config.is_llm_configured()
        self.provider_name = self.config.LLM_PROVIDER if self.is_configured else "rule_based_fallback"
        self.model_name = self.config.DEFAULT_MODEL if self.is_configured else "deterministic-heuristic-engine"
        self._openai_client = None
        self._anthropic_client = None

        if self.is_configured:
            self._init_clients()

    def _init_clients(self):
        try:
            if self.config.LLM_PROVIDER == "openai" and self.config.OPENAI_API_KEY:
                from openai import OpenAI
                self._openai_client = OpenAI(api_key=self.config.OPENAI_API_KEY)
            elif self.config.LLM_PROVIDER == "anthropic" and self.config.ANTHROPIC_API_KEY:
                from anthropic import Anthropic
                self._anthropic_client = Anthropic(api_key=self.config.ANTHROPIC_API_KEY)
        except Exception:
            self.is_configured = False
            self.provider_name = "rule_based_fallback"
            self.model_name = "deterministic-heuristic-engine"

    def generate_chat_response(self, system_prompt: str, user_prompt: str, temperature: float = 0.2) -> Dict[str, Any]:
        """Generate conversational or test response."""
        if not self.is_configured:
            # Deterministic simulated response
            return {
                "content": f"[Simulated Output]: Processed query based on preserved context. User requested: '{user_prompt[:80]}...'",
                "source": "rule_based_fallback",
                "model": "deterministic-heuristic-engine",
                "is_fallback": True,
            }

        try:
            if self.provider_name == "openai" and self._openai_client:
                res = self._openai_client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=temperature,
                    max_tokens=600,
                )
                return {
                    "content": res.choices[0].message.content or "",
                    "source": "llm",
                    "model": self.model_name,
                    "is_fallback": False,
                }
            elif self.provider_name == "anthropic" and self._anthropic_client:
                res = self._anthropic_client.messages.create(
                    model=self.model_name,
                    max_tokens=600,
                    system=system_prompt,
                    messages=[{"role": "user", "content": user_prompt}],
                    temperature=temperature,
                )
                return {
                    "content": res.content[0].text,
                    "source": "llm",
                    "model": self.model_name,
                    "is_fallback": False,
                }
        except Exception as e:
            # Safe degradation with transparent notice
            return {
                "content": f"[Fallback triggered due to API error: {str(e)}]",
                "source": "rule_based_fallback",
                "model": "deterministic-heuristic-engine",
                "is_fallback": True,
                "error": str(e),
            }

    def structured_completion(self, system_prompt: str, user_prompt: str) -> Dict[str, Any]:
        """Request structured JSON completion from LLM or return None on fallback."""
        if not self.is_configured:
            return {"source": "rule_based_fallback", "is_fallback": True, "data": None}

        try:
            if self.provider_name == "openai" and self._openai_client:
                res = self._openai_client.chat.completions.create(
                    model=self.model_name,
                    response_format={"type": "json_object"},
                    messages=[
                        {"role": "system", "content": system_prompt + "\nReturn valid JSON."},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.0,
                    max_tokens=400,
                )
                raw = res.choices[0].message.content or "{}"
                return {
                    "source": "llm",
                    "model": self.model_name,
                    "is_fallback": False,
                    "data": json.loads(raw),
                }
        except Exception as e:
            return {"source": "rule_based_fallback", "is_fallback": True, "error": str(e), "data": None}

        return {"source": "rule_based_fallback", "is_fallback": True, "data": None}
