"""
PALIMPSEST Context Reconstruction Builder
Assembles an optimized, token-budget-aware context package for a new user query.
Ensures strict provenance, priority protection for constraints, and transparent inclusion/exclusion auditing.
"""

from typing import List, Dict, Any, Optional
from services.token_counter import TokenCounter
from services.retrieval_service import RetrievalService


class ContextBuilder:
    """Builds reconstructed context packages respecting token budgets and constraints."""

    @classmethod
    def build_context(
        cls,
        query: str,
        objective: str,
        memories: List[Dict[str, Any]],
        token_budget: int = 2048,
    ) -> Dict[str, Any]:
        """
        Constructs context package for the given query and memory state.
        """
        warnings = []
        included = []
        excluded = []
        selected_ids = []

        # 1. Rank memories
        ranked_memories = RetrievalService.rank_memories(memories, query, objective)

        # 2. Check critical instructions requirement
        critical_instructions = [
            m for m in ranked_memories
            if m.get("is_instruction_or_constraint") and m.get("category") != "DISCARD"
        ]
        
        req_inst_tokens = sum(
            m.get("stored_token_count", m.get("original_token_count", 0))
            for m in critical_instructions
        )

        if req_inst_tokens > token_budget:
            warnings.append(
                f"CRITICAL TOKEN BUDGET WARNING: Configured token budget of {token_budget} tokens is insufficient "
                f"to preserve all {len(critical_instructions)} critical instructions and constraints "
                f"({req_inst_tokens} tokens required). Increase token budget to prevent instruction loss!"
            )

        # 3. Budget accounting
        current_tokens = 0
        # Overhead estimate for context formatting headers
        overhead_tokens = 40
        current_tokens += overhead_tokens

        # Phase A: Mandatory constraints & instructions first
        for mem in critical_instructions:
            content_to_use = mem.get("content", "")
            cost = mem.get("stored_token_count") or TokenCounter.count_tokens(content_to_use)[0]

            if current_tokens + cost <= token_budget:
                current_tokens += cost
                included.append({
                    "id": mem.get("id"),
                    "category": mem.get("category"),
                    "is_instruction": True,
                    "text_used": content_to_use,
                    "token_cost": cost,
                    "retrieval_score": mem.get("retrieval_score", 1.0),
                    "retrieval_reason": mem.get("retrieval_reason", "Mandatory constraint"),
                    "source": mem.get("source_document") or f"Msg: {mem.get('source_message_id', 'N/A')}",
                    "tags": mem.get("topic_tags", []),
                })
                selected_ids.append(mem.get("id"))
            else:
                excluded.append({
                    "id": mem.get("id"),
                    "category": mem.get("category"),
                    "is_instruction": True,
                    "token_cost": cost,
                    "exclusion_reason": f"Insufficient token budget ({current_tokens}/{token_budget} tokens already used). Critical constraint could not fit!",
                })

        # Phase B: Ranked factual & summarized items
        remaining_memories = [
            m for m in ranked_memories
            if m.get("id") not in selected_ids
        ]

        for mem in remaining_memories:
            cat = mem.get("category", "")
            if cat == "DISCARD":
                excluded.append({
                    "id": mem.get("id"),
                    "category": cat,
                    "is_instruction": False,
                    "token_cost": mem.get("original_token_count", 0),
                    "exclusion_reason": "Excluded by memory engine (Action: DISCARD - filler, redundant, or low utility).",
                })
                continue

            # Determine text content to inject: verbatim or summary
            if cat == "SUMMARIZE" and mem.get("summary_content"):
                text_to_use = mem.get("summary_content")
                cost = mem.get("stored_token_count") or TokenCounter.count_tokens(text_to_use)[0]
            else:
                text_to_use = mem.get("content", "")
                cost = mem.get("stored_token_count") or mem.get("original_token_count") or TokenCounter.count_tokens(text_to_use)[0]

            if current_tokens + cost <= token_budget:
                current_tokens += cost
                included.append({
                    "id": mem.get("id"),
                    "category": cat,
                    "is_instruction": False,
                    "text_used": text_to_use,
                    "token_cost": cost,
                    "retrieval_score": mem.get("retrieval_score", 0.0),
                    "retrieval_reason": mem.get("retrieval_reason", "Relevant background fact"),
                    "source": mem.get("source_document") or f"Msg: {mem.get('source_message_id', 'N/A')}",
                    "tags": mem.get("topic_tags", []),
                })
                selected_ids.append(mem.get("id"))
            else:
                excluded.append({
                    "id": mem.get("id"),
                    "category": cat,
                    "is_instruction": False,
                    "token_cost": cost,
                    "exclusion_reason": f"Exceeded remaining token budget ({current_tokens}/{token_budget} tokens committed).",
                })

        # 4. Assemble formatted context package
        context_text = cls._format_package_text(objective, query, included)
        actual_tokens, _ = TokenCounter.count_tokens(context_text)

        utilization_pct = round((actual_tokens / max(1, token_budget)) * 100, 1)

        return {
            "query": query,
            "objective": objective,
            "token_budget": token_budget,
            "reconstructed_tokens": actual_tokens,
            "budget_utilization_pct": utilization_pct,
            "is_budget_exceeded": actual_tokens > token_budget,
            "warnings": warnings,
            "selected_memory_ids": selected_ids,
            "included_count": len(included),
            "excluded_count": len(excluded),
            "included_memories": included,
            "excluded_memories": excluded,
            "reconstructed_context_text": context_text,
        }

    @staticmethod
    def _format_package_text(objective: str, query: str, included_items: List[Dict[str, Any]]) -> str:
        """Renders structured context package for downstream agent or inspection."""
        lines = []
        lines.append("=== PALIMPSEST CONTEXT PACKAGE ===")
        if objective:
            lines.append(f"PROJECT OBJECTIVE: {objective}")
        lines.append(f"ACTIVE QUERY: {query}\n")

        instructions = [i for i in included_items if i.get("is_instruction")]
        facts = [i for i in included_items if not i.get("is_instruction")]

        if instructions:
            lines.append("--- CRITICAL INSTRUCTIONS & CONSTRAINTS (PRIORITY PRESERVED) ---")
            for inst in instructions:
                lines.append(f"• [ID: {inst['id'][:8]} | {inst['category']}]: {inst['text_used']}")
            lines.append("")

        if facts:
            lines.append("--- ACTIVE RELEVANT MEMORIES & SUMMARIES ---")
            for f in facts:
                cat_label = f['category']
                lines.append(f"• [ID: {f['id'][:8]} | {cat_label}]: {f['text_used']}")
            lines.append("")

        lines.append("=== END CONTEXT PACKAGE ===")
        return "\n".join(lines)
