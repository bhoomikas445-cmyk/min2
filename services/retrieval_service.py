"""
PALIMPSEST Retrieval Service
Performs hybrid keyword, n-gram, and priority scoring to identify relevant memories
for a target query and current project objective.
Guarantees that explicit constraints and active instructions receive prioritized ranking.
"""

import re
import math
from typing import List, Dict, Any, Tuple


class RetrievalService:
    """Ranks and retrieves memory items for context reconstruction."""

    @staticmethod
    def score_memory(
        item: Dict[str, Any],
        query: str,
        objective: str = ""
    ) -> Tuple[float, str]:
        """
        Calculates relevance score of an individual memory item against a query.
        Returns:
            (relevance_score, reason)
        """
        content = item.get("content", "")
        summary = item.get("summary_content") or ""
        text_to_match = (content + " " + summary).lower()

        # Tokenize query and objective
        q_words = [w for w in re.findall(r"\b\w{2,}\b", query.lower()) if len(w) > 2]
        obj_words = [w for w in re.findall(r"\b\w{3,}\b", objective.lower()) if len(w) > 3]

        score = 0.0
        reasons = []

        # 1. Mandatory Instruction / Constraint Protection
        is_instruction = item.get("is_instruction_or_constraint", False)
        if is_instruction:
            score += 0.50
            reasons.append("Mandatory instruction/constraint priority")

        # 2. Query Term Overlap
        if q_words:
            matched_terms = [w for w in q_words if w in text_to_match]
            overlap_ratio = len(matched_terms) / float(len(q_words))
            score += overlap_ratio * 0.40
            if matched_terms:
                reasons.append(f"Matched query terms: {', '.join(matched_terms[:3])}")

        # 3. Project Objective Alignment
        if obj_words:
            matched_obj = [w for w in obj_words if w in text_to_match]
            if matched_obj:
                score += 0.15
                reasons.append("Aligned with project objective")

        # 4. Memory Category Weight
        cat = item.get("category", "")
        if cat == "KEEP VERBATIM":
            score += 0.15
        elif cat == "SUMMARIZE":
            score += 0.10
        elif cat == "DISCARD":
            score -= 0.60  # Severely penalized; discarded memories do not enter context

        # 5. Base Importance
        imp = item.get("importance_score", 0.5)
        score += imp * 0.10

        final_score = max(0.0, min(1.0, score))
        reason_str = "; ".join(reasons) if reasons else "General background memory"
        return final_score, reason_str

    @classmethod
    def rank_memories(
        cls,
        memories: List[Dict[str, Any]],
        query: str,
        objective: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Rank all memories by relevance to query.
        Excludes DISCARD memories unless explicitly forced.
        """
        scored = []
        for mem in memories:
            score, reason = cls.score_memory(mem, query, objective)
            mem_copy = dict(mem)
            mem_copy["retrieval_score"] = round(score, 3)
            mem_copy["retrieval_reason"] = reason
            scored.append(mem_copy)

        # Sort: first instructions, then by score descending
        scored.sort(
            key=lambda x: (
                1 if x.get("is_instruction_or_constraint") else 0,
                x["retrieval_score"],
                x.get("importance_score", 0.0)
            ),
            reverse=True
        )
        return scored
