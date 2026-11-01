"""
PALIMPSEST Web UI Route Views
Renders modern Bootstrap 5 templates for all 8 application pages.
"""

from flask import Blueprint, render_template, request, redirect, url_for
from models import Project, MemoryVersion, MemoryBranch, MemoryItem

views_bp = Blueprint("views", __name__)


def get_current_project():
    """Helper to retrieve active project or default to the most recent."""
    project_id = request.args.get("project_id")
    if project_id:
        p = Project.query.get(project_id)
        if p:
            return p
    return Project.query.order_by(Project.created_at.desc()).first()


@views_bp.route("/")
@views_bp.route("/dashboard")
def dashboard():
    """Page A: Modern Analytics Dashboard."""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    current_proj = get_current_project()
    return render_template("dashboard.html", projects=projects, current_project=current_proj)


@views_bp.route("/workspace")
def workspace():
    """Page B & C: Conversation Workspace & Memory Decision Processing."""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    current_proj = get_current_project()
    return render_template("workspace.html", projects=projects, current_project=current_proj)


@views_bp.route("/explorer")
def explorer():
    """Page D: Memory Explorer with search, filters, and manual override."""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    current_proj = get_current_project()
    return render_template("explorer.html", projects=projects, current_project=current_proj)


@views_bp.route("/reconstruct")
def reconstruct():
    """Page E: Context Reconstruction Workbench."""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    current_proj = get_current_project()
    return render_template("reconstruct.html", projects=projects, current_project=current_proj)


@views_bp.route("/version-control")
def version_control():
    """Page F: Git-inspired Version Control System (History, Diff, Branches, Merging)."""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    current_proj = get_current_project()
    return render_template("version_control.html", projects=projects, current_project=current_proj)


@views_bp.route("/audit")
def audit():
    """Page G: Memory Decision Audit Log."""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    current_proj = get_current_project()
    return render_template("audit_log.html", projects=projects, current_project=current_proj)


@views_bp.route("/evaluation")
def evaluation():
    """Page H: Evaluation Laboratory (Baseline vs PALIMPSEST benchmark)."""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    current_proj = get_current_project()
    return render_template("evaluation.html", projects=projects, current_project=current_proj)


@views_bp.route("/drift-demo")
def drift_demo():
    """Page I: Drift Recovery Demonstration."""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    current_proj = get_current_project()
    return render_template("drift_demo.html", projects=projects, current_project=current_proj)
