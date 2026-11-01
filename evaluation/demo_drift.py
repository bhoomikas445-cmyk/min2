"""
PALIMPSEST Drift Recovery Demonstration
Shows how memory drift occurs and how PALIMPSEST recovers from it.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from config import Config
from palimpsest.agent import PalimpsestAgent
from evaluation.baseline import BaselineAgent

console = Console()

# Phase 1: Establishing key architectural decisions (10 turns)
PHASE1_CONVERSATION = [
    "I'm building a FastAPI project. Always use PostgreSQL.",
    "Use async SQLAlchemy for all database access. This is mandatory.",
    "JWT tokens for authentication. Remember this throughout.",
    "Use Pydantic v2 for all request/response models.",
    "The project must have 90%+ test coverage. Non-negotiable.",
    "Use Docker for deployment. Always containerize.",
    "API versioning: prefix all endpoints with /api/v1/.",
    "Use CORS middleware to allow all origins in development.",
    "Response format: always wrap in {'status': 'success', 'data': ...}.",
    "Use Redis for caching. Session TTL is 30 minutes.",
]

# Phase 2: Unrelated conversation to cause drift (10 turns)
PHASE2_DRIFT = [
    "What is the history of the Roman Empire?",
    "Explain quantum entanglement.",
    "Tell me about the French Revolution.",
    "What are the rules of chess?",
    "Who wrote Pride and Prejudice?",
    "What is photosynthesis?",
    "Explain the theory of relativity.",
    "What is the capital of Australia?",
    "Tell me about the water cycle.",
    "How does a combustion engine work?",
]

# Probe questions to test memory
PROBE_QUESTIONS = [
    ("What database should I use?", "postgresql"),
    ("What ORM should I use?", "sqlalchemy"),
    ("What authentication method?", "jwt"),
    ("What is the API version prefix?", "/api/v1"),
    ("What cache should I use?", "redis"),
]


def run_drift_demo(config: Config | None = None) -> None:
    cfg = config or Config()
    cfg.mock_mode = True  # Use mock mode for demo without API key

    console.print(Panel.fit(
        "[bold cyan]PALIMPSEST — Memory Drift Recovery Demo[/bold cyan]\n"
        "This demo shows how memory drift occurs in a baseline agent and how\n"
        "PALIMPSEST recovers by rolling back to an earlier context version.",
        border_style="cyan"
    ))

    # ── Setup Agents ──────────────────────────────────────────────────────────
    agent = PalimpsestAgent(cfg)
    baseline = BaselineAgent(cfg)

    objective = "Build a FastAPI REST API project with specific architectural requirements."
    checkpoint_version_id = agent.start_session(objective=objective)
    baseline.start_session(objective=objective)

    # ── Phase 1: Establish Architecture ───────────────────────────────────────
    console.print("\n[bold green]PHASE 1: Establishing architectural decisions (10 turns)[/bold green]")
    for i, msg in enumerate(PHASE1_CONVERSATION, 1):
        agent.chat(msg)
        baseline.chat(msg)
        console.print(f"  Turn {i:02d}: {msg[:70]}")

    # Save checkpoint version for PALIMPSEST
    checkpoint_version_id = agent._active_version_id
    console.print(f"\n  [yellow]✓ PALIMPSEST checkpoint saved: version {checkpoint_version_id[:8]}...[/yellow]")

    # ── Phase 2: Drift Conversation ────────────────────────────────────────────
    console.print("\n[bold red]PHASE 2: Drift conversation — 10 unrelated turns[/bold red]")
    for i, msg in enumerate(PHASE2_DRIFT, 1):
        agent.chat(msg)
        baseline.chat(msg)
        console.print(f"  Turn {i:02d}: {msg[:70]}")

    # ── Probe: Before Recovery ─────────────────────────────────────────────────
    console.print("\n[bold yellow]PROBING MEMORY — Before Recovery[/bold yellow]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Probe Question", style="dim", width=35)
    table.add_column("Expected", width=12)
    table.add_column("Baseline Recalled", width=18)
    table.add_column("PALIMPSEST Recalled", width=20)

    before_p_hits, before_b_hits = 0, 0
    for question, expected in PROBE_QUESTIONS:
        p_ans = agent.chat(question)
        b_ans = baseline.chat(question)
        p_hit = expected.lower() in p_ans.lower()
        b_hit = expected.lower() in b_ans.lower()
        before_p_hits += int(p_hit)
        before_b_hits += int(b_hit)
        table.add_row(
            question,
            expected,
            "[green]✓[/green]" if b_hit else "[red]✗[/red]",
            "[green]✓[/green]" if p_hit else "[red]✗[/red]",
        )
    console.print(table)

    # ── PALIMPSEST Rollback ────────────────────────────────────────────────────
    console.print(f"\n[bold cyan]ROLLING BACK PALIMPSEST to checkpoint version {checkpoint_version_id[:8]}...[/bold cyan]")
    new_session = agent.rollback(checkpoint_version_id)
    console.print(f"  [green]✓ Restored. New session: {new_session[:8]}...[/green]")

    # ── Probe: After Recovery ──────────────────────────────────────────────────
    console.print("\n[bold green]PROBING MEMORY — After PALIMPSEST Rollback[/bold green]")
    table2 = Table(show_header=True, header_style="bold magenta")
    table2.add_column("Probe Question", style="dim", width=35)
    table2.add_column("Expected", width=12)
    table2.add_column("Baseline (no change)", width=20)
    table2.add_column("PALIMPSEST (restored)", width=22)

    after_p_hits, after_b_hits = 0, 0
    for question, expected in PROBE_QUESTIONS:
        p_ans = agent.chat(question)
        b_ans = baseline.chat(question)
        p_hit = expected.lower() in p_ans.lower()
        b_hit = expected.lower() in b_ans.lower()
        after_p_hits += int(p_hit)
        after_b_hits += int(b_hit)
        table2.add_row(
            question,
            expected,
            "[green]✓[/green]" if b_hit else "[red]✗[/red]",
            "[green]✓[/green]" if p_hit else "[red]✗[/red]",
        )
    console.print(table2)

    # ── Summary ────────────────────────────────────────────────────────────────
    console.print(Panel(
        f"[bold]Drift Recovery Summary[/bold]\n\n"
        f"Before rollback  → Baseline: {before_b_hits}/{len(PROBE_QUESTIONS)} | PALIMPSEST: {before_p_hits}/{len(PROBE_QUESTIONS)}\n"
        f"After rollback   → Baseline: {after_b_hits}/{len(PROBE_QUESTIONS)} | PALIMPSEST: {after_p_hits}/{len(PROBE_QUESTIONS)}\n\n"
        f"PALIMPSEST recovered by restoring context from version checkpoint.\n"
        f"Baseline cannot recover — it has no version history.",
        title="Result", border_style="green"
    ))


if __name__ == "__main__":
    run_drift_demo()
