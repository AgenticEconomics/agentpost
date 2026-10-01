"""AgentPost CLI - command-line interface for the AgentPost HTTP API."""
from __future__ import annotations

import base64
import json
import mimetypes
import os
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich import print_json

from app import __version__
from app.sdk.client import BoxClient, OperatorClient

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------

app = typer.Typer(
    name="agentpost",
    help="AgentPost CLI - interact with the AgentPost HTTP API.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)

console = Console()
err_console = Console(stderr=True)

# ---------------------------------------------------------------------------
# Configuration helpers
# ---------------------------------------------------------------------------

_DEFAULT_API = "http://localhost:8765"


def _load_config_toml() -> dict:
    """Load optional config from ~/.agentpost/config.toml."""
    cfg_path = Path.home() / ".agentpost" / "config.toml"
    if not cfg_path.exists():
        return {}
    try:
        import toml
        return toml.load(cfg_path)
    except Exception:
        return {}


def _get_config() -> dict:
    """Merge TOML config with environment variables (env wins)."""
    cfg = _load_config_toml()
    api = os.environ.get("AGENTPOST_API", cfg.get("api", _DEFAULT_API))
    token = os.environ.get("AGENTPOST_TOKEN", cfg.get("token", ""))
    root = os.environ.get("AGENTPOST_ROOT", cfg.get("root", ""))
    act_as = os.environ.get("AGENTPOST_ACT_AS", cfg.get("act_as", ""))
    return {
        "api": api or _DEFAULT_API,
        "token": token,
        "root": root,
        "act_as": act_as,
    }


def _require_token(cfg: dict) -> str:
    token = cfg["token"]
    if not token:
        err_console.print("[red]Error:[/red] No token configured. Set AGENTPOST_TOKEN or add token to ~/.agentpost/config.toml")
        raise typer.Exit(code=1)
    return token


def _resolve_box_id(cfg: dict, explicit: Optional[str]) -> str:
    """Return the box_id from the explicit arg or AGENTPOST_ACT_AS."""
    box_id = explicit or cfg.get("act_as", "")
    if not box_id:
        err_console.print("[red]Error:[/red] --box is required (or set AGENTPOST_ACT_AS)")
        raise typer.Exit(code=1)
    return box_id


def _make_operator(cfg: dict) -> OperatorClient:
    token = _require_token(cfg)
    return OperatorClient(api_base=cfg["api"], token=token)


def _make_box_client(cfg: dict, box_id: Optional[str] = None) -> BoxClient:
    token = _require_token(cfg)
    bid = _resolve_box_id(cfg, box_id)
    return BoxClient(api_base=cfg["api"], token=token, box_id=bid)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------

def _output(data, as_json: bool = False):
    """Print data as JSON or via rich console."""
    if as_json:
        print_json(data=data)
    else:
        console.print(data)


def _api_error_exit(exc: Exception):
    """Handle httpx / API errors uniformly."""
    import httpx
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        try:
            detail = exc.response.json().get("detail", exc.response.text)
        except Exception:
            detail = exc.response.text
        err_console.print(f"[red]HTTP {status}:[/red] {detail}")
        raise typer.Exit(code=1)
    elif isinstance(exc, httpx.ConnectError):
        err_console.print(f"[red]Connection error:[/red] Cannot reach {exc.request.url}")
        raise typer.Exit(code=1)
    else:
        err_console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# Global callback for --json
# ---------------------------------------------------------------------------

_json_output = False


@app.callback()
def main_callback(
    json_output: bool = typer.Option(False, "--json", help="Output in JSON format"),
):
    """AgentPost CLI - interact with the AgentPost HTTP API."""
    global _json_output
    _json_output = json_output


# ---------------------------------------------------------------------------
# System commands
# ---------------------------------------------------------------------------

@app.command()
def version():
    """Show AgentPost version."""
    cfg = _get_config()
    try:
        token = cfg["token"] or "anonymous"
        client = BoxClient(api_base=cfg["api"], token=token, box_id=None)
        result = client.version()
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"AgentPost CLI version: [bold]{__version__}[/bold]")
        console.print(f"Server version:      [bold]{result.get('version', '?')}[/bold]")
        console.print(f"Protocol:            {result.get('protocol', '?')}")


