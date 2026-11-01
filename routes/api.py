"""
PALIMPSEST REST API Blueprint
Clean JSON endpoints for projects, ingestion, classification, context reconstruction,
versioning, branching, merging, auditing, evaluation, and CSV export.
"""

from flask import Blueprint, request, jsonify, Response
from werkzeug.utils import secure_filename
from models import (
    db, Project, Conversation, Message, MemoryItem, MemoryDecision,
    MemoryVersion, MemoryBranch, VersionChange, AuditLog,
    EvaluationRun, EvaluationResult, utc_now, generate_uuid
)
from services import (
    TokenCounter, LLMProvider, CompressionService, MemoryClassifier,
    RetrievalService, ContextBuilder, VersionControlService,
    AuditService, EvaluationService, DriftDemoService
)
from config import Config

api_bp = Blueprint("api", __name__, url_prefix="/api")


# ── 1. Projects ──────────────────────────────────────────────────────────────

@api_bp.route("/projects", methods=["GET"])
def list_projects():
    """List all projects."""
    projects = Project.query.order_by(Project.created_at.desc()).all()
    return jsonify({"success": True, "projects": [p.to_dict() for p in projects]})


@api_bp.route("/projects", methods=["POST"])
def create_project():
    """Create a new project."""
    data = request.get_json() or {}
    name = data.get("name", "").strip()
    if not name:
        return jsonify({"success": False, "error": "Project name is required"}), 400

    project = Project(
        id=generate_uuid(),
        name=name,
        description=data.get("description", "").strip(),
        objective=data.get("objective", "General development and context management").strip(),
        token_budget=int(data.get("token_budget", Config.DEFAULT_TOKEN_BUDGET)),
    )
    db.session.add(project)
    db.session.commit()

    # Automatically initialize default 'main' branch
    branch = VersionControlService.get_or_create_default_branch(project.id)

    return jsonify({"success": True, "project": project.to_dict()}), 201


@api_bp.route("/projects/<project_id>", methods=["GET"])
def get_project(project_id):
    """Retrieve project details, statistics, and branch/version summaries."""
    project = Project.query.get(project_id)
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404

    # Calculate live stats
    items = MemoryItem.query.filter_by(project_id=project_id).all()
    verbatim_count = sum(1 for i in items if i.category == "KEEP VERBATIM")
    summary_count = sum(1 for i in items if i.category == "SUMMARIZE")
    discard_count = sum(1 for i in items if i.category == "DISCARD")
    
    total_orig_tokens = sum(i.original_token_count for i in items)
    current_stored_tokens = sum(i.stored_token_count for i in items if i.category != "DISCARD")
    token_savings = max(0, total_orig_tokens - current_stored_tokens)

    data = project.to_dict()
    data["stats"] = {
        "total_items": len(items),
        "verbatim_count": verbatim_count,
        "summary_count": summary_count,
        "discard_count": discard_count,
        "total_original_tokens": total_orig_tokens,
        "current_memory_tokens": current_stored_tokens,
        "token_savings": token_savings,
        "budget_utilization_pct": round((current_stored_tokens / max(1, project.token_budget)) * 100, 1),
    }
    return jsonify({"success": True, "project": data})


# ── 2. Conversations & Messages ──────────────────────────────────────────────

@api_bp.route("/conversations", methods=["POST"])
def create_conversation():
    """Create a new conversation session inside a project."""
    data = request.get_json() or {}
    project_id = data.get("project_id")
    title = data.get("title", "Session").strip()

    if not project_id:
        return jsonify({"success": False, "error": "project_id is required"}), 400

    project = Project.query.get(project_id)
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404

    conversation = Conversation(
        id=generate_uuid(),
        project_id=project_id,
        title=title,
    )
    db.session.add(conversation)
    db.session.commit()
    return jsonify({"success": True, "conversation": conversation.to_dict()}), 201


