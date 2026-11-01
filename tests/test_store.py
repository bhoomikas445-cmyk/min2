"""
PALIMPSEST Test Suite — Memory Store Tests
"""

import os
import pytest
from datetime import datetime

from palimpsest.store import MemoryStore
from palimpsest.models import MemoryItem, VersionNode, DecisionRecord, MemoryCategory, MessageRole


TEST_DB = "test_palimpsest.db"


@pytest.fixture
def store():
    s = MemoryStore(db_path=TEST_DB)
    yield s
    s.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def make_item(session_id="s1", version_id="v1") -> MemoryItem:
    return MemoryItem(
        session_id=session_id,
        version_id=version_id,
        role=MessageRole.user,
        content="Test memory content",
        category=MemoryCategory.verbatim,
        importance_score=0.9,
        relevance_score=0.8,
        token_count=10,
        topic_tags=["test"],
        decision_rationale="Test rationale",
    )


def make_version(session_id="s1", parent=None) -> VersionNode:
    return VersionNode(
        session_id=session_id,
        topic_label="Test version",
        parent_version_id=parent,
        branch_name="main",
    )


def test_save_and_retrieve_memory_item(store):
    item = make_item()
    store.save_memory_item(item)
    retrieved = store.get_memory_item(item.id)
    assert retrieved is not None
    assert retrieved.content == "Test memory content"
    assert retrieved.category == MemoryCategory.verbatim


def test_get_items_by_version(store):
    item1 = make_item(version_id="v-abc")
    item2 = make_item(version_id="v-abc")
    item3 = make_item(version_id="v-xyz")
    for i in [item1, item2, item3]:
        store.save_memory_item(i)
    items = store.get_items_by_version("v-abc")
    assert len(items) == 2


def test_save_and_retrieve_version(store):
    v = make_version()
    store.save_version(v)
    retrieved = store.get_version(v.version_id)
    assert retrieved is not None
    assert retrieved.topic_label == "Test version"
    assert retrieved.branch_name == "main"


def test_version_chain(store):
    v1 = make_version()
    store.save_version(v1)
    v2 = make_version(parent=v1.version_id)
    store.save_version(v2)
    v3 = make_version(parent=v2.version_id)
    store.save_version(v3)

    chain = store.get_version_chain(v3.version_id)
    assert len(chain) == 3
    assert chain[0].version_id == v1.version_id
    assert chain[-1].version_id == v3.version_id


def test_save_and_retrieve_decision(store):
    item = make_item()
    store.save_memory_item(item)
    decision = DecisionRecord(
        version_id="v1",
        memory_item_id=item.id,
        category=MemoryCategory.verbatim,
        rationale="High importance item",
        factors={"importance": 0.9, "relevance": 0.8},
    )
    store.save_decision(decision)
    decisions = store.get_decisions_for_version("v1")
    assert len(decisions) == 1
    assert decisions[0].rationale == "High importance item"


def test_get_decisions_for_item(store):
    item = make_item()
    store.save_memory_item(item)
    d = DecisionRecord(
        version_id="v1",
        memory_item_id=item.id,
        category=MemoryCategory.summary,
        rationale="Moderate item",
        factors={},
    )
    store.save_decision(d)
    results = store.get_decisions_for_item(item.id)
    assert len(results) == 1


def test_embedding_stored_and_retrieved(store):
    item = make_item()
    item.embedding = [0.1, 0.2, 0.3]
    store.save_memory_item(item)
    retrieved = store.get_memory_item(item.id)
    assert retrieved.embedding == [0.1, 0.2, 0.3]
