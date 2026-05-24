from __future__ import annotations
import sys
from pathlib import Path
from typing import Optional

import click
from rich.console import Console
from rich.table import Table

from .config import Config, write_example_config
from .models import DocuGenOutput
from .parsers.git import parse_all_commits, parse_commit_range, parse_commit_range_by_branch
from .parsers.session import parse_session_log
from .summarizer.engine import summarize_commits, summarize_session
from .output.markdown import save_markdown
from .output.confluence import ConfluenceClient, push_to_confluence
from .utils import find_repo_root

console = Console()


@click.group()
@click.option("--config", "-c", help="Path to config file", default=None)
@click.pass_context
def cli(ctx: click.Context, config: Optional[str]):
    ctx.ensure_object(dict)
    ctx.obj["config"] = Config.load(config)


@cli.command()
@click.argument("since_ref", default="main")
@click.argument("until_ref", required=False)
@click.option("--repo", "-r", help="Path to git repository")
@click.option("--title", "-t", help="Override document title")
@click.option("--output", "-o", help="Output file (for markdown mode)")
@click.option("--to-confluence", "to_confluence", is_flag=True, help="Push to Confluence")
@click.option("--space-key", help="Confluence space key")
@click.option("--parent-page", "parent_page", help="Confluence parent page ID")
@click.option("--preview", is_flag=True, help="Print markdown to stdout instead of saving")
@click.pass_context
def from_git(
    ctx: click.Context,
    since_ref: str,
    until_ref: Optional[str],
    repo: Optional[str],
    title: Optional[str],
    output: Optional[str],
    to_confluence: bool,
    space_key: Optional[str],
    parent_page: Optional[str],
    preview: bool,
):
    """Generate documentation from git commit history."""
    config: Config = ctx.obj["config"]
    repo_path = repo or find_repo_root()

    if not repo_path:
        console.print("[red]Error: Not in a git repository. Use --repo to specify one.[/red]")
        sys.exit(1)

    with console.status("[bold green]Parsing git history..."):
        if until_ref:
            commits = parse_commit_range(since_ref, until_ref, str(repo_path))
        else:
            commits = parse_commit_range_by_branch(
                since_ref, repo_path=str(repo_path)
            )

    if not commits:
        console.print("[yellow]No commits found in the specified range.[/yellow]")
        sys.exit(0)

    with console.status("[bold green]Summarizing changes..."):
        doc_output = summarize_commits(commits, title, config)

    _handle_output(doc_output, config, output, to_confluence, space_key, parent_page, preview)


@cli.command()
@click.argument("branch", default="main")
@click.option("--repo", "-r", help="Path to git repository")
@click.option("--title", "-t", help="Override document title")
@click.option("--output", "-o", help="Output file (for markdown mode)")
@click.option("--to-confluence", "to_confluence", is_flag=True, help="Push to Confluence")
@click.option("--space-key", help="Confluence space key")
@click.option("--parent-page", "parent_page", help="Confluence parent page ID")
@click.option("--preview", is_flag=True, help="Print markdown to stdout")
@click.pass_context
def from_branch(
    ctx: click.Context,
    branch: str,
    repo: Optional[str],
    title: Optional[str],
    output: Optional[str],
    to_confluence: bool,
    space_key: Optional[str],
    parent_page: Optional[str],
    preview: bool,
):
    """Generate docs comparing current branch to another branch."""
    config: Config = ctx.obj["config"]
    repo_path = repo or find_repo_root()

    if not repo_path:
        console.print("[red]Error: Not in a git repository.[/red]")
        sys.exit(1)

    current_branch = _get_current_branch(repo_path)
    console.print(f"[dim]Comparing {current_branch} → {branch}[/dim]")

    with console.status("[bold green]Parsing git history..."):
        commits = parse_commit_range_by_branch(branch, None, str(repo_path))

    if not commits:
        console.print("[yellow]No new commits on this branch.[/yellow]")
        sys.exit(0)

    with console.status("[bold green]Summarizing changes..."):
        doc_output = summarize_commits(commits, title, config)

    _handle_output(doc_output, config, output, to_confluence, space_key, parent_page, preview)


@cli.command()
@click.argument("log_file")
@click.option("--title", "-t", help="Override document title")
@click.option("--output", "-o", help="Output file (for markdown mode)")
@click.option("--to-confluence", "to_confluence", is_flag=True, help="Push to Confluence")
@click.option("--space-key", help="Confluence space key")
@click.option("--parent-page", "parent_page", help="Confluence parent page ID")
@click.option("--preview", is_flag=True, help="Print markdown to stdout")
@click.pass_context
def from_session(
    ctx: click.Context,
    log_file: str,
    title: Optional[str],
    output: Optional[str],
    to_confluence: bool,
    space_key: Optional[str],
    parent_page: Optional[str],
    preview: bool,
):
    """Generate documentation from an agent session log file.

    Supports OpenCode and Claude Code session logs (JSON format).
    """
    config: Config = ctx.obj["config"]

    with console.status("[bold green]Parsing session log..."):
        session = parse_session_log(log_file)

    if not session:
        console.print(f"[red]Error: Could not parse session log: {log_file}[/red]")
        sys.exit(1)

    with console.status("[bold green]Summarizing session..."):
        doc_output = summarize_session(session, config)

    if title:
        doc_output.title = title

    _print_session_summary(session)

    _handle_output(doc_output, config, output, to_confluence, space_key, parent_page, preview)


