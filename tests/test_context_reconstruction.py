"""
Unit tests for PALIMPSEST Context Reconstruction & Token Budgeting
Covers token budgets, constraint prioritization, budget warning, and provenance.
"""

import pytest
from services.context_builder import ContextBuilder


def test_context_reconstruction_prioritizes_constraints():
    """Test that critical constraints are given top priority in reconstructed context."""
    memories = [
        {
            "id": "mem-1",
            "content": "Must use PostgreSQL for database persistence.",
            "category": "KEEP VERBATIM",
            "is_instruction_or_constraint": True,
            "stored_token_count": 15,
            "original_token_count": 15,
            "importance_score": 0.95,
        },
        {
            "id": "mem-2",
            "content": "Team discussed weather in Seattle during morning standup.",
            "category": "DISCARD",
            "is_instruction_or_constraint": False,
            "stored_token_count": 0,
            "original_token_count": 12,
            "importance_score": 0.1,
        },
        {
            "id": "mem-3",
            "content": "API requires async SQLAlchemy with connection pooling.",
            "category": "KEEP VERBATIM",
            "is_instruction_or_constraint": True,
            "stored_token_count": 14,
            "original_token_count": 14,
            "importance_score": 0.90,
        },
    ]

    pkg = ContextBuilder.build_context(
        query="What database should I use?",
        objective="Build REST backend",
        memories=memories,
        token_budget=500,
    )

    assert pkg["reconstructed_tokens"] > 0
    assert pkg["included_count"] >= 2
    assert "mem-1" in pkg["selected_memory_ids"]
    assert "PostgreSQL" in pkg["reconstructed_context_text"]
    # Discarded memory must not be in context text
    assert "Seattle" not in pkg["reconstructed_context_text"]


def test_token_budget_insufficient_warning():
    """Test that an explicit warning is generated if token budget is too small for constraints."""
    memories = [
        {
            "id": "mem-1",
            "content": "Mandatory Requirement: All patient data must strictly adhere to HIPAA regulations with AES-256 bit encryption.",
            "category": "KEEP VERBATIM",
            "is_instruction_or_constraint": True,
            "stored_token_count": 150,
            "original_token_count": 150,
            "importance_score": 0.95,
        },
    ]

    # Constrain budget to 50 tokens (insufficient for 150 tokens)
    pkg = ContextBuilder.build_context(
        query="Compliance check",
        objective="HIPAA Medical API",
        memories=memories,
        token_budget=50,
    )

    assert len(pkg["warnings"]) > 0
    assert "CRITICAL TOKEN BUDGET WARNING" in pkg["warnings"][0]


def test_excluded_memories_explanation():
    """Test that excluded items receive clear audit explanations."""
    memories = [
        {
            "id": "mem-disc",
            "content": "Hey there! Good morning.",
            "category": "DISCARD",
            "is_instruction_or_constraint": False,
            "stored_token_count": 0,
            "original_token_count": 5,
            "importance_score": 0.1,
        }
    ]

    pkg = ContextBuilder.build_context(
        query="Status report",
        objective="General development",
        memories=memories,
        token_budget=200,
    )

    assert pkg["excluded_count"] == 1
    assert "DISCARD" in pkg["excluded_memories"][0]["exclusion_reason"]
