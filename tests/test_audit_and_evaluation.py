"""
Unit tests for PALIMPSEST Audit Logging and Evaluation Benchmarks
Covers audit log tracing, evaluation laboratory metrics, CSV export, and drift recovery.
"""

import pytest
from app import create_app
from config import TestConfig
from models import db, Project, MemoryItem, AuditLog, EvaluationRun
from services.audit_service import AuditService
from services.evaluation_service import EvaluationService
from services.drift_demo_service import DriftDemoService


@pytest.fixture
def app_ctx():
    app = create_app(TestConfig)
    with app.app_context():
        yield app


@pytest.fixture
def test_project(app_ctx):
    p = Project(
        name="Audit & Eval Project",
        objective="Benchmarking context memory",
        token_budget=2048,
    )
    db.session.add(p)
    db.session.commit()
    return p


def test_audit_log_completeness(app_ctx, test_project):
    """Test that decision changes produce complete, queryable audit records."""
    item = MemoryItem(
        project_id=test_project.id,
        content="Must use PostgreSQL.",
        category="KEEP VERBATIM",
    )
    db.session.add(item)
    db.session.commit()

    # Log an override
    log = AuditService.log_decision_change(
        project_id=test_project.id,
        memory_item_id=item.id,
        previous_action="KEEP VERBATIM",
        new_action="SUMMARIZE",
        reason="Manual user override: condense database requirement",
        source="manual",
    )

    assert log.id is not None
    assert log.previous_action == "KEEP VERBATIM"
    assert log.new_action == "SUMMARIZE"
    assert "Manual" in log.reason

    # Query audit trail
    trail = AuditService.get_audit_trail(test_project.id, memory_item_id=item.id)
    assert len(trail) >= 1
    assert trail[0]["new_action"] == "SUMMARIZE"


def test_evaluation_metric_calculations_and_csv(app_ctx, test_project):
    """Test evaluation benchmark runs and verifies token reduction and CSV export."""
    run = EvaluationService.run_benchmark(
        project_id=test_project.id,
        name="Automated Test Run",
        token_budget=350,
    )

    assert run.id is not None
    assert run.baseline_tokens > 0
    assert run.palimpsest_tokens > 0
    assert run.token_reduction_pct >= 0.0
    assert run.retention_accuracy > 0.0
    assert len(run.results) == 5

    # Test CSV Export
    csv_text = EvaluationService.export_csv(run.id)
    assert "PALIMPSEST EVALUATION LABORATORY REPORT" in csv_text
    assert "Metric,Baseline (Full History / FIFO),PALIMPSEST,Improvement" in csv_text
    assert run.name in csv_text


def test_drift_recovery_demonstration_scenario(app_ctx, test_project):
    """Test that the 7-phase drift demo correctly verifies constraint recovery."""
    demo_res = DriftDemoService.run_full_drift_demo(test_project.id)

    assert demo_res["verification"]["recovery_verified"] is True
    assert demo_res["verification"]["postgres_recovered"] is True
    assert demo_res["verification"]["jwt_recovered"] is True
    assert demo_res["verification"]["hipaa_recovered"] is True
    assert demo_res["verification"]["mongodb_eradicated"] is True
    assert demo_res["verification"]["drift_directive_eradicated"] is True
    assert demo_res["verification"]["status_badge"] == "RECOVERY VERIFIED"