@api_bp.route("/conversations/<conversation_id>/messages", methods=["POST"])
def add_message(conversation_id):
    """Add a single message or bulk messages to a conversation."""
    conversation = Conversation.query.get(conversation_id)
    if not conversation:
        return jsonify({"success": False, "error": "Conversation not found"}), 404

    data = request.get_json() or {}
    messages_data = data.get("messages")

    # Support single message or list of messages
    if not messages_data:
        single_content = data.get("content", "").strip()
        role = data.get("role", "user")
        if not single_content:
            return jsonify({"success": False, "error": "Message content is required"}), 400
        messages_data = [{"role": role, "content": single_content}]

    created = []
    for m in messages_data:
        content = m.get("content", "").strip()
        if not content:
            continue
        role = m.get("role", "user")
        token_count, _ = TokenCounter.count_tokens(content)

        msg = Message(
            id=generate_uuid(),
            conversation_id=conversation_id,
            role=role,
            content=content,
            token_count=token_count,
            is_processed=False,
        )
        db.session.add(msg)
        created.append(msg)

    db.session.commit()
    return jsonify({"success": True, "count": len(created), "messages": [m.to_dict() for m in created]}), 201


@api_bp.route("/conversations/<conversation_id>/upload", methods=["POST"])
def upload_document(conversation_id):
    """
    Ingest text or markdown document into conversation.
    Enforces file-size limits and extension validation.
    """
    conversation = Conversation.query.get(conversation_id)
    if not conversation:
        return jsonify({"success": False, "error": "Conversation not found"}), 404

    if "file" not in request.files:
        return jsonify({"success": False, "error": "No file part in request"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "error": "No file selected"}), 400

    filename = secure_filename(file.filename)
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""

    if ext not in Config.ALLOWED_EXTENSIONS:
        return jsonify({
            "success": False,
            "error": f"Invalid file extension '.{ext}'. Allowed: {', '.join(Config.ALLOWED_EXTENSIONS)}"
        }), 400

    try:
        content = file.read().decode("utf-8", errors="replace")
    except Exception as e:
        return jsonify({"success": False, "error": f"Failed to read file: {str(e)}"}), 400

    if len(content.strip()) == 0:
        return jsonify({"success": False, "error": "Uploaded file is empty"}), 400

    # Split document into paragraphs or logical sections if long
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    created_messages = []

    for p in paragraphs:
        tokens, _ = TokenCounter.count_tokens(p)
        msg = Message(
            id=generate_uuid(),
            conversation_id=conversation_id,
            role="tool",  # Document ingestion role
            content=p,
            token_count=tokens,
            is_processed=False,
        )
        db.session.add(msg)
        created_messages.append(msg)

    db.session.commit()
    return jsonify({
        "success": True,
        "filename": filename,
        "paragraphs_ingested": len(created_messages),
        "total_tokens": sum(m.token_count for m in created_messages)
    }), 201


# ── 3. Memory Processing Engine ──────────────────────────────────────────────

