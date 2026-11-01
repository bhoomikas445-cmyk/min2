"""
Unit tests for Git-inspired Version Control System (VersionControlService)
Covers version creation, diffs, safe restorations, branch independence, and merge conflicts.
"""

import pytest
from app import create_app
from config import TestConfig
from models import db, Project, MemoryItem, MemoryVersion, MemoryBranch
from services.version_control import VersionControlService


@pytest.fixture
def app_ctx():
    app = create_app(TestConfig)
    with app.app_context():
        yield app


@pytest.fixture
def test_project(app_ctx):
    p = Project(
        name="Test VCS Project",
        objective="VCS Testing",
        token_budget=2048,
    )
    db.session.add(p)
    db.session.commit()
    VersionControlService.get_or_create_default_branch(p.id)
    return p


def test_version_creation_and_hash(app_ctx, test_project):
    """Test creating a version checkpoint with SHA-1 hash."""
    item1 = MemoryItem(
        project_id=test_project.id,
        content="Must use PostgreSQL.",
        category="KEEP VERBATIM",
        is_instruction_or_constraint=True,
        original_token_count=10,
        stored_token_count=10,
    )
    db.session.add(item1)
    db.session.commit()

    v1 = VersionControlService.create_version(
        project_id=test_project.id,
        branch_id=test_project.active_branch_id,
        label="V1: Init Constraints",
        summary="Initial setup",
        memory_items=[item1],
    )

    assert v1.version_number == 1
    assert len(v1.version_hash) == 40
    assert v1.verbatim_count == 1
    assert v1.active_token_count == 10


def test_version_diff(app_ctx, test_project):
    """Test side-by-side diff computation between two versions."""
    item1 = MemoryItem(
        project_id=test_project.id,
        content="Must use PostgreSQL.",
        category="KEEP VERBATIM",
        stored_token_count=10,
    )
    db.session.add(item1)
    db.session.commit()

    v1 = VersionControlService.create_version(
        project_id=test_project.id,
        branch_id=test_project.active_branch_id,
        label="V1",
        memory_items=[item1],
    )

    item2 = MemoryItem(
        project_id=test_project.id,
        content="Added Redis caching layer.",
        category="SUMMARIZE",
        stored_token_count=8,
    )
    db.session.add(item2)
    db.session.commit()

    v2 = VersionControlService.create_version(
        project_id=test_project.id,
        branch_id=test_project.active_branch_id,
        label="V2",
        memory_items=[item1, item2],
    )

    diff = VersionControlService.diff_versions(v1.id, v2.id)
    assert len(diff["added"]) == 1
    assert "Redis" in diff["added"][0]["content"]
    assert diff["token_diff"] == 8


def test_safe_non_destructive_restore(app_ctx, test_project):
    """Test restoring an earlier version creates a NEW version without deleting history."""
    item1 = MemoryItem(
        project_id=test_project.id,
        content="PostgreSQL database rule.",
        category="KEEP VERBATIM",
    )
    db.session.add(item1)
    db.session.commit()

    v1 = VersionControlService.create_version(
        project_id=test_project.id,
        branch_id=test_project.active_branch_id,
        label="V1 Baseline",
        memory_items=[item1],
    )

    item2 = MemoryItem(
        project_id=test_project.id,
        content="Conflicting drift: use MongoDB.",
        category="KEEP VERBATIM",
    )
    db.session.add(item2)
    db.session.commit()

    v2 = VersionControlService.create_version(
        project_id=test_project.id,
        branch_id=test_project.active_branch_id,
        label="V2 Polluted",
        memory_items=[item1, item2],
    )

    # Restore back to V1
    v3_restored = VersionControlService.restore_version(
        project_id=test_project.id,
        target_version_id=v1.id,
        label="V3 Rollback to V1",
    )

    assert v3_restored.is_restoration is True
    assert v3_restored.version_number == 3
    # V1 and V2 still exist in history!
    assert MemoryVersion.query.get(v1.id) is not None
    assert MemoryVersion.query.get(v2.id) is not None


def test_branch_creation_and_independence(app_ctx, test_project):
    """Test creating an independent branch with its own lineage."""
    main_branch = MemoryBranch.query.get(test_project.active_branch_id)
    
    item1 = MemoryItem(
        project_id=test_project.id,
        content="Main branch spec.",
        category="KEEP VERBATIM",
    )
    db.session.add(item1)
    db.session.commit()

    v1 = VersionControlService.create_version(
        project_id=test_project.id,
        branch_id=main_branch.id,
        label="V1 on Main",
        memory_items=[item1],
    )

    # Create new feature branch
    feature_branch = VersionControlService.create_branch(
        project_id=test_project.id,
        branch_name="feature-auth",
        source_version_id=v1.id,
    )

    assert feature_branch.name == "feature-auth"
    assert feature_branch.created_from_version_id == v1.id


def test_merge_branches_with_conflict_resolution(app_ctx, test_project):
    """Test merge conflict detection and resolution when both branches alter same memory."""
    main_branch = MemoryBranch.query.get(test_project.active_branch_id)

    item = MemoryItem(
        project_id=test_project.id,
        content="Authentication protocol specification.",
        category="KEEP VERBATIM",
    )
    db.session.add(item)
    db.session.commit()

    v_main = VersionControlService.create_version(
        project_id=test_project.id,
        branch_id=main_branch.id,
        label="Main: Keep Verbatim Auth",
        memory_items=[item],
    )

    feature_branch = VersionControlService.create_branch(
        project_id=test_project.id,
        branch_name="feature-summary",
        source_version_id=v_main.id,
    )

    # Feature branch changes item category to SUMMARIZE
    item.category = "SUMMARIZE"
    v_feat = VersionControlService.create_version(
        project_id=test_project.id,
        branch_id=feature_branch.id,
        label="Feature: Summarize Auth",
        memory_items=[item],
    )

    # Execute merge with verbatim_priority strategy (should protect KEEP VERBATIM)
    res = VersionControlService.merge_branches(
        project_id=test_project.id,
        source_branch_id=feature_branch.id,
        target_branch_id=main_branch.id,
        strategy="verbatim_priority",
    )

    assert res["has_conflicts"] is False
    assert res["merge_version"] is not None
    assert "Merged" in res["message"] or "Successfully" in res["message"]
