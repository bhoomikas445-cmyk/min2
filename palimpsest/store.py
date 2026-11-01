"""
PALIMPSEST SQLite Memory Store
Persists MemoryItems, VersionNodes, and DecisionRecords to a local SQLite database.
"""

import json
import sqlite3
from datetime import datetime
from typing import Optional

from palimpsest.models import DecisionRecord, MemoryItem, VersionNode


class MemoryStore:
    """SQLite-backed persistent store for all PALIMPSEST data."""

    def __init__(self, db_path: str = "palimpsest.db"):
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._create_tables()

    def _create_tables(self):
        cur = self._conn.cursor()
        cur.executescript("""
        CREATE TABLE IF NOT EXISTS memory_items (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            version_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            category TEXT NOT NULL,
            importance_score REAL DEFAULT 0.5,
            relevance_score REAL DEFAULT 0.5,
            recency_score REAL DEFAULT 1.0,
            token_count INTEGER DEFAULT 0,
            topic_tags TEXT DEFAULT '[]',
            decision_rationale TEXT DEFAULT '',
            created_at TEXT NOT NULL,
            embedding TEXT DEFAULT NULL
        );

        CREATE TABLE IF NOT EXISTS versions (
            version_id TEXT PRIMARY KEY,
            parent_version_id TEXT,
            branch_name TEXT NOT NULL DEFAULT 'main',
            topic_label TEXT DEFAULT '',
            session_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            memory_item_ids TEXT DEFAULT '[]',
            is_merged INTEGER DEFAULT 0,
            merge_source_version_id TEXT
        );

        CREATE TABLE IF NOT EXISTS decisions (
            record_id TEXT PRIMARY KEY,
            version_id TEXT NOT NULL,
            memory_item_id TEXT NOT NULL,
            category TEXT NOT NULL,
            rationale TEXT NOT NULL,
            factors TEXT DEFAULT '{}',
            created_at TEXT NOT NULL
        );
        """)
        self._conn.commit()

    # ── MemoryItem ────────────────────────────────────────────────────────────

    def save_memory_item(self, item: MemoryItem):
        cur = self._conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO memory_items VALUES (
                :id, :session_id, :version_id, :role, :content,
                :category, :importance_score, :relevance_score, :recency_score,
                :token_count, :topic_tags, :decision_rationale, :created_at, :embedding
            )
        """, {
            "id": item.id,
            "session_id": item.session_id,
            "version_id": item.version_id,
            "role": item.role.value,
            "content": item.content,
            "category": item.category.value,
            "importance_score": item.importance_score,
            "relevance_score": item.relevance_score,
            "recency_score": item.recency_score,
            "token_count": item.token_count,
            "topic_tags": json.dumps(item.topic_tags),
            "decision_rationale": item.decision_rationale,
            "created_at": item.created_at.isoformat(),
            "embedding": json.dumps(item.embedding) if item.embedding else None,
        })
        self._conn.commit()

    def get_memory_item(self, item_id: str) -> Optional[MemoryItem]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM memory_items WHERE id = ?", (item_id,))
        row = cur.fetchone()
        return self._row_to_item(row) if row else None

    def get_items_by_version(self, version_id: str) -> list[MemoryItem]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM memory_items WHERE version_id = ? ORDER BY created_at ASC",
            (version_id,)
        )
        return [self._row_to_item(r) for r in cur.fetchall()]

    def get_items_by_session(self, session_id: str) -> list[MemoryItem]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM memory_items WHERE session_id = ? ORDER BY created_at ASC",
            (session_id,)
        )
        return [self._row_to_item(r) for r in cur.fetchall()]

    def _row_to_item(self, row) -> MemoryItem:
        d = dict(row)
        d["topic_tags"] = json.loads(d["topic_tags"] or "[]")
        d["embedding"] = json.loads(d["embedding"]) if d["embedding"] else None
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        return MemoryItem(**d)

    # ── VersionNode ───────────────────────────────────────────────────────────

    def save_version(self, version: VersionNode):
        cur = self._conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO versions VALUES (
                :version_id, :parent_version_id, :branch_name, :topic_label,
                :session_id, :created_at, :memory_item_ids, :is_merged,
                :merge_source_version_id
            )
        """, {
            "version_id": version.version_id,
            "parent_version_id": version.parent_version_id,
            "branch_name": version.branch_name,
            "topic_label": version.topic_label,
            "session_id": version.session_id,
            "created_at": version.created_at.isoformat(),
            "memory_item_ids": json.dumps(version.memory_item_ids),
            "is_merged": int(version.is_merged),
            "merge_source_version_id": version.merge_source_version_id,
        })
        self._conn.commit()

    def get_version(self, version_id: str) -> Optional[VersionNode]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM versions WHERE version_id = ?", (version_id,))
        row = cur.fetchone()
        return self._row_to_version(row) if row else None

    def get_all_versions(self) -> list[VersionNode]:
        cur = self._conn.cursor()
        cur.execute("SELECT * FROM versions ORDER BY created_at ASC")
        return [self._row_to_version(r) for r in cur.fetchall()]

    def get_version_chain(self, version_id: str) -> list[VersionNode]:
        chain = []
        current_id = version_id
        while current_id:
            v = self.get_version(current_id)
            if not v:
                break
            chain.insert(0, v)
            current_id = v.parent_version_id
        return chain

    def _row_to_version(self, row) -> VersionNode:
        d = dict(row)
        d["memory_item_ids"] = json.loads(d["memory_item_ids"] or "[]")
        d["is_merged"] = bool(d["is_merged"])
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        return VersionNode(**d)

    # ── DecisionRecord ────────────────────────────────────────────────────────

    def save_decision(self, decision: DecisionRecord):
        cur = self._conn.cursor()
        cur.execute("""
            INSERT OR REPLACE INTO decisions VALUES (
                :record_id, :version_id, :memory_item_id, :category,
                :rationale, :factors, :created_at
            )
        """, {
            "record_id": decision.record_id,
            "version_id": decision.version_id,
            "memory_item_id": decision.memory_item_id,
            "category": decision.category.value,
            "rationale": decision.rationale,
            "factors": json.dumps(decision.factors),
            "created_at": decision.created_at.isoformat(),
        })
        self._conn.commit()

    def get_decisions_for_version(self, version_id: str) -> list[DecisionRecord]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM decisions WHERE version_id = ? ORDER BY created_at ASC",
            (version_id,)
        )
        return [self._row_to_decision(r) for r in cur.fetchall()]

    def get_decisions_for_item(self, memory_item_id: str) -> list[DecisionRecord]:
        cur = self._conn.cursor()
        cur.execute(
            "SELECT * FROM decisions WHERE memory_item_id = ?",
            (memory_item_id,)
        )
        return [self._row_to_decision(r) for r in cur.fetchall()]

    def _row_to_decision(self, row) -> DecisionRecord:
        d = dict(row)
        d["factors"] = json.loads(d["factors"] or "{}")
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        return DecisionRecord(**d)

    def close(self):
        self._conn.close()