@api_bp.route("/memory/process", methods=["POST"])
def process_memory():
    """
    Processes unprocessed messages through the Memory Decision Engine:
    - Evaluates importance, relevance, redundancy, constraint protection
    - Assigns KEEP VERBATIM, SUMMARIZE, or DISCARD with explanations
    - Creates a new version node and records audit logs
    """
    data = request.get_json() or {}
    project_id = data.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id is required"}), 400

    project = Project.query.get(project_id)
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404

    # Optional custom version label
    version_label = data.get("version_label", "").strip() or "Memory Process Run"

    # Fetch unprocessed messages in this project
    unprocessed = (
        Message.query.join(Conversation)
        .filter(Conversation.project_id == project_id, Message.is_processed == False)
        .order_by(Message.created_at.asc())
        .all()
    )

    if not unprocessed:
        return jsonify({"success": True, "message": "No new messages to process.", "processed_count": 0})

    classifier = MemoryClassifier()
    existing_items = [i.to_dict() for i in MemoryItem.query.filter_by(project_id=project_id).all()]

    created_memories = []
    decisions = []
    audit_logs = []

    for msg in unprocessed:
        eval_res = classifier.evaluate_item(
            content=msg.content,
            role=msg.role,
            objective=project.objective,
            existing_items=existing_items,
            source_message_id=msg.id,
        )

        item = MemoryItem(
            id=generate_uuid(),
            project_id=project_id,
            source_message_id=msg.id,
            content=eval_res["content"],
            summary_content=eval_res["summary_content"],
            category=eval_res["category"],
            importance_score=eval_res["importance_score"],
            relevance_score=eval_res["relevance_score"],
            recency_score=eval_res["recency_score"],
            redundancy_score=eval_res["redundancy_score"],
            is_instruction_or_constraint=eval_res["is_instruction_or_constraint"],
            topic_tags=",".join(eval_res["topic_tags"]),
            original_token_count=eval_res["original_token_count"],
            stored_token_count=eval_res["stored_token_count"],
            is_active=True,
        )
        db.session.add(item)
        created_memories.append(item)

        decision = MemoryDecision(
            id=generate_uuid(),
            memory_item_id=item.id,
            action=eval_res["action"],
            explanation=eval_res["explanation"],
            importance_score=eval_res["importance_score"],
            relevance_score=eval_res["relevance_score"],
            original_token_count=eval_res["original_token_count"],
            stored_token_count=eval_res["stored_token_count"],
            processing_method=eval_res["processing_method"],
        )
        db.session.add(decision)
        decisions.append(decision)

        audit = AuditLog(
            id=generate_uuid(),
            project_id=project_id,
            memory_item_id=item.id,
            previous_action=None,
            new_action=eval_res["action"],
            reason=eval_res["explanation"],
            source=eval_res["processing_method"],
        )
        db.session.add(audit)
        audit_logs.append(audit)

        msg.is_processed = True
        existing_items.append(item.to_dict())

    db.session.commit()

    # Create new Version node covering all active memories
    all_active_items = MemoryItem.query.filter_by(project_id=project_id, is_active=True).all()
    version = VersionControlService.create_version(
        project_id=project_id,
        branch_id=project.active_branch_id,
        label=version_label,
        summary=f"Processed {len(unprocessed)} new message(s). Added {len(created_memories)} memories.",
        memory_items=all_active_items,
    )

    # Link version to decisions and audits
    for d in decisions:
        d.version_id = version.id
    for a in audit_logs:
        a.version_id = version.id
    db.session.commit()

    return jsonify({
        "success": True,
        "processed_count": len(created_memories),
        "version": version.to_dict(),
        "decisions": [d.to_dict() for d in decisions],
    }), 200


# ── 4. Memory Explorer & Manual Override ─────────────────────────────────────

@api_bp.route("/memory/items", methods=["GET"])
def list_memory_items():
    """Search and filter memories by project, category, tags, or keyword."""
    project_id = request.args.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id query param is required"}), 400

    query = MemoryItem.query.filter_by(project_id=project_id)

    category = request.args.get("category")
    if category:
        query = query.filter_by(category=category.upper())

    is_instruction = request.args.get("is_instruction")
    if is_instruction is not None:
        query = query.filter_by(is_instruction_or_constraint=is_instruction.lower() == "true")

    search = request.args.get("q", "").strip()
    if search:
        query = query.filter(MemoryItem.content.ilike(f"%{search}%"))

    items = query.order_by(MemoryItem.created_at.desc()).all()
    return jsonify({"success": True, "count": len(items), "items": [i.to_dict() for i in items]})


@api_bp.route("/memory/items/<item_id>", methods=["PUT"])
def update_memory_item(item_id):
    """
    Manual override of a memory decision.
    Audits the override with reason and provenance.
    """
    item = MemoryItem.query.get(item_id)
    if not item:
        return jsonify({"success": False, "error": "Memory item not found"}), 404

    data = request.get_json() or {}
    new_action = data.get("action", "").upper().strip()
    reason = data.get("reason", "").strip() or "Manual user override in Memory Explorer"

    if new_action not in ("KEEP VERBATIM", "SUMMARIZE", "DISCARD"):
        return jsonify({"success": False, "error": "Invalid action. Must be KEEP VERBATIM, SUMMARIZE, or DISCARD."}), 400

    prev_action = item.category
    item.category = new_action

    # Update stored tokens based on new action
    if new_action == "KEEP VERBATIM":
        item.stored_token_count = item.original_token_count
    elif new_action == "DISCARD":
        item.stored_token_count = 0
    elif new_action == "SUMMARIZE" and not item.summary_content:
        comp_service = CompressionService()
        item.summary_content, item.stored_token_count, _ = comp_service.summarize(item.content)

    # Record decision
    decision = MemoryDecision(
        id=generate_uuid(),
        memory_item_id=item.id,
        version_id=item.current_version_id,
        action=new_action,
        explanation=f"[Manual Override]: {reason}",
        importance_score=item.importance_score,
        relevance_score=item.relevance_score,
        original_token_count=item.original_token_count,
        stored_token_count=item.stored_token_count,
        processing_method="manual_override",
    )
    db.session.add(decision)

    # Record audit log
    AuditService.log_decision_change(
        project_id=item.project_id,
        memory_item_id=item.id,
        previous_action=prev_action,
        new_action=new_action,
        reason=reason,
        source="manual",
        version_id=item.current_version_id,
    )

    db.session.commit()
    return jsonify({"success": True, "item": item.to_dict(), "message": "Memory decision updated successfully."})


