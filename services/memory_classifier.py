"""
PALIMPSEST Memory Decision Engine (Classifier)
Evaluates memory items across 6 fundamental criteria:
1. Importance
2. Relevance to current project objective
3. Recency & degradation
4. Uniqueness & redundancy
5. Explicit instruction / constraint protection
6. Token cost

Assigns: KEEP VERBATIM, SUMMARIZE, or DISCARD.
Provides transparent explanations, scores, and token footprints.
Supports both deterministic rule-based evaluation and optional LLM-assisted evaluation.
"""

import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from config import Config
from services.token_counter import TokenCounter
from services.llm_provider import LLMProvider
from services.compression_service import CompressionService


# High-priority instruction/constraint indicators
INSTRUCTION_PATTERNS = [
    r"\b(must|always|never|mandatory|required|strictly|do not|don't|shall not|non-negotiable|forbidden)\b",
    r"\b(rule|constraint|requirement|specification|policy|compliance standard)\b",
    r"\b(remember\s+(that|to)|keep in mind|note that|make sure|ensure that)\b",
    r"\b(strictly comply|hipaa compliance|gdpr compliance|security constraint)\b",
    r"\b(\d+%\s+coverage|test coverage requirement)\b",
]

# Conversational filler patterns
FILLER_PATTERNS = [
    r"\b(hello|hi|hey|howdy|good\s+(morning|afternoon|evening))\b",
    r"\b(thanks|thank you|thx|cheers|sounds good|great|cool|awesome|perfect)\b",
    r"\b(okay|ok|sure|got it|roger that|understood|will do)\b",
    r"\b(bye|goodbye|see you|catch you later)\b",
    r"\b(tell me a joke|how is the weather|what's up)\b",
]


