"""
Unit tests for PALIMPSEST Memory Decision Engine (MemoryClassifier)
Covers all three memory classifications (VERBATIM, SUMMARIZE, DISCARD),
explicit instruction/constraint protection, and duplicate detection.
"""

import pytest
from services.memory_classifier import MemoryClassifier


@pytest.fixture
def classifier():
    return MemoryClassifier()


def test_keep_verbatim_explicit_instruction(classifier):
    """Test that explicit instructions are classified as KEEP VERBATIM and protected."""
    text = "We must strictly use PostgreSQL with async SQLAlchemy for database persistence."
    res = classifier.evaluate_item(content=text, role="user", objective="Build a FastAPI service")

    assert res["category"] == "KEEP VERBATIM"
    assert res["is_instruction_or_constraint"] is True
    assert res["importance_score"] >= 0.75
    assert "instruction" in res["topic_tags"]
    assert res["stored_token_count"] == res["original_token_count"]
    assert "PostgreSQL" in res["content"]


def test_keep_verbatim_security_constraint(classifier):
    """Test that security and compliance constraints are preserved verbatim."""
    text = "Strict JWT token authentication is mandatory across all API routes. Plaintext passwords forbidden."
    res = classifier.evaluate_item(content=text, role="user")

    assert res["category"] == "KEEP VERBATIM"
    assert res["is_instruction_or_constraint"] is True
    assert res["importance_score"] >= 0.75


def test_discard_conversational_filler(classifier):
    """Test that conversational fluff and small talk are classified as DISCARD."""
    fillers = [
        "Hello! Good morning, how are you today?",
        "Thanks so much, sounds great!",
        "Okay got it, cool.",
        "Tell me a joke about programming.",
    ]
    for text in fillers:
        res = classifier.evaluate_item(content=text, role="user", objective="Backend REST API")
        assert res["category"] == "DISCARD"
        assert res["stored_token_count"] == 0
        assert res["importance_score"] <= 0.30


def test_summarize_verbose_progress(classifier):
    """Test that verbose informational content is compressed under SUMMARIZE."""
    text = (
        "Yesterday during sprint planning we decided to refactor our user controller. "
        "We configured the Docker containers, set up CORS middleware, and connected the logging service. "
        "The team had an extended discussion regarding file upload endpoints."
    )
    res = classifier.evaluate_item(content=text, role="user", objective="Setup backend services")

    assert res["category"] == "SUMMARIZE"
    assert res["summary_content"] is not None
    assert len(res["summary_content"]) > 0
    assert res["stored_token_count"] <= res["original_token_count"]


def test_duplicate_detection(classifier):
    """Test that redundant duplicate items are detected and scored with high redundancy."""
    existing = [
        {"id": "item-1", "content": "Database persistence must strictly use PostgreSQL."}
    ]
    duplicate_text = "Database persistence must strictly use PostgreSQL."
    res = classifier.evaluate_item(
        content=duplicate_text,
        role="user",
        existing_items=existing,
    )

    assert res["redundancy_score"] >= 0.85
    assert res["category"] == "DISCARD"
    assert "duplicate" in res["explanation"].lower()


def test_instruction_protected_despite_age(classifier):
    """Explicit instructions must never be discarded simply because they are old."""
    text = "Requirement: All endpoints must be prefixed with /api/v1/."
    res = classifier.evaluate_item(content=text, role="user")
    
    assert res["category"] == "KEEP VERBATIM"
    assert res["is_instruction_or_constraint"] is True