# ── 5. Context Reconstruction ────────────────────────────────────────────────

@api_bp.route("/context/reconstruct", methods=["POST"])
def reconstruct_context():
    """
    Reconstructs relevant context for a new query within token budget.
    Prioritizes explicit instructions and emits warnings if budget is inadequate.
    """
    data = request.get_json() or {}
    project_id = data.get("project_id")
    query = data.get("query", "").strip()
    token_budget = int(data.get("token_budget", 2048))

    if not project_id:
        return jsonify({"success": False, "error": "project_id is required"}), 400
    if not query:
        return jsonify({"success": False, "error": "Query string is required"}), 400

    project = Project.query.get(project_id)
    if not project:
        return jsonify({"success": False, "error": "Project not found"}), 404

    # Fetch active memory items
    items = MemoryItem.query.filter_by(project_id=project_id, is_active=True).all()
    memories_data = [i.to_dict() for i in items]

    pkg = ContextBuilder.build_context(
        query=query,
        objective=project.objective,
        memories=memories_data,
        token_budget=token_budget,
    )
    return jsonify({"success": True, "package": pkg})


# ── 6. Version Control System ────────────────────────────────────────────────

@api_bp.route("/versions", methods=["GET"])
def list_versions():
    """Chronological history of versions for a project."""
    project_id = request.args.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id query param is required"}), 400

    versions = MemoryVersion.query.filter_by(project_id=project_id).order_by(MemoryVersion.created_at.desc()).all()
    return jsonify({"success": True, "versions": [v.to_dict() for v in versions]})


@api_bp.route("/versions/<version_id>", methods=["GET"])
def get_version(version_id):
    """Retrieve details and changes for a specific version."""
    v = MemoryVersion.query.get(version_id)
    if not v:
        return jsonify({"success": False, "error": "Version not found"}), 404

    changes = VersionChange.query.filter_by(version_id=v.id).all()
    data = v.to_dict()
    data["changes"] = [c.to_dict() for c in changes]
    return jsonify({"success": True, "version": data})