@app.command()
def health():
    """Check AgentPost server health."""
    cfg = _get_config()
    try:
        token = cfg["token"] or "anonymous"
        client = BoxClient(api_base=cfg["api"], token=token, box_id=None)
        result = client.health()
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        status = result.get("status", "unknown")
        color = "green" if status == "ok" else "yellow"
        console.print(f"Status:    [{color}]{status}[/{color}]")
        console.print(f"Version:   {result.get('version', '?')}")
        console.print(f"Ready:     {result.get('ready', False)}")
        console.print(f"Boxes:     {result.get('boxes', 0)}")
        console.print(f"Uptime:    {result.get('uptime_sec', 0)}s")
        depths = result.get("queue_depth", {})
        if depths:
            console.print(f"Queue:     {depths}")


@app.command()
def doctor(
    repair: bool = typer.Option(False, "--repair", help="Attempt to repair discovered issues"),
):
    """Run integrity checks on the AgentPost installation."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        result = op.doctor(repair=repair)
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        issues = result.get("issues", [])
        repaired = result.get("repaired", False)
        count = result.get("count", 0)
        if count == 0:
            console.print("[green]✓ No issues found.[/green]")
        else:
            console.print(f"[yellow]Found {count} issue(s)[/yellow] (repair={'yes' if repaired else 'no'}):")
            for issue in issues:
                if isinstance(issue, dict):
                    console.print(f"  • {issue.get('description', issue)}")
                else:
                    console.print(f"  • {issue}")


# ---------------------------------------------------------------------------
# Box lifecycle commands (operator)
# ---------------------------------------------------------------------------

@app.command()
def register(
    id: str = typer.Option(..., "--id", help="Box ID (local part)"),
    name: str = typer.Option(..., "--name", help="Display name"),
    summary: str = typer.Option("", "--summary", help="Box summary / description"),
    cap: Optional[list[str]] = typer.Option(None, "--cap", help="Capability tag (repeatable)"),
):
    """Register a new box."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        result = op.register(
            id=id,
            display_name=name,
            summary=summary,
            capabilities=cap or [],
        )
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[green]✓ Box registered[/green]")
        console.print(f"  ID:      {result.get('id', id)}")
        console.print(f"  Address: {result.get('address', '?')}")
        token = result.get("token", "")
        if token:
            console.print(f"  Token:   {token}")


@app.command(name="list")
def list_boxes():
    """List all registered boxes."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        boxes = op.list_boxes()
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(boxes, as_json=True)
    else:
        if not boxes:
            console.print("[dim]No boxes registered.[/dim]")
            return
        table = Table(title="Boxes")
        table.add_column("ID", style="cyan")
        table.add_column("Name")
        table.add_column("Address")
        table.add_column("Status")
        table.add_column("Unread", justify="right")
        table.add_column("Sent", justify="right")
        table.add_column("Failed", justify="right")
        table.add_column("Summary")
        for b in boxes:
            status = b.get("status", "?")
            color = {"active": "green", "paused": "yellow", "revoked": "red"}.get(status, "white")
            table.add_row(
                b.get("id", ""),
                b.get("display_name", ""),
                b.get("address", ""),
                f"[{color}]{status}[/{color}]",
                str(b.get("unread", 0)),
                str(b.get("sent", 0)),
                str(b.get("failed", 0)),
                b.get("summary", ""),
            )
        console.print(table)


@app.command()
def show(
    box_id: str = typer.Argument(..., help="Box ID"),
):
    """Show detailed information about a box."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        result = op.get_box(box_id)
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[bold]Box: {result.get('id', box_id)}[/bold]")
        console.print(f"  Address:  {result.get('address', '?')}")
        console.print(f"  Name:     {result.get('display_name', '')}")
        console.print(f"  Status:   {result.get('status', '?')}")
        console.print(f"  Summary:  {result.get('summary', '')}")
        caps = result.get("capabilities", [])
        if caps:
            console.print(f"  Caps:     {', '.join(caps)}")
        queue = result.get("queue", {})
        if queue:
            console.print(f"  Queue:")
            for k, v in queue.items():
                console.print(f"    {k}: {v}")
        issues = result.get("issues", [])
        if issues:
            console.print(f"  [yellow]Issues:[/yellow]")
            for iss in issues:
                console.print(f"    • {iss}")