class MemoryClassifier:
    """Core memory decision engine."""

    def __init__(self, config: Optional[Config] = None, llm_provider: Optional[LLMProvider] = None):
        self.config = config or Config()
        self.llm_provider = llm_provider or LLMProvider(self.config)
        self.compression_service = CompressionService(self.llm_provider)

    def evaluate_item(
        self,
        content: str,
        role: str = "user",
        objective: str = "",
        existing_items: Optional[List[Dict[str, Any]]] = None,
        source_message_id: Optional[str] = None,
        source_document: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Evaluate an item and produce an auditable memory decision.
        """
        content_clean = content.strip()
        orig_tokens, token_method = TokenCounter.count_tokens(content_clean)

        # 1. Check for explicit instructions and constraints
        is_instruction = self._detect_instruction_or_constraint(content_clean)
        
        # 2. Check for conversational filler / noise
        is_filler = self._detect_filler(content_clean)

        # 3. Calculate redundancy against existing memories
        redundancy_score, duplicate_of_id = self._calculate_redundancy(content_clean, existing_items or [])

        # 4. Calculate relevance to the project objective
        relevance_score = self._calculate_relevance(content_clean, objective)

        # 5. Base importance calculation
        importance_score = self._calculate_importance(
            content=content_clean,
            role=role,
            is_instruction=is_instruction,
            is_filler=is_filler,
            redundancy=redundancy_score,
            relevance=relevance_score,
        )

        # 6. Check if external LLM should be consulted
        llm_decision = None
        if self.llm_provider.is_configured and not is_filler:
            llm_decision = self._consult_llm(content_clean, role, objective, is_instruction)

        # 7. Final Category Decision
        action, explanation, processing_method = self._assign_action(
            importance=importance_score,
            is_instruction=is_instruction,
            is_filler=is_filler,
            redundancy=redundancy_score,
            relevance=relevance_score,
            llm_decision=llm_decision,
        )

        # 8. Compute stored token count and compressed content
        summary_content = None
        if action == "KEEP VERBATIM":
            stored_tokens = orig_tokens
        elif action == "SUMMARIZE":
            summary_content, stored_tokens, comp_method = self.compression_service.summarize(content_clean, objective)
        else:  # DISCARD
            stored_tokens = 0

        # Topic tags extraction
        topic_tags = self._extract_tags(content_clean, is_instruction)

        return {
            "content": content_clean,
            "source_message_id": source_message_id,
            "source_document": source_document,
            "category": action,
            "action": action,
            "explanation": explanation,
            "importance_score": float(round(importance_score, 2)),
            "relevance_score": float(round(relevance_score, 2)),
            "recency_score": 1.0,  # Fresh item
            "redundancy_score": float(round(redundancy_score, 2)),
            "is_instruction_or_constraint": is_instruction,
            "topic_tags": topic_tags,
            "original_token_count": orig_tokens,
            "stored_token_count": stored_tokens,
            "summary_content": summary_content,
            "processing_method": processing_method,
            "timestamp": datetime.now(timezone.utc),
        }

    def _detect_instruction_or_constraint(self, text: str) -> bool:
        """Determines if the text contains binding instructions, architecture constraints, or rules."""
        lower = text.lower()
        # Code snippets or definitions are always treated as high-importance constraints/specs
        if "```" in text or "def " in text or "class " in text or "SELECT " in text:
            return True
        for pattern in INSTRUCTION_PATTERNS:
            if re.search(pattern, lower):
                return True
        return False

    def _detect_filler(self, text: str) -> bool:
        """Detects low-value conversational pleasantries, small talk, or acknowledgments."""
        lower = text.lower().strip()
        for pat in FILLER_PATTERNS:
            if re.search(pat, lower):
                return True
        if lower in {"ok", "okay", "yes", "no", "cool", "thanks", "hello", "hi", "bye", "good"}:
            return True
        return False

    def _calculate_redundancy(self, text: str, existing_items: List[Dict[str, Any]]) -> Tuple[float, Optional[str]]:
        """Calculates token Jaccard similarity against existing items."""
        if not existing_items:
            return 0.0, None

        words_curr = set(re.findall(r"\b\w{3,}\b", text.lower()))
        if not words_curr:
            return 0.0, None

        max_sim = 0.0
        dup_id = None

        for item in existing_items:
            other_text = item.get("content", "")
            words_other = set(re.findall(r"\b\w{3,}\b", other_text.lower()))
            if not words_other:
                continue

            intersection = len(words_curr.intersection(words_other))
            union = len(words_curr.union(words_other))
            sim = intersection / float(union) if union > 0 else 0.0

            if sim > max_sim:
                max_sim = sim
                dup_id = item.get("id")

        return max_sim, dup_id

    def _calculate_relevance(self, text: str, objective: str) -> float:
        """Calculates relevance score between content and project objective."""
        if not objective:
            return 0.6  # Default neutral relevance

        obj_words = set(re.findall(r"\b\w{3,}\b", objective.lower()))
        text_words = set(re.findall(r"\b\w{3,}\b", text.lower()))

        if not obj_words:
            return 0.5

        overlap = len(obj_words.intersection(text_words))
        score = min(1.0, 0.3 + (overlap * 0.25))
        return score

    def _calculate_importance(
        self,
        content: str,
        role: str,
        is_instruction: bool,
        is_filler: bool,
        redundancy: float,
        relevance: float,
    ) -> float:
        """Computes composite importance score (0.0 to 1.0)."""
        if is_filler:
            return 0.1

        # Explicit instructions receive top priority
        if is_instruction:
            base = 0.88 + (0.10 * relevance)
            # Penalize only if it's completely duplicate
            if redundancy > 0.85:
                base -= 0.25
            return min(1.0, max(0.70, base))

        # Role weighting
        role_weight = 0.55 if role in ("user", "system") else 0.45

        # Length / informational density bonus
        length_factor = min(0.2, len(content) / 800.0)

        # Redundancy penalty
        red_penalty = redundancy * 0.4

        score = (role_weight * 0.4) + (relevance * 0.4) + length_factor - red_penalty
        return max(0.1, min(0.95, score))

    def _assign_action(
        self,
        importance: float,
        is_instruction: bool,
        is_filler: bool,
        redundancy: float,
        relevance: float,
        llm_decision: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, str, str]:
        """
        Determines the category and provides a comprehensive explanation.
        Guarantees that explicit instructions are NEVER discarded simply because of age.
        """
        # If an explicit instruction exists, protect it
        if is_instruction:
            if redundancy > 0.90:
                return (
                    "DISCARD",
                    f"Protected instruction discarded solely because it is an exact duplicate of existing recorded constraint (similarity {redundancy:.0%}).",
                    "rule_based_protection",
                )
            return (
                "KEEP VERBATIM",
                f"Explicit instruction or architectural constraint detected (Importance: {importance:.2f}). Protected verbatim for exact policy adherence.",
                "rule_based_protection",
            )

        if is_filler:
            return (
                "DISCARD",
                f"Conversational filler / trivial pleasantry detected (Importance: {importance:.2f}). Excluded from active memory to conserve token budget.",
                "rule_based_heuristic",
            )

        if redundancy > 0.80:
            return (
                "DISCARD",
                f"Redundant information (redundancy score {redundancy:.2f}). Key details already present in memory state.",
                "rule_based_heuristic",
            )

        # If LLM generated a structured decision
        if llm_decision and not llm_decision.get("is_fallback"):
            cat = llm_decision.get("category", "").upper()
            expl = llm_decision.get("rationale", "")
            if cat in ("KEEP VERBATIM", "SUMMARIZE", "DISCARD"):
                return cat, f"[LLM Verified]: {expl}", "llm"

        # Standard Threshold Action
        if importance >= self.config.VERBATIM_THRESHOLD:
            return (
                "KEEP VERBATIM",
                f"High informational value (Importance: {importance:.2f} >= threshold {self.config.VERBATIM_THRESHOLD}). Retained verbatim.",
                "rule_based_threshold",
            )
        elif importance <= self.config.DISCARD_THRESHOLD:
            return (
                "DISCARD",
                f"Low utility or marginal relevance (Importance: {importance:.2f} <= threshold {self.config.DISCARD_THRESHOLD}). Excluded from context.",
                "rule_based_threshold",
            )
        else:
            return (
                "SUMMARIZE",
                f"Moderate informational value (Importance: {importance:.2f}). Eligible for compression to preserve core semantics at lower token cost.",
                "rule_based_threshold",
            )

    def _consult_llm(self, content: str, role: str, objective: str, is_instruction: bool) -> Optional[Dict[str, Any]]:
        """Optional structured LLM consultation with schema validation."""
        sys_prompt = (
            "You are the memory decision classifier for PALIMPSEST. Analyze the user statement and classify it "
            "into 'KEEP VERBATIM', 'SUMMARIZE', or 'DISCARD'. Return a JSON object with keys: "
            "'category', 'importance_score', 'relevance_score', and 'rationale'."
        )
        user_prompt = f"Objective: {objective}\nRole: {role}\nInstruction flagged: {is_instruction}\nText:\n{content[:1000]}"
        res = self.llm_provider.structured_completion(sys_prompt, user_prompt)
        return res if not res.get("is_fallback") and res.get("data") else None

    def _extract_tags(self, text: str, is_instruction: bool) -> List[str]:
        """Extracts descriptive topic tags."""
        tags = set()
        if is_instruction:
            tags.add("instruction")
            tags.add("constraint")

        common_tags = {
            "database": ["postgres", "sql", "db", "sqlite", "redis", "mongodb"],
            "auth": ["jwt", "oauth", "token", "login", "auth", "security"],
            "api": ["fastapi", "flask", "rest", "endpoint", "crud", "http"],
            "architecture": ["docker", "container", "microservice", "async", "orm", "sqlalchemy"],
            "quality": ["test", "coverage", "pytest", "unit", "lint", "ci/cd"],
            "compliance": ["hipaa", "gdpr", "phi", "pii", "audit"],
        }

        lower = text.lower()
        for tag, keywords in common_tags.items():
            if any(k in lower for k in keywords):
                tags.add(tag)

        if not tags:
            tags.add("general")

        return sorted(list(tags))