@cli.command()
@click.option("--repo", "-r", help="Path to git repository")
@click.option("--title", "-t", help="Override document title")
@click.option("--output", "-o", help="Output file (for markdown mode)")
@click.option("--to-confluence", "to_confluence", is_flag=True, help="Push to Confluence")
@click.option("--space-key", help="Confluence space key")
@click.option("--parent-page", "parent_page", help="Confluence parent page ID")
@click.option("--preview", is_flag=True, help="Print markdown to stdout")
@click.pass_context
def all_commits(
    ctx: click.Context,
    repo: Optional[str],
    title: Optional[str],
    output: Optional[str],
    to_confluence: bool,
    space_key: Optional[str],
    parent_page: Optional[str],
    preview: bool,
):
    """Generate documentation from all recent commits."""
    config: Config = ctx.obj["config"]
    repo_path = repo or find_repo_root()

    if not repo_path:
        console.print("[red]Error: Not in a git repository.[/red]")
        sys.exit(1)

    with console.status("[bold green]Parsing recent commits..."):
        commits = parse_all_commits(str(repo_path), max_count=50)

    if not commits:
        console.print("[yellow]No commits found.[/yellow]")
        sys.exit(0)

    with console.status("[bold green]Summarizing changes..."):
        doc_output = summarize_commits(commits, title, config)

    _handle_output(doc_output, config, output, to_confluence, space_key, parent_page, preview)


@cli.command()
@click.argument("path", default="docu-gen.yaml")
def init(path: str):
    """Create an example configuration file."""
    config_path = Path(path)
    if config_path.exists():
        console.print(f"[yellow]File already exists: {path}[/yellow]")
        return
    write_example_config(config_path)
    console.print(f"[green]Created example config: {path}[/green]")
    console.print("Edit it with your Confluence URL, API token, and space key.")


@cli.command()
@click.option("--api-key", help="API key for LLM provider")
@click.option("--provider", help="LLM provider (openai, anthropic, gemini, ollama)")
@click.option("--model", help="Model name (e.g. gpt-4o, claude-sonnet-4, gemini-2.0-flash)")
@click.pass_context
def test_llm(ctx: click.Context, api_key: Optional[str], provider: Optional[str], model: Optional[str]):
    """Test LLM connection with current config."""
    config: Config = ctx.obj["config"]
    if api_key:
        config.llm.api_key = api_key
    if provider:
        config.llm.provider = provider
    if model:
        config.llm.model = model

    if not config.llm.api_key:
        console.print("[yellow]No API key configured. Set DOCU_GEN_LLM_API_KEY or add to config.[/yellow]")
        return

    from .summarizer.engine import _call_llm
    console.print(f"[dim]Testing {config.llm.provider} ({config.llm.model})...[/dim]")
    try:
        resp = _call_llm('Say "Hello from docu-gen!" in JSON: {"message": "..."}', config)
        console.print(f"[green]LLM connected! Response: {resp[:100]}[/green]")
    except Exception as e:
        console.print(f"[red]LLM connection failed: {e}[/red]")


def _handle_output(
    output: DocuGenOutput,
    config: Config,
    output_path: Optional[str],
    to_confluence: bool,
    space_key: Optional[str],
    parent_page: Optional[str],
    preview: bool,
):
    if preview:
        console.print(output.to_markdown())
        return

    if output_path:
        path = save_markdown(output, output_path)
        console.print(f"[green]Documentation saved to: {path}[/green]")
        return

    if to_confluence or config.default_output == "confluence":
        client = ConfluenceClient(config)
        try:
            url = client.create_or_update_page(output, space_key, parent_page)
            console.print(f"[green]Published to Confluence: {url}[/green]")
            return
        except Exception as e:
            console.print(f"[red]Failed to publish to Confluence: {e}[/red]")

            fallback_path = f"{output.title.lower().replace(' ', '-')}.md"
            path = save_markdown(output, fallback_path)
            console.print(f"[yellow]Saved markdown to {path} instead.[/yellow]")
            return

    path = f"{output.title.lower().replace(' ', '-')}.md"
    save_markdown(output, path)
    console.print(f"[green]Documentation saved to: {path}[/green]")


def _get_current_branch(repo_path: str) -> str:
    import subprocess
    result = subprocess.run(
        ["git", "branch", "--show-current"],
        capture_output=True, text=True, cwd=repo_path,
    )
    return result.stdout.strip() or "HEAD"


def _print_session_summary(session):
    table = Table(title="Session Summary")
    table.add_column("Property", style="cyan")
    table.add_column("Value")
    table.add_row("Tool", session.tool)
    table.add_row("Messages", str(len(session.messages)))
    table.add_row("Tool Calls", str(len(session.tool_calls)))
    table.add_row("Files Touched", str(len(session.files_touched)))
    if session.user_goal:
        table.add_row("Goal", session.user_goal[:80])
    console.print(table)


def entry_point():
    cli(obj={})


if __name__ == "__main__":
    entry_point()