@api_bp.route("/versions/diff", methods=["GET"])
def diff_versions_route():
    """Compare two versions with side-by-side structured diff."""
    v1_id = request.args.get("v1")
    v2_id = request.args.get("v2")
    if not v1_id or not v2_id:
        return jsonify({"success": False, "error": "Query parameters v1 and v2 are required"}), 400

    try:
        diff_res = VersionControlService.diff_versions(v1_id, v2_id)
        return jsonify({"success": True, "diff": diff_res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route("/versions/restore", methods=["POST"])
def restore_version_route():
    """
    Restore context from an earlier historical version.
    Never rewrites history; creates a new version derived from the target state.
    """
    data = request.get_json() or {}
    project_id = data.get("project_id")
    target_version_id = data.get("target_version_id")
    label = data.get("label")

    if not project_id or not target_version_id:
        return jsonify({"success": False, "error": "project_id and target_version_id are required"}), 400

    try:
        new_v = VersionControlService.restore_version(
            project_id=project_id,
            target_version_id=target_version_id,
            label=label,
        )
        return jsonify({"success": True, "restored_version": new_v.to_dict(), "message": "Context restored successfully."})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route("/branches", methods=["GET"])
def list_branches():
    """List all branches for a project."""
    project_id = request.args.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id query param is required"}), 400

    branches = MemoryBranch.query.filter_by(project_id=project_id).order_by(MemoryBranch.created_at.asc()).all()
    return jsonify({"success": True, "branches": [b.to_dict() for b in branches]})


@api_bp.route("/branches", methods=["POST"])
def create_branch():
    """Create a new branch from a version checkpoint."""
    data = request.get_json() or {}
    project_id = data.get("project_id")
    branch_name = data.get("name", "").strip()
    source_version_id = data.get("source_version_id")

    if not project_id or not branch_name:
        return jsonify({"success": False, "error": "project_id and branch name are required"}), 400

    try:
        branch = VersionControlService.create_branch(
            project_id=project_id,
            branch_name=branch_name,
            source_version_id=source_version_id,
        )
        return jsonify({"success": True, "branch": branch.to_dict()}), 201
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


@api_bp.route("/branches/merge", methods=["POST"])
def merge_branches():
    """
    Merge source branch into target branch with conflict detection and resolution.
    """
    data = request.get_json() or {}
    project_id = data.get("project_id")
    source_branch_id = data.get("source_branch_id")
    target_branch_id = data.get("target_branch_id")
    strategy = data.get("strategy", "verbatim_priority")
    resolution_map = data.get("resolution_map", {})

    if not project_id or not source_branch_id or not target_branch_id:
        return jsonify({"success": False, "error": "project_id, source_branch_id, and target_branch_id are required"}), 400

    try:
        merge_res = VersionControlService.merge_branches(
            project_id=project_id,
            source_branch_id=source_branch_id,
            target_branch_id=target_branch_id,
            resolution_map=resolution_map,
            strategy=strategy,
        )
        return jsonify({"success": True, "result": merge_res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


# ── 7. Audit Logs ────────────────────────────────────────────────────────────

@api_bp.route("/audit-logs", methods=["GET"])
def get_audit_logs():
    """Query audit logs for a project with filters."""
    project_id = request.args.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id query param is required"}), 400

    source = request.args.get("source")
    item_id = request.args.get("memory_item_id")
    logs = AuditService.get_audit_trail(project_id, memory_item_id=item_id, source=source)
    return jsonify({"success": True, "count": len(logs), "logs": logs})


# ── 8. Evaluation Laboratory ─────────────────────────────────────────────────

@api_bp.route("/evaluation/run", methods=["POST"])
def run_evaluation():
    """Execute evaluation benchmark comparing Baseline vs PALIMPSEST."""
    data = request.get_json() or {}
    project_id = data.get("project_id")
    name = data.get("name", "Standard Architectural Benchmark")
    token_budget = int(data.get("token_budget", 400))

    if not project_id:
        return jsonify({"success": False, "error": "project_id is required"}), 400

    try:
        eval_run = EvaluationService.run_benchmark(
            project_id=project_id,
            name=name,
            token_budget=token_budget,
        )
        return jsonify({"success": True, "evaluation_run": eval_run.to_dict()})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@api_bp.route("/evaluation/runs", methods=["GET"])
def list_eval_runs():
    """List evaluation benchmark runs."""
    project_id = request.args.get("project_id")
    if not project_id:
        return jsonify({"success": False, "error": "project_id query param is required"}), 400

    runs = EvaluationRun.query.filter_by(project_id=project_id).order_by(EvaluationRun.created_at.desc()).all()
    return jsonify({"success": True, "runs": [r.to_dict() for r in runs]})


@api_bp.route("/evaluation/runs/<run_id>", methods=["GET"])
def get_eval_run(run_id):
    """Retrieve details and per-question results of an evaluation run."""
    run = EvaluationRun.query.get(run_id)
    if not run:
        return jsonify({"success": False, "error": "Evaluation run not found"}), 404

    data = run.to_dict()
    data["results"] = [r.to_dict() for r in run.results]
    return jsonify({"success": True, "run": data})


@api_bp.route("/evaluation/runs/<run_id>/export", methods=["GET"])
def export_eval_run_csv(run_id):
    """Export evaluation report as downloadable CSV."""
    try:
        csv_data = EvaluationService.export_csv(run_id)
        return Response(
            csv_data,
            mimetype="text/csv",
            headers={"Content-Disposition": f"attachment;filename=palimpsest_eval_{run_id[:8]}.csv"}
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 400


# ── 9. Drift Recovery Demonstration ──────────────────────────────────────────

@api_bp.route("/drift-demo/run", methods=["POST"])
def run_drift_demo():
    """Execute reproducible 7-step drift recovery demonstration."""
    data = request.get_json() or {}
    project_id = data.get("project_id")

    try:
        demo_res = DriftDemoService.run_full_drift_demo(project_id)
        return jsonify({"success": True, "demo": demo_res})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
