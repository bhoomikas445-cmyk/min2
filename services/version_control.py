"""
PALIMPSEST Version Control System
Git-inspired context memory versioning with branching, merging, conflict detection,
and non-destructive historical restorations.
"""

import hashlib
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional, Tuple
from models import (
    db, Project, MemoryBranch, MemoryVersion, MemoryItem,
    MemoryDecision, VersionChange, AuditLog, utc_now, generate_uuid
)
from services.token_counter import TokenCounter


class VersionControlService:
    """Manages context versions, branches, diffs, and merges with ACID transactions."""

    @classmethod
    def get_or_create_default_branch(cls, project_id: str) -> MemoryBranch:
        """Ensure a default 'main' branch exists for the project."""
        branch = MemoryBranch.query.filter_by(project_id=project_id, name="main").first()
        if not branch:
            branch = MemoryBranch(
                project_id=project_id,
                name="main",
                is_active=True,
            )
            db.session.add(branch)
            db.session.commit()
            
            project = Project.query.get(project_id)
            if project and not project.active_branch_id:
                project.active_branch_id = branch.id
                db.session.commit()
        return branch

    @classmethod
    def create_version(
        cls,
        project_id: str,
        branch_id: Optional[str],
        label: str,
        summary: str = "",
        parent_version_id: Optional[str] = None,
        memory_items: Optional[List[MemoryItem]] = None,
        is_restoration: bool = False,
        is_merge: bool = False,
        merge_source_version_id: Optional[str] = None,
    ) -> MemoryVersion:
        """
        Creates a new immutable version node in the version DAG.
        Enforces cycle prevention and updates branch head.
        """
        project = Project.query.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found.")

        if not branch_id:
            branch = cls.get_or_create_default_branch(project_id)
            branch_id = branch.id
        else:
            branch = MemoryBranch.query.get(branch_id)
            if not branch:
                raise ValueError(f"Branch {branch_id} not found.")

        # Determine parent if not specified
        if parent_version_id is None:
            parent_version_id = branch.current_head_version_id

        # Validate parent reference & cycle check
        if parent_version_id:
            cls._validate_parent_hierarchy(parent_version_id)

        # Compute next version number
        last_version = MemoryVersion.query.filter_by(project_id=project_id).order_by(MemoryVersion.version_number.desc()).first()
        next_version_num = (last_version.version_number + 1) if last_version else 1

        # Items to associate
        if memory_items is None:
            memory_items = MemoryItem.query.filter_by(project_id=project_id, is_active=True).all()

        # Compute metrics
        verbatim_count = sum(1 for m in memory_items if m.category == "KEEP VERBATIM")
        summary_count = sum(1 for m in memory_items if m.category == "SUMMARIZE")
        discard_count = sum(1 for m in memory_items if m.category == "DISCARD")
        active_tokens = sum(
            m.stored_token_count for m in memory_items if m.category in ("KEEP VERBATIM", "SUMMARIZE")
        )

        # Compute version hash (SHA-1)
        hash_input = f"{project_id}:{branch_id}:{parent_version_id}:{next_version_num}:{label}:{utc_now().isoformat()}"
        version_hash = hashlib.sha1(hash_input.encode("utf-8")).hexdigest()

        version = MemoryVersion(
            id=generate_uuid(),
            project_id=project_id,
            branch_id=branch_id,
            version_number=next_version_num,
            version_hash=version_hash,
            label=label,
            summary=summary or f"Version {next_version_num}: {label}",
            parent_version_id=parent_version_id,
            is_restoration=is_restoration,
            is_merge=is_merge,
            merge_source_version_id=merge_source_version_id,
            total_items_count=len(memory_items),
            verbatim_count=verbatim_count,
            summary_count=summary_count,
            discard_count=discard_count,
            active_token_count=active_tokens,
            created_at=utc_now(),
        )

        db.session.add(version)

        # Record changes and update item version references
        for item in memory_items:
            change_type = "RESTORED" if is_restoration else ("MERGED" if is_merge else ("MODIFIED" if item.current_version_id else "ADDED"))
            change = VersionChange(
                version_id=version.id,
                memory_item_id=item.id,
                change_type=change_type,
                old_category=item.category,
                new_category=item.category,
                diff_summary=f"{change_type} in {version.label}",
            )
            db.session.add(change)
            item.current_version_id = version.id

        # Update branch head pointer
        branch.current_head_version_id = version.id
        db.session.commit()
        return version

    @classmethod
    def _validate_parent_hierarchy(cls, parent_id: str, visited: Optional[set] = None):
        """Cycle prevention check: ensures parent does not form a loop."""
        if visited is None:
            visited = set()
        if parent_id in visited:
            raise ValueError(f"Cycle detected in version DAG involving version {parent_id}.")
        visited.add(parent_id)

        parent = MemoryVersion.query.get(parent_id)
        if parent and parent.parent_version_id:
            cls._validate_parent_hierarchy(parent.parent_version_id, visited)

    @classmethod
    def create_branch(cls, project_id: str, branch_name: str, source_version_id: Optional[str] = None) -> MemoryBranch:
        """Create a new branch from a specific version checkpoint."""
        name_clean = branch_name.strip()
        existing = MemoryBranch.query.filter_by(project_id=project_id, name=name_clean).first()
        if existing:
            raise ValueError(f"Branch '{name_clean}' already exists in this project.")

        project = Project.query.get(project_id)
        if not project:
            raise ValueError(f"Project {project_id} not found.")

        if not source_version_id:
            # Fork from current head of active branch or latest version
            if project.active_branch_id:
                active_br = MemoryBranch.query.get(project.active_branch_id)
                source_version_id = active_br.current_head_version_id if active_br else None

        new_branch = MemoryBranch(
            project_id=project_id,
            name=name_clean,
            created_from_version_id=source_version_id,
            current_head_version_id=source_version_id,
            is_active=True,
            created_at=utc_now(),
        )
        db.session.add(new_branch)
        db.session.commit()
        return new_branch

    @classmethod
    def diff_versions(cls, v1_id: str, v2_id: str) -> Dict[str, Any]:
        """
        Computes structured side-by-side diff between two versions.
        Returns added, removed, modified, and unchanged items.
        """
        v1 = MemoryVersion.query.get(v1_id)
        v2 = MemoryVersion.query.get(v2_id)
        if not v1 or not v2:
            raise ValueError("Both version IDs must be valid.")

        v1_changes = VersionChange.query.filter_by(version_id=v1.id).all()
        v2_changes = VersionChange.query.filter_by(version_id=v2.id).all()

        v1_items_map = {c.memory_item_id: c for c in v1_changes}
        v2_items_map = {c.memory_item_id: c for c in v2_changes}

        added = []
        removed = []
        modified = []
        unchanged = []

        all_item_ids = set(v1_items_map.keys()).union(set(v2_items_map.keys()))

        for item_id in all_item_ids:
            item = MemoryItem.query.get(item_id)
            if not item:
                continue

            in_v1 = item_id in v1_items_map
            in_v2 = item_id in v2_items_map

            if in_v2 and not in_v1:
                added.append({
                    "item_id": item_id,
                    "content": item.content,
                    "category": v2_items_map[item_id].new_category,
                    "is_instruction": item.is_instruction_or_constraint,
                    "token_count": item.stored_token_count,
                })
            elif in_v1 and not in_v2:
                removed.append({
                    "item_id": item_id,
                    "content": item.content,
                    "category": v1_items_map[item_id].new_category,
                    "is_instruction": item.is_instruction_or_constraint,
                    "token_count": item.stored_token_count,
                })
            else:
                c1 = v1_items_map[item_id].new_category
                c2 = v2_items_map[item_id].new_category
                if c1 != c2:
                    modified.append({
                        "item_id": item_id,
                        "content": item.content,
                        "v1_category": c1,
                        "v2_category": c2,
                        "is_instruction": item.is_instruction_or_constraint,
                        "diff": f"Action changed from {c1} -> {c2}",
                    })
                else:
                    unchanged.append({
                        "item_id": item_id,
                        "content": item.content[:80] + "...",
                        "category": c1,
                    })

        return {
            "v1": v1.to_dict(),
            "v2": v2.to_dict(),
            "added": added,
            "removed": removed,
            "modified": modified,
            "unchanged": unchanged,
            "token_diff": v2.active_token_count - v1.active_token_count,
            "items_count_diff": v2.total_items_count - v1.total_items_count,
        }

    @classmethod
    def restore_version(
        cls,
        project_id: str,
        target_version_id: str,
        branch_id: Optional[str] = None,
        label: Optional[str] = None,
    ) -> MemoryVersion:
        """
        Restores context to match target_version_id without rewriting history.
        Creates a new version node derived from the target state.
        """
        target = MemoryVersion.query.get(target_version_id)
        if not target:
            raise ValueError(f"Target version {target_version_id} not found.")

        # Find items that were recorded in the target version
        target_changes = VersionChange.query.filter_by(version_id=target.id).all()
        target_item_ids = {c.memory_item_id for c in target_changes}

        # Items created after target checkpoint are deactivated in active context
        all_project_items = MemoryItem.query.filter_by(project_id=project_id).all()
        for item in all_project_items:
            if item.id not in target_item_ids:
                item.is_active = False
                item.category = "DISCARD"
                item.stored_token_count = 0

        # Get items and restore their category
        restored_items = []
        for c in target_changes:
            item = MemoryItem.query.get(c.memory_item_id)
            if item:
                item.category = c.new_category
                item.is_active = True
                if item.category == "KEEP VERBATIM":
                    item.stored_token_count = item.original_token_count
                elif item.category == "DISCARD":
                    item.stored_token_count = 0
                restored_items.append(item)

        restore_label = label or f"Restore from {target.label} (#{target.version_number})"
        summary = f"Restored context state from historical version {target.version_hash[:8]}. Intervening history preserved."

        new_version = cls.create_version(
            project_id=project_id,
            branch_id=branch_id or target.branch_id,
            label=restore_label,
            summary=summary,
            memory_items=restored_items,
            is_restoration=True,
        )

        # Log audit entry
        audit = AuditLog(
            project_id=project_id,
            version_id=new_version.id,
            previous_action="HISTORICAL",
            new_action="RESTORED",
            reason=summary,
            source="restoration",
        )
        db.session.add(audit)
        db.session.commit()
        return new_version

    @classmethod
    def merge_branches(
        cls,
        project_id: str,
        source_branch_id: str,
        target_branch_id: str,
        resolution_map: Optional[Dict[str, str]] = None,
        strategy: str = "verbatim_priority",
    ) -> Dict[str, Any]:
        """
        Merges source branch into target branch with full conflict detection and resolution.
        If conflicts exist and no resolution_map is provided, returns conflict details.
        """
        src_branch = MemoryBranch.query.get(source_branch_id)
        tgt_branch = MemoryBranch.query.get(target_branch_id)
        if not src_branch or not tgt_branch:
            raise ValueError("Invalid source or target branch ID.")

        if not src_branch.current_head_version_id or not tgt_branch.current_head_version_id:
            raise ValueError("Both branches must have at least one committed version before merging.")

        src_head = MemoryVersion.query.get(src_branch.current_head_version_id)
        tgt_head = MemoryVersion.query.get(tgt_branch.current_head_version_id)

        # Retrieve items from both branch heads
        src_changes = {c.memory_item_id: c for c in VersionChange.query.filter_by(version_id=src_head.id).all()}
        tgt_changes = {c.memory_item_id: c for c in VersionChange.query.filter_by(version_id=tgt_head.id).all()}

        conflicts = []
        merged_items = []
        resolution_map = resolution_map or {}

        all_item_ids = set(src_changes.keys()).union(set(tgt_changes.keys()))

        for item_id in all_item_ids:
            item = MemoryItem.query.get(item_id)
            if not item:
                continue

            in_src = item_id in src_changes
            in_tgt = item_id in tgt_changes

            if in_src and in_tgt:
                src_cat = src_changes[item_id].new_category
                tgt_cat = tgt_changes[item_id].new_category

                if src_cat != tgt_cat:
                    # Conflict detected!
                    if item_id in resolution_map:
                        chosen_cat = resolution_map[item_id]
                        item.category = chosen_cat
                        merged_items.append(item)
                    elif strategy == "verbatim_priority":
                        # Auto-resolution strategy: protect KEEP VERBATIM
                        if "KEEP VERBATIM" in (src_cat, tgt_cat):
                            item.category = "KEEP VERBATIM"
                        elif "SUMMARIZE" in (src_cat, tgt_cat):
                            item.category = "SUMMARIZE"
                        else:
                            item.category = "DISCARD"
                        merged_items.append(item)
                    elif strategy == "target_wins":
                        item.category = tgt_cat
                        merged_items.append(item)
                    elif strategy == "source_wins":
                        item.category = src_cat
                        merged_items.append(item)
                    else:
                        conflicts.append({
                            "item_id": item_id,
                            "content": item.content,
                            "is_instruction": item.is_instruction_or_constraint,
                            "source_category": src_cat,
                            "target_category": tgt_cat,
                            "explanation": f"Source branch '{src_branch.name}' has '{src_cat}' while target branch '{tgt_branch.name}' has '{tgt_cat}'.",
                        })
                else:
                    item.category = tgt_cat
                    merged_items.append(item)
            elif in_src:
                item.category = src_changes[item_id].new_category
                merged_items.append(item)
            else:
                item.category = tgt_changes[item_id].new_category
                merged_items.append(item)

        if conflicts:
            return {
                "has_conflicts": True,
                "conflict_count": len(conflicts),
                "conflicts": conflicts,
                "message": f"Merge detected {len(conflicts)} conflicting memory item(s). Please provide resolutions.",
            }

        # Apply merge commit
        merge_label = f"Merge branch '{src_branch.name}' into '{tgt_branch.name}'"
        merge_version = cls.create_version(
            project_id=project_id,
            branch_id=tgt_branch.id,
            label=merge_label,
            summary=f"Clean merge of {src_branch.name} ({src_head.version_hash[:8]}) into {tgt_branch.name} ({tgt_head.version_hash[:8]}).",
            parent_version_id=tgt_head.id,
            memory_items=merged_items,
            is_merge=True,
            merge_source_version_id=src_head.id,
        )

        # Audit log entry
        audit = AuditLog(
            project_id=project_id,
            version_id=merge_version.id,
            previous_action=tgt_head.label,
            new_action="MERGED",
            reason=f"Merged from branch '{src_branch.name}'",
            source="merge",
        )
        db.session.add(audit)
        db.session.commit()

        return {
            "has_conflicts": False,
            "merge_version": merge_version.to_dict(),
            "message": f"Successfully merged '{src_branch.name}' into '{tgt_branch.name}'.",
        }
