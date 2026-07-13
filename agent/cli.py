"""
Command-line interface for RedBeard Social Agent.

Examples:
  python -m agent.cli generate
  python -m agent.cli generate --count 6 --dry-run
  python -m agent.cli status
  python -m agent.cli export BATCH_ID
  python -m agent.cli dashboard
  python -m agent.cli list-batches
"""

from __future__ import annotations

import json
import sys

import click
from rich.console import Console
from rich.table import Table

from agent import __version__

console = Console()


@click.group()
@click.version_option(__version__, prog_name="redbeard-social-agent")
def cli() -> None:
    """RedBeard Social Agent — semi-automatic content for trade-shop IT."""


@cli.command("generate")
@click.option("--count", "-n", type=int, default=None, help="Posts in this batch")
@click.option("--label", "-l", default="", help="Human label for the batch")
@click.option("--seed", type=int, default=None, help="RNG seed for reproducible mix")
@click.option(
    "--dry-run",
    is_flag=True,
    help="Plan slots only — no LLM API calls",
)
def generate_cmd(count: int | None, label: str, seed: int | None, dry_run: bool) -> None:
    """Generate a new batch of draft posts for human review."""
    from agent.scheduler.jobs import run_generate_job

    try:
        summary = run_generate_job(
            count=count,
            label=label,
            seed=seed,
            dry_run=dry_run,
        )
    except Exception as exc:
        console.print(f"[bold red]Generate failed:[/bold red] {exc}")
        sys.exit(1)

    console.print("[bold green]Batch generated[/bold green]")
    console.print_json(json.dumps(summary))
    console.print(
        "\nReview in the dashboard: [cyan]python -m agent.cli dashboard[/cyan]"
    )


@cli.command("status")
def status_cmd() -> None:
    """Show pending drafts and config safety flags."""
    from agent.scheduler.jobs import run_status_job

    summary = run_status_job()
    console.print_json(json.dumps(summary))


@cli.command("list-batches")
def list_batches_cmd() -> None:
    """List stored batches (newest first)."""
    from agent.config import load_config
    from agent.logging_setup import setup_logging
    from agent.storage import Storage

    cfg = load_config(require_api_key=False)
    setup_logging(cfg)
    storage = Storage(cfg.posts_dir, cfg.exports_dir)
    batches = storage.list_batches()

    table = Table(title="Content Batches")
    table.add_column("ID", style="cyan")
    table.add_column("Label")
    table.add_column("Created")
    table.add_column("Draft")
    table.add_column("Approved")
    table.add_column("Rejected")
    table.add_column("Total")

    for b in batches:
        counts = b.get("counts") or {}
        table.add_row(
            b.get("id", ""),
            b.get("label", ""),
            str(b.get("created_at", ""))[:19],
            str(counts.get("draft", 0)),
            str(counts.get("approved", 0)),
            str(counts.get("rejected", 0)),
            str(counts.get("total", 0)),
        )

    console.print(table)
    if not batches:
        console.print("[yellow]No batches yet. Run: python -m agent.cli generate[/yellow]")


@cli.command("export")
@click.argument("batch_id")
def export_cmd(batch_id: str) -> None:
    """Export approved posts from a batch to data/exports/ (copy-paste pack)."""
    from agent.config import load_config
    from agent.logging_setup import setup_logging
    from agent.publishing.exporter import export_batch_approved

    cfg = load_config(require_api_key=False)
    setup_logging(cfg)
    path = export_batch_approved(cfg, batch_id)
    if path:
        console.print(f"[green]Exported →[/green] {path}")
    else:
        console.print("[red]Nothing exported (missing batch or no approved posts)[/red]")
        sys.exit(1)


@cli.command("dashboard")
@click.option("--host", default=None, help="Override bind host")
@click.option("--port", default=None, type=int, help="Override port")
def dashboard_cmd(host: str | None, port: int | None) -> None:
    """Start the local review dashboard (Flask)."""
    from agent.config import load_config
    from agent.dashboard.app import create_app
    from agent.logging_setup import setup_logging

    cfg = load_config(require_api_key=False)
    setup_logging(cfg)
    app = create_app(cfg)

    bind_host = host or cfg.dashboard.host
    bind_port = port or cfg.dashboard.port
    console.print(
        f"[bold]RedBeard dashboard[/bold] → http://{bind_host}:{bind_port}/"
    )
    if cfg.dashboard.password:
        console.print("[dim]Password protection is enabled (DASHBOARD_PASSWORD)[/dim]")
    console.print(
        "[yellow]v1 safety: no auto-posting. Approve → export → publish manually.[/yellow]"
    )
    # threaded=True helps Pi stay responsive under light multi-tab use
    app.run(host=bind_host, port=bind_port, debug=False, threaded=True)


@cli.command("approve")
@click.argument("batch_id")
@click.argument("post_id")
@click.option("--notes", default="", help="Reviewer notes")
def approve_cmd(batch_id: str, post_id: str, notes: str) -> None:
    """Approve a single post from the CLI."""
    from agent.config import load_config
    from agent.logging_setup import setup_logging
    from agent.models import PostStatus
    from agent.storage import Storage

    cfg = load_config(require_api_key=False)
    setup_logging(cfg)
    storage = Storage(cfg.posts_dir, cfg.exports_dir)
    post = storage.update_post_status(batch_id, post_id, PostStatus.APPROVED, notes=notes)
    if not post:
        console.print("[red]Post not found[/red]")
        sys.exit(1)
    console.print(f"[green]Approved[/green] {post_id}")


@cli.command("reject")
@click.argument("batch_id")
@click.argument("post_id")
@click.option("--notes", default="", help="Reviewer notes")
def reject_cmd(batch_id: str, post_id: str, notes: str) -> None:
    """Reject a single post from the CLI."""
    from agent.config import load_config
    from agent.logging_setup import setup_logging
    from agent.models import PostStatus
    from agent.storage import Storage

    cfg = load_config(require_api_key=False)
    setup_logging(cfg)
    storage = Storage(cfg.posts_dir, cfg.exports_dir)
    post = storage.update_post_status(batch_id, post_id, PostStatus.REJECTED, notes=notes)
    if not post:
        console.print("[red]Post not found[/red]")
        sys.exit(1)
    console.print(f"[yellow]Rejected[/yellow] {post_id}")


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