@app.command()
def pause(
    box_id: str = typer.Argument(..., help="Box ID"),
):
    """Pause a box."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        result = op.pause_box(box_id)
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[yellow]⏸ Box '{box_id}' paused.[/yellow]")


@app.command()
def resume(
    box_id: str = typer.Argument(..., help="Box ID"),
):
    """Resume a paused box."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        result = op.resume_box(box_id)
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[green]▶ Box '{box_id}' resumed.[/green]")


@app.command()
def revoke(
    box_id: str = typer.Argument(..., help="Box ID"),
):
    """Revoke a box (irreversible)."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        result = op.revoke_box(box_id)
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[red]⛔ Box '{box_id}' revoked.[/red]")


@app.command(name="token-rotate")
def token_rotate(
    box_id: str = typer.Argument(..., help="Box ID"),
):
    """Rotate the authentication token for a box."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        result = op.rotate_token(box_id)
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[green]✓ Token rotated for box '{box_id}'.[/green]")
        new_token = result.get("token", "")
        if new_token:
            console.print(f"  New token: {new_token}")


# ---------------------------------------------------------------------------
# Mail commands
# ---------------------------------------------------------------------------

@app.command()
def inbox(
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
    folder: str = typer.Option("new", "--folder", help="Folder: new, cur, or seen"),
    unread: bool = typer.Option(False, "--unread", help="Show only unread messages (new folder)"),
):
    """List inbox messages."""
    cfg = _get_config()
    try:
        actual_folder = "new" if unread else folder
        client = _make_box_client(cfg, box)
        messages = client.list_inbox(folder=actual_folder)
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(messages, as_json=True)
    else:
        if not messages:
            console.print("[dim]Inbox is empty.[/dim]")
            return
        table = Table(title=f"Inbox ({actual_folder})")
        table.add_column("Message ID", style="cyan", max_width=30)
        table.add_column("From")
        table.add_column("Subject")
        table.add_column("Type")
        table.add_column("Date")
        for msg in messages:
            table.add_row(
                msg.get("message_id", msg.get("_file", ""))[:30],
                msg.get("from", ""),
                msg.get("subject", ""),
                msg.get("type", ""),
                msg.get("date", ""),
            )
        console.print(table)


