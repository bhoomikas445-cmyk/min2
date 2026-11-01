"""
PALIMPSEST Test Suite — Version Controller Tests
"""

import os
import pytest

from palimpsest.store import MemoryStore
from palimpsest.version_control import VersionController
from palimpsest.models import MemoryCategory, MemoryItem, MessageRole


TEST_DB = "test_vc_palimpsest.db"


@pytest.fixture
def vc():
    store = MemoryStore(db_path=TEST_DB)
    vc = VersionController(store)
    yield vc
    store.close()
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


def make_item(version_id: str, content: str = "test", tags: list = None) -> MemoryItem:
    return MemoryItem(
        session_id="s1",
        version_id=version_id,
        role=MessageRole.user,
        content=content,
        category=MemoryCategory.verbatim,
        topic_tags=tags or ["general"],
    )


def test_create_version(vc):
    v = vc.create_version("session1", topic_label="Initial session", branch_name="main")
    assert v.version_id is not None
    assert v.branch_name == "main"
    assert v.topic_label == "Initial session"


def test_commit_items(vc):
    v = vc.create_version("s1", "Test commit")
    item = make_item(v.version_id, "Important instruction")
    updated = vc.commit(v.version_id, [item])
    assert item.id in updated.memory_item_ids


def test_traceback_single(vc):
    v = vc.create_version("s1", "Only version")
    chain = vc.traceback(v.version_id)
    assert len(chain) == 1
    assert chain[0].version_id == v.version_id


def test_traceback_chain(vc):
    v1 = vc.create_version("s1", "Version 1")
    v2 = vc.create_version("s1", "Version 2", parent_version_id=v1.version_id)
    v3 = vc.create_version("s1", "Version 3", parent_version_id=v2.version_id)
    chain = vc.traceback(v3.version_id)
    assert len(chain) == 3
    assert chain[0].version_id == v1.version_id
    assert chain[2].version_id == v3.version_id


def test_branch_creation(vc):
    v = vc.create_version("s1", "Main version", branch_name="main")
    branch_v = vc.branch(v.version_id, "experiment", "Experiment branch")
    assert branch_v.branch_name == "experiment"
    assert branch_v.parent_version_id == v.version_id


def test_list_branches(vc):
    vc.create_version("s1", "Main v", branch_name="main")
    vc.create_version("s1", "Feature v", branch_name="feature-a")
    branches = vc.list_branches()
    assert "main" in branches
    assert "feature-a" in branches


def test_merge_union(vc):
    v1 = vc.create_version("s1", "Source", branch_name="feature")
    v2 = vc.create_version("s1", "Target", branch_name="main")

    item1 = make_item(v1.version_id, "Content from feature branch", ["api"])
    item2 = make_item(v2.version_id, "Content from main branch", ["db"])
    vc.commit(v1.version_id, [item1])
    vc.commit(v2.version_id, [item2])

    merged = vc.merge(v1.version_id, v2.version_id, strategy="union")
    assert merged.is_merged is True
    assert merged.merge_source_version_id == v1.version_id
    assert len(merged.memory_item_ids) == 2


def test_restart_from_version(vc):
    v1 = vc.create_version("s1", "Checkpoint")
    item = make_item(v1.version_id, "Use PostgreSQL always")
    vc.commit(v1.version_id, [item])

    new_version = vc.restart_from(v1.version_id, "new-session-id")
    assert new_version.parent_version_id == v1.version_id
    assert "Restart" in new_version.topic_label
    assert len(new_version.memory_item_ids) > 0


def test_get_branch_tip(vc):
    v1 = vc.create_version("s1", "V1", branch_name="main")
    v2 = vc.create_version("s1", "V2", parent_version_id=v1.version_id, branch_name="main")
    tip = vc.get_branch_tip("main")
    assert tip is not None
    assert tip.version_id == v2.version_id
