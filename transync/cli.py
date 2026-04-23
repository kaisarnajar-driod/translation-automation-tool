"""Transync CLI — manage projects and sync Android translations."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.logging import RichHandler
from rich.table import Table

from transync import __version__
from transync.config import AppConfig, load_config
from transync.database import Database
from transync.models.project import Project, SyncStatus
from transync.services.sync_orchestrator import SyncError, SyncOrchestrator

console = Console()


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True, show_path=False)],
    )


def _get_config(ctx: click.Context) -> AppConfig:
    config_path = ctx.obj.get("config_path")
    return load_config(Path(config_path) if config_path else None)


def _get_db(config: AppConfig) -> Database:
    return Database(config.database.resolved_path)


@click.group()
@click.version_option(__version__, prog_name="transync")
@click.option(
    "--config",
    "config_path",
    type=click.Path(exists=False),
    envvar="TRANSYNC_CONFIG",
    help="Path to config.yaml",
)
@click.pass_context
def cli(ctx: click.Context, config_path: str | None) -> None:
    """Transync — Android Translation Automation Tool."""
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path


# ── Project Management ────────────────────────────────────────────


@cli.command()
@click.argument("name")
@click.argument("repo_url")
@click.option("--path", "local_path", required=True, help="Local clone path")
@click.option("--branch", default="main", help="Default branch")
@click.option(
    "--strings-path",
    default="app/src/main/res/values/strings.xml",
    help="Relative path to strings.xml",
)
@click.option(
    "--res-dir",
    default="app/src/main/res",
    help="Relative path to res directory",
)
@click.option("--languages", default="", help="Comma-separated target language codes")
@click.option("--clone/--no-clone", default=True, help="Clone the repo if path doesn't exist")
@click.pass_context
def add(
    ctx: click.Context,
    name: str,
    repo_url: str,
    local_path: str,
    branch: str,
    strings_path: str,
    res_dir: str,
    languages: str,
    clone: bool,
) -> None:
    """Add a project to manage."""
    config = _get_config(ctx)
    _setup_logging(config.logging.level)
    db = _get_db(config)

    if db.get_project(name):
        console.print(f"[red]Error:[/red] Project '{name}' already exists.")
        sys.exit(1)

    local = Path(local_path).expanduser().resolve()

    if clone and not local.exists():
        from transync.services.git_service import GitService
        console.print(f"Cloning [cyan]{repo_url}[/cyan] → [cyan]{local}[/cyan] ...")
        GitService.clone(repo_url, local, branch=branch)

    lang_list = [l.strip() for l in languages.split(",") if l.strip()] if languages else []

    project = Project(
        id=None,
        name=name,
        repo_url=repo_url,
        local_path=str(local),
        branch=branch,
        strings_path=strings_path,
        res_directory=res_dir,
        target_languages=lang_list,
    )
    db.add_project(project)
    console.print(f"[green]✓[/green] Project [bold]{name}[/bold] added successfully.")


@cli.command()
@click.argument("name")
@click.pass_context
def remove(ctx: click.Context, name: str) -> None:
    """Remove a project from management."""
    config = _get_config(ctx)
    _setup_logging(config.logging.level)
    db = _get_db(config)

    if not db.remove_project(name):
        console.print(f"[red]Error:[/red] Project '{name}' not found.")
        sys.exit(1)
    console.print(f"[green]✓[/green] Project [bold]{name}[/bold] removed.")


@cli.command(name="list")
@click.pass_context
def list_projects(ctx: click.Context) -> None:
    """List all managed projects."""
    config = _get_config(ctx)
    _setup_logging(config.logging.level)
    db = _get_db(config)

    projects = db.list_projects()
    if not projects:
        console.print("[yellow]No projects configured.[/yellow] Use `transync add` to add one.")
        return

    table = Table(title="Managed Projects", show_lines=True)
    table.add_column("Name", style="bold cyan")
    table.add_column("Repository")
    table.add_column("Branch")
    table.add_column("Local Path")
    table.add_column("Languages")

    for p in projects:
        langs = ", ".join(p.target_languages) if p.target_languages else "(config default)"
        table.add_row(p.name, p.repo_url, p.branch, p.local_path, langs)

    console.print(table)


# ── Sync ──────────────────────────────────────────────────────────


@cli.command()
@click.argument("name")
@click.option("--dry-run", is_flag=True, default=False, help="Preview changes without committing")
@click.pass_context
def sync(ctx: click.Context, name: str, dry_run: bool) -> None:
    """Sync translations for a project."""
    config = _get_config(ctx)
    _setup_logging(config.logging.level)
    db = _get_db(config)

    project = db.get_project(name)
    if not project:
        console.print(f"[red]Error:[/red] Project '{name}' not found.")
        sys.exit(1)

    if dry_run:
        console.print("[yellow]DRY RUN[/yellow] — no changes will be committed.\n")

    orchestrator = SyncOrchestrator(config, db)

    try:
        with console.status("[bold green]Syncing translations..."):
            record = orchestrator.sync_project(project, dry_run=dry_run)
    except SyncError as exc:
        console.print(f"\n[red]Sync failed:[/red] {exc}")
        sys.exit(1)

    _print_sync_result(record, dry_run)


def _print_sync_result(record, dry_run: bool) -> None:
    status_style = "green" if record.status == SyncStatus.SUCCESS else "red"
    console.print(f"\n[{status_style}]Status: {record.status.value}[/{status_style}]")

    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Label", style="dim")
    table.add_column("Value")

    table.add_row("New keys", str(record.new_keys))
    table.add_row("Modified keys", str(record.modified_keys))
    table.add_row("Removed keys", str(record.removed_keys))
    table.add_row("Languages synced", str(record.languages_synced))
    if record.commit_sha:
        table.add_row("Commit", record.commit_sha[:12])
    if dry_run:
        table.add_row("Mode", "[yellow]dry-run[/yellow]")
    console.print(table)


# ── History ───────────────────────────────────────────────────────


@cli.command()
@click.argument("name")
@click.option("--limit", default=10, help="Number of records to show")
@click.pass_context
def history(ctx: click.Context, name: str, limit: int) -> None:
    """Show sync history for a project."""
    config = _get_config(ctx)
    _setup_logging(config.logging.level)
    db = _get_db(config)

    project = db.get_project(name)
    if not project:
        console.print(f"[red]Error:[/red] Project '{name}' not found.")
        sys.exit(1)

    records = db.get_sync_history(project.id, limit=limit)  # type: ignore[arg-type]
    if not records:
        console.print(f"[yellow]No sync history for '{name}'.[/yellow]")
        return

    table = Table(title=f"Sync History — {name}", show_lines=True)
    table.add_column("#", style="dim")
    table.add_column("Status")
    table.add_column("New")
    table.add_column("Modified")
    table.add_column("Languages")
    table.add_column("Commit")
    table.add_column("Started")

    for r in records:
        status_style = "green" if r.status == SyncStatus.SUCCESS else "red"
        table.add_row(
            str(r.id),
            f"[{status_style}]{r.status.value}[/{status_style}]",
            str(r.new_keys),
            str(r.modified_keys),
            str(r.languages_synced),
            r.commit_sha[:12] if r.commit_sha else "—",
            r.started_at[:19],
        )

    console.print(table)


# ── Config Info ───────────────────────────────────────────────────


@cli.command(name="config")
@click.pass_context
def show_config(ctx: click.Context) -> None:
    """Display current configuration."""
    config = _get_config(ctx)

    table = Table(title="Current Configuration", show_lines=True)
    table.add_column("Setting", style="bold")
    table.add_column("Value")

    table.add_row("Target languages", ", ".join(config.target_languages))
    table.add_row("Translation provider", config.translation.provider)
    table.add_row("Default strings path", config.default_strings_path)
    table.add_row("Res directory", config.res_directory)
    table.add_row("Git branch", config.git.default_branch)
    table.add_row("Dry run", str(config.sync.dry_run))
    table.add_row("Sort keys", str(config.sync.sort_keys))
    table.add_row("DB path", str(config.database.resolved_path))

    console.print(table)


# ── Init (generate config) ───────────────────────────────────────


@cli.command()
@click.option("--force", is_flag=True, help="Overwrite existing config")
def init(force: bool) -> None:
    """Generate a config.yaml from defaults."""
    target = Path("config.yaml")
    source = Path(__file__).parent.parent / "config.default.yaml"

    if target.exists() and not force:
        console.print(
            "[yellow]config.yaml already exists.[/yellow] Use --force to overwrite."
        )
        return

    if source.is_file():
        target.write_text(source.read_text())
    else:
        import yaml
        from transync.config import AppConfig as _AppConfig

        cfg = _AppConfig()
        target.write_text(yaml.dump(cfg.model_dump(), default_flow_style=False, sort_keys=False))

    console.print(f"[green]✓[/green] Config written to [cyan]{target}[/cyan]")


@cli.command()
@click.option("--port", default=8090, help="Port to run the web UI on")
@click.pass_context
def serve(ctx: click.Context, port: int) -> None:
    """Start the web UI server."""
    from transync.web import create_app

    config = _get_config(ctx)
    _setup_logging(config.logging.level)
    app = create_app(config)
    console.print(f"\n  [bold green]Transync Web UI[/bold green] running at [cyan]http://localhost:{port}[/cyan]\n")
    app.run(host="0.0.0.0", port=port, debug=True)


if __name__ == "__main__":
    cli()
