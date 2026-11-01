"""
PALIMPSEST Version Controller
Manages the versioned context chain: create, commit, branch, merge, traceback, restart.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from palimpsest.models import MemoryCategory, MemoryItem, VersionNode
from palimpsest.store import MemoryStore


class VersionController:
    """Manages topic-labelled versions of memory, supporting branching and merging."""

    def __init__(self, store: MemoryStore):
        self.store = store

    def create_version(
        self,
        session_id: str,
        topic_label: str,
        parent_version_id: str | None = None,
        branch_name: str = "main",
    ) -> VersionNode:
        """Create a new version node."""
        version = VersionNode(
            session_id=session_id,
            topic_label=topic_label,
            parent_version_id=parent_version_id,
            branch_name=branch_name,
            created_at=datetime.utcnow(),
        )
        self.store.save_version(version)
        return version

    def commit(self, version_id: str, items: list[MemoryItem]) -> VersionNode:
        """Save items to a version (updates item_ids list)."""
        version = self.store.get_version(version_id)
        if not version:
            raise ValueError(f"Version {version_id} not found.")
        for item in items:
            item.version_id = version_id
            self.store.save_memory_item(item)
            if item.id not in version.memory_item_ids:
                version.memory_item_ids.append(item.id)
        self.store.save_version(version)
        return version

    def traceback(self, version_id: str) -> list[VersionNode]:
        """Return the full ancestor chain from root to the given version."""
        return self.store.get_version_chain(version_id)

    def get_version_tree(self) -> dict:
        """Return a nested dict representing the version tree by branch."""
        all_versions = self.store.get_all_versions()
        tree: dict[str, list] = {}
        for v in all_versions:
            tree.setdefault(v.branch_name, []).append({
                "version_id": v.version_id,
                "topic_label": v.topic_label,
                "parent": v.parent_version_id,
                "created_at": v.created_at.isoformat(),
                "item_count": len(v.memory_item_ids),
                "is_merged": v.is_merged,
            })
        return tree

    def restart_from(self, version_id: str, new_session_id: str) -> VersionNode:
        """
        Create a new 'main' version branching from an older checkpoint.
        Used for drift recovery: roll back and continue from a past state.
        """
        source = self.store.get_version(version_id)
        if not source:
            raise ValueError(f"Version {version_id} not found.")

        # Copy all non-discard items from the source version
        source_items = self.store.get_items_by_version(version_id)
        kept_items = [i for i in source_items if i.category != MemoryCategory.discard]

        new_version = VersionNode(
            session_id=new_session_id,
            topic_label=f"Restart from '{source.topic_label}'",
            parent_version_id=version_id,
            branch_name="main",
            created_at=datetime.utcnow(),
        )
        self.store.save_version(new_version)

        for item in kept_items:
            item.id = str(uuid.uuid4())  # New id for the copy
            item.session_id = new_session_id
            item.version_id = new_version.version_id
            item.decision_rationale += " [Restored from rollback]"
            self.store.save_memory_item(item)
            new_version.memory_item_ids.append(item.id)

        self.store.save_version(new_version)
        return new_version

    def branch(
        self, version_id: str, branch_name: str, topic_label: str
    ) -> VersionNode:
        """Create a new branch from the given version."""
        source = self.store.get_version(version_id)
        if not source:
            raise ValueError(f"Version {version_id} not found.")
        new_version = VersionNode(
            session_id=source.session_id,
            topic_label=topic_label,
            parent_version_id=version_id,
            branch_name=branch_name,
            created_at=datetime.utcnow(),
        )
        self.store.save_version(new_version)
        return new_version

    def merge(
        self,
        source_version_id: str,
        target_version_id: str,
        strategy: str = "union",
    ) -> VersionNode:
        """
        Merge two versions into a new version on the target branch.
        strategy='union'        : all unique items from both versions.
        strategy='intersection' : only items with matching topic tags in both.
        """
        source = self.store.get_version(source_version_id)
        target = self.store.get_version(target_version_id)
        if not source or not target:
            raise ValueError("Source or target version not found.")

        src_items = self.store.get_items_by_version(source_version_id)
        tgt_items = self.store.get_items_by_version(target_version_id)

        if strategy == "union":
            seen_contents = set()
            merged_items = []
            for item in tgt_items + src_items:
                key = item.content[:100]
                if key not in seen_contents:
                    seen_contents.add(key)
                    merged_items.append(item)
        elif strategy == "intersection":
            src_tags = {tag for i in src_items for tag in i.topic_tags}
            merged_items = [i for i in tgt_items if any(t in src_tags for t in i.topic_tags)]
        else:
            merged_items = tgt_items

        merged_version = VersionNode(
            session_id=target.session_id,
            topic_label=f"Merge of '{source.topic_label}' into '{target.topic_label}'",
            parent_version_id=target_version_id,
            branch_name=target.branch_name,
            created_at=datetime.utcnow(),
            is_merged=True,
            merge_source_version_id=source_version_id,
        )
        self.store.save_version(merged_version)

        for item in merged_items:
            item.id = str(uuid.uuid4())
            item.version_id = merged_version.version_id
            self.store.save_memory_item(item)
            merged_version.memory_item_ids.append(item.id)

        self.store.save_version(merged_version)
        return merged_version

    def list_branches(self) -> list[str]:
        """Return all unique branch names."""
        return list({v.branch_name for v in self.store.get_all_versions()})

    def get_branch_tip(self, branch_name: str) -> VersionNode | None:
        """Return the latest version on a given branch."""
        versions = [v for v in self.store.get_all_versions() if v.branch_name == branch_name]
        if not versions:
            return None
        return max(versions, key=lambda v: v.created_at)