@app.command()
def read(
    message_id: str = typer.Argument(..., help="Message ID"),
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """Read a message from the inbox."""
    cfg = _get_config()
    try:
        client = _make_box_client(cfg, box)
        result = client.read_message(message_id)
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[bold]From:[/bold]    {result.get('from', '?')}")
        console.print(f"[bold]To:[/bold]      {', '.join(result.get('to', []))}")
        console.print(f"[bold]Subject:[/bold] {result.get('subject', '')}")
        console.print(f"[bold]Date:[/bold]    {result.get('date', '')}")
        console.print(f"[bold]Type:[/bold]    {result.get('type', '')}")
        console.print(f"[bold]Msg ID:[/bold]  {result.get('message_id', '')}")
        labels = result.get("labels", [])
        if labels:
            console.print(f"[bold]Labels:[/bold]  {', '.join(labels)}")
        console.print()
        body = result.get("body", "")
        if body:
            console.print(body)
        attachments = result.get("attachments", [])
        if attachments:
            console.print()
            console.print("[bold]Attachments:[/bold]")
            for att in attachments:
                console.print(f"  • {att.get('name', '?')} ({att.get('media_type', '?')})")


@app.command()
def ack(
    message_id: str = typer.Argument(..., help="Message ID to acknowledge"),
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """Acknowledge (mark as seen) a message."""
    cfg = _get_config()
    try:
        client = _make_box_client(cfg, box)
        result = client.ack_message(message_id)
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[green]✓ Message '{message_id}' acknowledged.[/green]")


@app.command()
def compose(
    to: Optional[list[str]] = typer.Option(None, "--to", help="Recipient address (repeatable)"),
    subject: str = typer.Option(..., "--subject", help="Message subject"),
    body: Optional[str] = typer.Option(None, "--body", help="Message body text"),
    body_file: Optional[Path] = typer.Option(None, "--body-file", help="Read body from file"),
    type: str = typer.Option("request", "--type", help="Message type"),
    label: Optional[list[str]] = typer.Option(None, "--label", help="Label (repeatable)"),
    attach: Optional[list[Path]] = typer.Option(None, "--attach", help="File to attach (repeatable)"),
    ack_flag: bool = typer.Option(True, "--ack/--no-ack", help="Request delivery acknowledgement"),
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """Compose and send a message.

    Success means the message was accepted by the outbox, not that it was delivered.
    """
    cfg = _get_config()

    # Resolve body text
    body_text = ""
    if body_file:
        if not body_file.exists():
            err_console.print(f"[red]Error:[/red] Body file not found: {body_file}")
            raise typer.Exit(code=1)
        body_text = body_file.read_text(encoding="utf-8")
    elif body:
        body_text = body

    if not to:
        err_console.print("[red]Error:[/red] At least one --to recipient is required")
        raise typer.Exit(code=1)

    # Build attachments
    attachments = []
    if attach:
        for fpath in attach:
            if not fpath.exists():
                err_console.print(f"[red]Error:[/red] Attachment not found: {fpath}")
                raise typer.Exit(code=1)
            content_bytes = fpath.read_bytes()
            content_b64 = base64.b64encode(content_bytes).decode("ascii")
            media_type = mimetypes.guess_type(str(fpath))[0] or "application/octet-stream"
            attachments.append({
                "filename": fpath.name,
                "content_base64": content_b64,
                "media_type": media_type,
            })

    try:
        client = _make_box_client(cfg, box)
        result = client.compose(
            to=to,
            subject=subject,
            body=body_text,
            type=type,
            ack=ack_flag,
            labels=label or [],
            attachments=attachments,
        )
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        status = result.get("status", "?")
        console.print(f"[green]✓ Message {status}[/green]")
        console.print(f"  Message ID: {result.get('message_id', '?')}")
        console.print(f"  From:       {result.get('from', '?')}")
        console.print(f"  Filename:   {result.get('filename', '?')}")


@app.command()
def reply(
    message_id: str = typer.Argument(..., help="Message ID to reply to"),
    body: Optional[str] = typer.Option(None, "--body", help="Reply body text"),
    body_file: Optional[Path] = typer.Option(None, "--body-file", help="Read reply body from file"),
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """Reply to an existing message."""
    cfg = _get_config()

    body_text = ""
    if body_file:
        if not body_file.exists():
            err_console.print(f"[red]Error:[/red] Body file not found: {body_file}")
            raise typer.Exit(code=1)
        body_text = body_file.read_text(encoding="utf-8")
    elif body:
        body_text = body

    try:
        client = _make_box_client(cfg, box)
        # First, read the original message to get its metadata
        original = client.read_message(message_id)
        # Then compose a reply using the SDK's reply method
        result = client.reply(original, body_text)
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        status = result.get("status", "?")
        console.print(f"[green]✓ Reply {status}[/green]")
        console.print(f"  Message ID: {result.get('message_id', '?')}")
        console.print(f"  From:       {result.get('from', '?')}")


@app.command()
def outbox(
    folder: str = typer.Option("sent", "--folder", help="Folder: sent, failed, or new"),
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """List outbox messages."""
    cfg = _get_config()
    try:
        client = _make_box_client(cfg, box)
        messages = client.list_outbox(folder=folder)
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(messages, as_json=True)
    else:
        if not messages:
            console.print(f"[dim]Outbox ({folder}) is empty.[/dim]")
            return
        table = Table(title=f"Outbox ({folder})")
        table.add_column("Message ID", style="cyan", max_width=30)
        table.add_column("To")
        table.add_column("Subject")
        table.add_column("Type")
        table.add_column("Date")
        for msg in messages:
            to_list = msg.get("to", [])
            to_str = ", ".join(to_list) if isinstance(to_list, list) else str(to_list)
            table.add_row(
                msg.get("message_id", msg.get("_file", ""))[:30],
                to_str,
                msg.get("subject", ""),
                msg.get("type", ""),
                msg.get("date", ""),
            )
        console.print(table)


@app.command()
def thread(
    thread_id: str = typer.Argument(..., help="Thread ID"),
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """Show all messages in a thread."""
    cfg = _get_config()
    try:
        client = _make_box_client(cfg, box)
        messages = client.get_thread(thread_id)
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(messages, as_json=True)
    else:
        if not messages:
            console.print("[dim]No messages in thread.[/dim]")
            return
        console.print(f"[bold]Thread: {thread_id}[/bold] ({len(messages)} message(s))")
        console.print()
        for msg in messages:
            direction = msg.get("_folder", "?")
            console.print(f"  [cyan]{msg.get('date', '?')}[/cyan]  [{direction}]")
            console.print(f"  From: {msg.get('from', '?')} → {', '.join(msg.get('to', []))}")
            console.print(f"  Subject: {msg.get('subject', '')}")
            console.print(f"  ID: {msg.get('message_id', '')}")
            console.print()


# ---------------------------------------------------------------------------
# Observe commands
# ---------------------------------------------------------------------------

@app.command()
def tail(
    box: Optional[str] = typer.Option(None, "--box", help="Filter events for a specific box"),
    json_output: bool = typer.Option(False, "--json", help="Output raw JSON events"),
):
    """Tail real-time events via WebSocket (Ctrl+C to stop)."""
    cfg = _get_config()
    token = _require_token(cfg)
    api_base = cfg["api"]

    # Convert HTTP URL to WS URL
    ws_base = api_base.replace("http://", "ws://").replace("https://", "wss://")
    ws_url = f"{ws_base}/api/v1/stream?token={token}"
    if box:
        ws_url += f"&box={box}"

    try:
        import asyncio
        import websockets

        async def _tail_events():
            try:
                async with websockets.connect(ws_url) as ws:
                    console.print(f"[dim]Connected to {api_base} — streaming events (Ctrl+C to stop)...[/dim]")
                    while True:
                        raw = await ws.recv()
                        event = json.loads(raw)
                        if event.get("type") == "keepalive":
                            continue
                        if json_output:
                            print_json(data=event)
                        else:
                            etype = event.get("type", "event")
                            edata = event.get("data", {})
                            console.print(f"[cyan]{etype}[/cyan]  {edata}")
            except KeyboardInterrupt:
                pass
            except Exception as e:
                err_console.print(f"[red]WebSocket error:[/red] {e}")
                raise typer.Exit(code=1)

        asyncio.run(_tail_events())
    except KeyboardInterrupt:
        console.print("\n[dim]Stopped.[/dim]")


@app.command()
def logs(
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """Show recent audit log entries for a box."""
    cfg = _get_config()
    try:
        client = _make_box_client(cfg, box)
        entries = client.get_logs()
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(entries, as_json=True)
    else:
        if not entries:
            console.print("[dim]No log entries.[/dim]")
            return
        table = Table(title="Logs")
        # Detect columns from the first entry
        sample = entries[0] if entries else {}
        columns = list(sample.keys())
        for col in columns:
            table.add_column(col)
        for entry in entries:
            table.add_row(*[str(entry.get(c, "")) for c in columns])
        console.print(table)


@app.command()
def queue():
    """Show queue / spool status (operator)."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        result = op.get_spool()
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        depths = result.get("depths", {})
        if depths:
            console.print("[bold]Queue Depths:[/bold]")
            for k, v in depths.items():
                console.print(f"  {k}: {v}")
        dead = result.get("dead_letter", [])
        if dead:
            console.print(f"\n[bold]Dead Letter ({len(dead)} items):[/bold]")
            table = Table()
            table.add_column("ID", style="cyan")
            table.add_column("From")
            table.add_column("To")
            table.add_column("Subject")
            table.add_column("Error")
            for item in dead:
                table.add_row(
                    str(item.get("id", item.get("item_id", ""))),
                    item.get("from", ""),
                    str(item.get("to", "")),
                    item.get("subject", ""),
                    item.get("error", ""),
                )
            console.print(table)
        else:
            console.print("\n[dim]No dead-letter items.[/dim]")


@app.command()
def retry(
    dead_letter_id: str = typer.Argument(..., help="Dead letter item ID to retry"),
):
    """Retry a dead-letter queue item."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        result = op.retry_dead_letter(dead_letter_id)
        op.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[green]✓ Dead letter '{dead_letter_id}' retried.[/green]")


@app.command()
def addrbook():
    """Show the address book (all known box addresses)."""
    cfg = _get_config()
    try:
        op = _make_operator(cfg)
        entries = op.addrbook()
        op.close()
    except Exception as exc:
        # Fall back to box client if operator fails
        try:
            token = _require_token(cfg)
            client = BoxClient(api_base=cfg["api"], token=token, box_id=cfg.get("act_as", ""))
            entries = client.addrbook()
            client.close()
        except Exception as exc2:
            _api_error_exit(exc2)

    if _json_output:
        _output(entries, as_json=True)
    else:
        if not entries:
            console.print("[dim]Address book is empty.[/dim]")
            return
        table = Table(title="Address Book")
        table.add_column("Address", style="cyan")
        table.add_column("Name")
        table.add_column("Status")
        table.add_column("Summary")
        for entry in entries:
            if isinstance(entry, dict):
                table.add_row(
                    entry.get("address", ""),
                    entry.get("display_name", entry.get("name", "")),
                    entry.get("status", ""),
                    entry.get("summary", ""),
                )
            else:
                table.add_row(str(entry), "", "", "")
        console.print(table)


# ---------------------------------------------------------------------------
# File commands
# ---------------------------------------------------------------------------

@app.command(name="ls")
def ls_files(
    path: str = typer.Argument("", help="Remote directory path"),
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """List files in a box's filesystem."""
    cfg = _get_config()
    try:
        client = _make_box_client(cfg, box)
        files = client.list_files(path)
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(files, as_json=True)
    else:
        if not files:
            console.print("[dim]Directory is empty.[/dim]")
            return
        table = Table(title=f"Files: {path or '/'}")
        table.add_column("Name", style="cyan")
        table.add_column("Type")
        table.add_column("Size", justify="right")
        table.add_column("Path")
        for f in files:
            ftype = f.get("type", "?")
            icon = "📁" if ftype == "dir" else "📄"
            size = f.get("size", "")
            size_str = str(size) if size != "" else "-"
            table.add_row(
                f"{icon} {f.get('name', '')}",
                ftype,
                size_str,
                f.get("path", ""),
            )
        console.print(table)


@app.command(name="cat")
def cat_file(
    path: str = typer.Argument(..., help="Remote file path"),
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """Read and display a file's content from a box."""
    cfg = _get_config()
    try:
        client = _make_box_client(cfg, box)
        content = client.read_file(path)
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    # Try to decode as text; fall back to binary notice
    try:
        text = content.decode("utf-8")
        console.print(text, markup=False)
    except UnicodeDecodeError:
        console.print(f"[dim](binary file, {len(content)} bytes)[/dim]")
        sys.stdout.buffer.write(content)


@app.command()
def put(
    remote_path: str = typer.Argument(..., help="Remote file path to write to"),
    local_path: Path = typer.Argument(..., help="Local file to upload"),
    box: Optional[str] = typer.Option(None, "--box", help="Box ID (or use AGENTPOST_ACT_AS)"),
):
    """Upload a local file to a box's filesystem."""
    cfg = _get_config()
    if not local_path.exists():
        err_console.print(f"[red]Error:[/red] Local file not found: {local_path}")
        raise typer.Exit(code=1)

    try:
        client = _make_box_client(cfg, box)
        content = local_path.read_bytes()
        result = client.write_file(remote_path, content)
        client.close()
    except Exception as exc:
        _api_error_exit(exc)

    if _json_output:
        _output(result, as_json=True)
    else:
        console.print(f"[green]✓ Uploaded[/green] {local_path.name} → {remote_path} ({result.get('size', len(content))} bytes)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    app()
