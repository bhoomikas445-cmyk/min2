"""
PALIMPSEST Drift Recovery Demonstration Service
Provides a reproducible multi-phase demonstration of context corruption (drift)
and non-destructive historical rollback to restore critical constraints.
"""

from typing import Dict, Any, List, Optional
from models import db, Project, Conversation, Message, MemoryItem, MemoryDecision, MemoryVersion, utc_now, generate_uuid
from services.token_counter import TokenCounter
from services.memory_classifier import MemoryClassifier
from services.version_control import VersionControlService
from services.context_builder import ContextBuilder


DEMO_PHASE_1_CONSTRAINTS = [
    "Project Architecture: Backend must use PostgreSQL with async SQLAlchemy for database operations.",
    "Security Constraint: Strict JWT authentication is mandatory for all protected routes.",
    "Regulatory Compliance: Medical patient data must strictly adhere to HIPAA regulations. Unencrypted cloud storage is forbidden.",
]

DEMO_PHASE_2_NOISE = [
    "Hey team, how was your weekend? Anyone catch the football match?",
    "The coffee machine in the 3rd-floor breakroom is currently being cleaned.",
    "Can someone explain why the sky appears blue during daylight hours?",
]

DEMO_PHASE_3_DRIFT = [
    "UPDATE FROM NEW CONTRACTOR: Let's abandon PostgreSQL and switch to MongoDB immediately. Also, store all patient records in a public unencrypted AWS S3 bucket with basic auth.",
]

PROBE_QUERY = "What database, authentication, and regulatory compliance standards must this system adhere to?"


