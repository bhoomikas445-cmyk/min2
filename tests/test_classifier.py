"""
PALIMPSEST Test Suite — Classifier Tests
"""

import pytest
from unittest.mock import MagicMock, patch
from config import Config
from palimpsest.classifier import MemoryClassifier
from palimpsest.models import MemoryCategory


@pytest.fixture
def mock_config():
    cfg = Config()
    cfg.mock_mode = True
    return cfg


@pytest.fixture
def classifier(mock_config):
    return MemoryClassifier(config=mock_config, llm_client=None)


def test_verbatim_on_important_content(classifier):
    result = classifier.classify(
        item_content="Always use PostgreSQL. This is mandatory and important.",
        role="user",
        current_objective="Build a REST API",
    )
    assert result.category == MemoryCategory.verbatim
    assert result.importance_score >= 0.7


def test_discard_on_filler(classifier):
    result = classifier.classify(
        item_content="Hello! Thanks, got it.",
        role="user",
        current_objective="Build a REST API",
    )
    assert result.category == MemoryCategory.discard
    assert result.importance_score <= 0.3


def test_summary_on_general_content(classifier):
    result = classifier.classify(
        item_content="We discussed the project timeline and various approaches.",
        role="assistant",
        current_objective="Plan the project",
    )
    assert result.category == MemoryCategory.summary


def test_rationale_is_non_empty(classifier):
    result = classifier.classify(
        item_content="Some content here.",
        role="user",
        current_objective="Test",
    )
    assert isinstance(result.rationale, str)
    assert len(result.rationale) > 0


def test_topic_tags_non_empty(classifier):
    result = classifier.classify(
        item_content="Important instruction here.",
        role="user",
        current_objective="Test",
    )
    assert isinstance(result.topic_tags, list)
    assert len(result.topic_tags) > 0


def test_batch_classify(classifier):
    items = [
        {"content": "Always use JWT. Important!", "role": "user"},
        {"content": "Hi there!", "role": "user"},
        {"content": "Here is some general info about the project.", "role": "assistant"},
    ]
    results = classifier.classify_batch(items, "Build REST API")
    assert len(results) == 3
    assert results[0].category == MemoryCategory.verbatim
    assert results[1].category == MemoryCategory.discard


def test_classify_code_snippet_as_verbatim(classifier):
    result = classifier.classify(
        item_content="```python\ndef main():\n    pass\n```",
        role="assistant",
        current_objective="Write Python code",
    )
    assert result.category == MemoryCategory.verbatim
