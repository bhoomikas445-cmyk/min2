"""
PALIMPSEST Audit Service
Records and queries tamper-evident audit logs of memory decisions,
manual overrides, historical restorations, and branch merges.
"""

from typing import List, Dict, Any, Optional
from models import db, AuditLog, MemoryItem, MemoryDecision, MemoryVersion, utc_now, generate_uuid


class AuditService:
    """Provides methods for logging actions and querying audit records."""

    @staticmethod
    def log_decision_change(
        project_id: str,
        memory_item_id: str,
        previous_action: Optional[str],
        new_action: str,
        reason: str,
        source: str = "manual",  # 'rule_based', 'llm', 'manual', 'restoration', 'merge'
        version_id: Optional[str] = None,
    ) -> AuditLog:
        """Create and persist an audit record."""
        audit = AuditLog(
            id=generate_uuid(),
            project_id=project_id,
            memory_item_id=memory_item_id,
            version_id=version_id,
            previous_action=previous_action or "NONE",
            new_action=new_action,
            reason=reason,
            source=source,
            timestamp=utc_now(),
        )
        db.session.add(audit)
        db.session.commit()
        return audit

    @staticmethod
    def get_audit_trail(
        project_id: str,
        memory_item_id: Optional[str] = None,
        source: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """Query audit log records for a project."""
        query = AuditLog.query.filter_by(project_id=project_id)
        if memory_item_id:
            query = query.filter_by(memory_item_id=memory_item_id)
        if source:
            query = query.filter_by(source=source)

        logs = query.order_by(AuditLog.timestamp.desc()).limit(limit).all()
        result = []
        for log in logs:
            data = log.to_dict()
            if log.memory_item:
                data["content_preview"] = log.memory_item.content[:80] + ("..." if len(log.memory_item.content) > 80 else "")
                data["is_instruction"] = log.memory_item.is_instruction_or_constraint
            else:
                data["content_preview"] = "N/A"
                data["is_instruction"] = False
            result.append(data)
        return result
