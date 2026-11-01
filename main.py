"""
PALIMPSEST CLI Entry Point
Commands: chat, inspect, history, rollback, branch, eval, drift, ui
"""

import click
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

console = Console()


def get_agent(mock: bool = False):
    from config import Config
    from palimpsest.agent import PalimpsestAgent
    cfg = Config()
    if mock:
        cfg.mock_mode = True
    return PalimpsestAgent(cfg)


@click.group()
def cli():
    """📜 PALIMPSEST — Transparent, Versioned Context Memory for AI Agents"""
    pass


@cli.command()
@click.option("--objective", "-o", default="General conversation", help="Session objective")
@click.option("--mock", is_flag=True, help="Run in mock mode (no API key needed)")
def chat(objective, mock):
    """Start an interactive chat session with PALIMPSEST."""
    agent = get_agent(mock)
    vid = agent.start_session(objective=objective)
    console.print(Panel.fit(
        f"[bold cyan]PALIMPSEST Chat[/bold cyan]\n"
        f"Objective: {objective}\nVersion: {vid[:8]}...\n"
        f"Type [bold]exit[/bold] to quit.",
        border_style="cyan"
    ))
    while True:
        try:
            user_input = console.input("[bold green]You:[/bold green] ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if user_input.lower() in ("exit", "quit", "q"):
            break
        if not user_input:
            continue
        response = agent.chat(user_input)
        console.print(f"[bold blue]PALIMPSEST:[/bold blue] {response}\n")

    summary = agent.get_memory_summary()
    console.print(Panel(
        f"Session ended.\nItems stored: {summary['total_items']} "
        f"(Verbatim: {summary['verbatim_count']}, "
        f"Summary: {summary['summary_count']}, "
        f"Discarded: {summary['discard_count']})",
        title="Session Summary", border_style="green"
    ))


@cli.command()
@click.argument("version_id")
@click.option("--mock", is_flag=True)
def inspect(version_id, mock):
    """Inspect memory items for a VERSION_ID."""
    agent = get_agent(mock)
    summary = agent.get_memory_summary(version_id)
    items = agent.store.get_items_by_version(version_id)

    console.print(Panel.fit(
        f"[bold]Version:[/bold] {version_id[:12]}...\n"
        f"Items: {summary['total_items']} | "
        f"Verbatim: {summary['verbatim_count']} | "
        f"Summary: {summary['summary_count']} | "
        f"Discarded: {summary['discard_count']}",
        title="Memory Inspector"
    ))

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Category", width=10)
    table.add_column("Role", width=8)
    table.add_column("Content (truncated)", width=50)
    table.add_column("Importance", width=10)
    table.add_column("Tags", width=15)

    for item in items:
        cat_color = {"verbatim": "green", "summary": "yellow", "discard": "red"}.get(item.category.value, "white")
        table.add_row(
            f"[{cat_color}]{item.category.value}[/{cat_color}]",
            item.role.value,
            item.content[:50] + ("..." if len(item.content) > 50 else ""),
            f"{item.importance_score:.2f}",
            ", ".join(item.topic_tags[:2]),
        )
    console.print(table)


@cli.command()
@click.option("--mock", is_flag=True)
def history(mock):
    """Show the full version history tree."""
    agent = get_agent(mock)
    tree = agent.get_version_history()
    if not tree:
        console.print("[yellow]No versions found. Start a session first.[/yellow]")
        return
    for branch, versions in tree.items():
        console.print(f"\n[bold cyan]Branch: {branch}[/bold cyan]")
        for v in versions:
            merged = " 🔀 MERGED" if v.get("is_merged") else ""
            console.print(
                f"  {'└──' if v.get('parent') else '●──'} [{v['version_id'][:8]}] "
                f"{v['topic_label'] or 'No label'}{merged}  ({v['item_count']} items)"
            )


@cli.command()
@click.argument("version_id")
@click.option("--mock", is_flag=True)
def rollback(version_id, mock):
    """Roll back to an earlier VERSION_ID checkpoint."""
    agent = get_agent(mock)
    new_sid = agent.rollback(version_id)
    console.print(f"[green]✓ Rolled back to version {version_id[:8]}...[/green]")
    console.print(f"New session ID: {new_sid}")


@cli.command()
@click.argument("version_id")
@click.argument("branch_name")
@click.option("--label", default="", help="Topic label for the new branch")
@click.option("--mock", is_flag=True)
def branch(version_id, branch_name, label, mock):
    """Create a BRANCH_NAME from VERSION_ID."""
    agent = get_agent(mock)
    new_sid = agent.branch_session(version_id, branch_name, label or f"Branch: {branch_name}")
    console.print(f"[green]✓ Branch '{branch_name}' created.[/green]")
    console.print(f"New session ID: {new_sid}")


@cli.command()
@click.option("--mock", is_flag=True, default=True, help="Use mock mode (default: True)")
def eval(mock):
    """Run evaluation comparison: PALIMPSEST vs Baseline."""
    from evaluation.evaluator import Evaluator
    from config import Config
    cfg = Config()
    cfg.mock_mode = mock
    console.print("[bold]Running evaluation...[/bold]")
    evaluator = Evaluator(cfg)
    report = evaluator.run_comparison()
    console.print(Panel(
        f"[bold]Evaluation Report[/bold]\n\n"
        f"Tokens  — Baseline: {report.baseline_total_tokens} | PALIMPSEST: {report.palimpsest_total_tokens}\n"
        f"Cost    — Baseline: \${report.baseline_estimated_cost_usd:.6f} | PALIMPSEST: \${report.palimpsest_estimated_cost_usd:.6f}\n"
        f"Latency — Baseline: {report.baseline_avg_latency_ms:.1f}ms | PALIMPSEST: {report.palimpsest_avg_latency_ms:.1f}ms\n"
        f"Recall  — Baseline: {report.baseline_quality_score:.0%} | PALIMPSEST: {report.palimpsest_quality_score:.0%}\n\n"
        f"{report.summary}",
        title="Results", border_style="cyan"
    ))


@cli.command()
def drift():
    """Run the drift recovery demonstration."""
    from evaluation.demo_drift import run_drift_demo
    run_drift_demo()


@cli.command()
def ui():
    """Launch the Streamlit UI."""
    import subprocess
    ui_path = os.path.join(os.path.dirname(__file__), "ui", "app.py")
    console.print(f"[bold cyan]Launching Streamlit UI...[/bold cyan]")
    subprocess.run(["streamlit", "run", ui_path])


if __name__ == "__main__":
    cli()