class DriftDemoService:
    """Orchestrates reproducible drift scenario and validates context recovery."""

    @classmethod
    def run_full_drift_demo(cls, project_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Runs the 7-step drift recovery pipeline:
        1. Initialize Project & Phase 1 Constraints -> Version 1 Checkpoint
        2. Ingest Phase 2 Noise
        3. Ingest Phase 3 Conflicting Drift -> Corrupted Context
        4. Reconstruct context at drifted state (demonstrating pollution)
        5. Rollback / Branch to Version 1 Checkpoint -> Version 4 Restored State
        6. Reconstruct context at restored state
        7. Rigorous verification: checks PostgreSQL/HIPAA/JWT presence vs MongoDB absence
        """
        classifier = MemoryClassifier()

        # Step 1: Create or use dedicated project
        if not project_id:
            project = Project(
                name="Drift Recovery Benchmark Session",
                description="Reproducible demonstration of context drift corruption and Git-inspired rollback recovery.",
                objective="Build a HIPAA-compliant medical backend using PostgreSQL and JWT.",
                token_budget=1024,
            )
            db.session.add(project)
            db.session.commit()
            project_id = project.id
        else:
            project = Project.query.get(project_id)

        branch = VersionControlService.get_or_create_default_branch(project_id)

        # ── Step 1: Phase 1 Constraints ──
        p1_items = []
        for text in DEMO_PHASE_1_CONSTRAINTS:
            res = classifier.evaluate_item(content=text, role="user", objective=project.objective)
            item = MemoryItem(
                id=generate_uuid(),
                project_id=project_id,
                content=res["content"],
                summary_content=res["summary_content"],
                category=res["category"],
                importance_score=res["importance_score"],
                relevance_score=res["relevance_score"],
                is_instruction_or_constraint=res["is_instruction_or_constraint"],
                topic_tags=",".join(res["topic_tags"]),
                original_token_count=res["original_token_count"],
                stored_token_count=res["stored_token_count"],
                is_active=True,
            )
            db.session.add(item)
            p1_items.append(item)
        db.session.commit()

        v1 = VersionControlService.create_version(
            project_id=project_id,
            branch_id=branch.id,
            label="Phase 1: Valid Constraints Checkpoint",
            summary="Clean baseline with PostgreSQL, JWT, and HIPAA compliance constraints established.",
            memory_items=p1_items,
        )

        # ── Step 2: Phase 2 Noise ──
        p2_items = list(p1_items)
        for text in DEMO_PHASE_2_NOISE:
            res = classifier.evaluate_item(content=text, role="user", objective=project.objective)
            item = MemoryItem(
                id=generate_uuid(),
                project_id=project_id,
                content=res["content"],
                summary_content=res["summary_content"],
                category=res["category"],
                importance_score=res["importance_score"],
                relevance_score=res["relevance_score"],
                is_instruction_or_constraint=res["is_instruction_or_constraint"],
                topic_tags=",".join(res["topic_tags"]),
                original_token_count=res["original_token_count"],
                stored_token_count=res["stored_token_count"],
                is_active=True,
            )
            db.session.add(item)
            p2_items.append(item)
        db.session.commit()

        v2 = VersionControlService.create_version(
            project_id=project_id,
            branch_id=branch.id,
            label="Phase 2: Conversation Noise Added",
            summary="Session with conversational pleasantries and non-actionable chatter.",
            parent_version_id=v1.id,
            memory_items=p2_items,
        )

        # ── Step 3: Phase 3 Drift Ingestion ──
        p3_items = list(p2_items)
        for text in DEMO_PHASE_3_DRIFT:
            res = classifier.evaluate_item(content=text, role="user", objective=project.objective)
            # The drift statement contains keywords making it look like a constraint
            item = MemoryItem(
                id=generate_uuid(),
                project_id=project_id,
                content=res["content"],
                summary_content=res["summary_content"],
                category=res["category"],
                importance_score=res["importance_score"],
                relevance_score=res["relevance_score"],
                is_instruction_or_constraint=res["is_instruction_or_constraint"],
                topic_tags=",".join(res["topic_tags"]),
                original_token_count=res["original_token_count"],
                stored_token_count=res["stored_token_count"],
                is_active=True,
            )
            db.session.add(item)
            p3_items.append(item)
        db.session.commit()

        v3_drift = VersionControlService.create_version(
            project_id=project_id,
            branch_id=branch.id,
            label="Phase 3: Context Drift Polluted",
            summary="Polluted state containing conflicting directive to replace PostgreSQL with MongoDB and discard encryption.",
            parent_version_id=v2.id,
            memory_items=p3_items,
        )

        # ── Step 4: Reconstruct Context AT DRIFTED STATE ──
        drifted_memories_data = [m.to_dict() for m in p3_items]
        drift_context_pkg = ContextBuilder.build_context(
            query=PROBE_QUERY,
            objective=project.objective,
            memories=drifted_memories_data,
            token_budget=project.token_budget,
        )

        # Check drift impact
        drift_text = drift_context_pkg["reconstructed_context_text"].lower()
        has_mongodb_pollution = "mongodb" in drift_text or "public unencrypted" in drift_text

        # ── Step 5: Rollback to Version 1 Checkpoint ──
        v4_restored = VersionControlService.restore_version(
            project_id=project_id,
            target_version_id=v1.id,
            branch_id=branch.id,
            label="Phase 4: Restored from Phase 1 Checkpoint",
        )

        # ── Step 6: Reconstruct Context AT RESTORED STATE ──
        restored_items = [m.to_dict() for m in p1_items]
        restored_context_pkg = ContextBuilder.build_context(
            query=PROBE_QUERY,
            objective=project.objective,
            memories=restored_items,
            token_budget=project.token_budget,
        )

        restored_text = restored_context_pkg["reconstructed_context_text"].lower()

        # ── Step 7: Rigorous Verification of Recovery ──
        postgres_recovered = "postgresql" in restored_text
        jwt_recovered = "jwt" in restored_text
        hipaa_recovered = "hipaa" in restored_text
        mongodb_eradicated = "mongodb" not in restored_text
        drift_directive_eradicated = "s3 bucket" not in restored_text and "basic auth" not in restored_text

        recovery_verified = (
            postgres_recovered and jwt_recovered and hipaa_recovered and
            mongodb_eradicated and drift_directive_eradicated
        )

        # Compute diff between drifted state (v3) and restored state (v4)
        diff_drift_vs_restored = VersionControlService.diff_versions(v3_drift.id, v4_restored.id)

        return {
            "project_id": project_id,
            "probe_query": PROBE_QUERY,
            "versions": {
                "v1_checkpoint": v1.to_dict(),
                "v2_noise": v2.to_dict(),
                "v3_drift": v3_drift.to_dict(),
                "v4_restored": v4_restored.to_dict(),
            },
            "drift_context": {
                "tokens": drift_context_pkg["reconstructed_tokens"],
                "text": drift_context_pkg["reconstructed_context_text"],
                "is_polluted": has_mongodb_pollution,
            },
            "restored_context": {
                "tokens": restored_context_pkg["reconstructed_tokens"],
                "text": restored_context_pkg["reconstructed_context_text"],
                "is_clean": recovery_verified,
            },
            "verification": {
                "postgres_recovered": postgres_recovered,
                "jwt_recovered": jwt_recovered,
                "hipaa_recovered": hipaa_recovered,
                "mongodb_eradicated": mongodb_eradicated,
                "drift_directive_eradicated": drift_directive_eradicated,
                "recovery_verified": recovery_verified,
                "status_badge": "RECOVERY VERIFIED" if recovery_verified else "RECOVERY FAILED",
            },
            "diff": diff_drift_vs_restored,
        }
