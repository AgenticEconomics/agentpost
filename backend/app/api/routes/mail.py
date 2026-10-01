"""Mail API routes - inbox, outbox, compose, reply, threads."""
from __future__ import annotations

import base64
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from app.api.auth import authenticate_request, require_box_access, require_operator, AuthContext
from app.boxfs.paths import atomic_write, box_path, list_messages
from app.message.protocol import (
    Attachment,
    Message,
    Routing,
    generate_filename,
    generate_message_id,
    parse_message,
)

router = APIRouter()


class ComposeRequest(BaseModel):
    to: list[str]
    cc: list[str] = Field(default_factory=list)
    subject: str
    body: str = ""
    type: str = "request"
    priority: str = "normal"
    thread_id: str = ""
    in_reply_to: Optional[str] = None
    ack: bool = True
    labels: list[str] = Field(default_factory=list)
    attachments: list[dict] = Field(default_factory=list)


@router.get("/boxes/{box_id}/inbox")
async def list_inbox(
    request: Request,
    box_id: str,
    folder: str = Query(default="new"),
    unread: Optional[int] = Query(default=None),
    limit: int = Query(default=50),
    from_addr: Optional[str] = Query(default=None, alias="from"),
    subject: Optional[str] = Query(default=None),
    since: Optional[str] = Query(default=None),
    until: Optional[str] = Query(default=None),
    label: Optional[str] = Query(default=None),
    type_filter: Optional[str] = Query(default=None, alias="type"),
):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    if not registry.get(box_id):
        raise HTTPException(status_code=404, detail=f"Box '{box_id}' not found")

    bp = box_path(registry.root, box_id)
    if folder == "new":
        target = bp / "inbox" / "new"
    elif folder == "seen":
        target = bp / "inbox" / "cur" / "seen"
    else:
        target = bp / "inbox" / "cur"

    files = list_messages(target, limit=limit * 3 if any([from_addr, subject, since, until, label, type_filter]) else limit)
    messages = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            msg = parse_message(content)
            summary = msg.to_summary()
            summary["_file"] = f.name
            messages.append(summary)
        except Exception:
            messages.append({"_file": f.name, "subject": "(parse error)", "type": "unknown"})

    # IMP-002: search/filter
    if from_addr:
        messages = [m for m in messages if m.get("from", "").lower().startswith(from_addr.lower())]
    if subject:
        kw = subject.lower()
        messages = [m for m in messages if kw in m.get("subject", "").lower()]
    if since:
        messages = [m for m in messages if m.get("date", "") >= since]
    if until:
        messages = [m for m in messages if m.get("date", "") <= until]
    if label:
        messages = [m for m in messages if label in m.get("labels", [])]
    if type_filter:
        messages = [m for m in messages if m.get("type") == type_filter]

    return messages[:limit]


@router.get("/boxes/{box_id}/inbox/{message_id}")
async def read_message(request: Request, box_id: str, message_id: str):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    if not registry.get(box_id):
        raise HTTPException(status_code=404, detail=f"Box '{box_id}' not found")

    bp = box_path(registry.root, box_id)
    for subdir in ["inbox/cur", "inbox/new", "inbox/cur/seen"]:
        target = bp / subdir
        if not target.is_dir():
            continue
        for f in target.iterdir():
            if f.is_file():
                try:
                    content = f.read_text(encoding="utf-8")
                    msg = parse_message(content)
                    if msg.message_id == message_id or f.name == message_id:
                        result = msg.to_summary()
                        result["body"] = msg.body
                        result["attachments"] = [
                            {"name": a.name, "path": a.path, "media_type": a.media_type, "sha256": a.sha256}
                            for a in msg.attachments
                        ]
                        result["_file"] = f.name
                        return result
                except Exception:
                    continue

    raise HTTPException(status_code=404, detail="Message not found")


@router.post("/boxes/{box_id}/inbox/{message_id}/ack")
async def ack_message(request: Request, box_id: str, message_id: str):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    for subdir in ["inbox/cur", "inbox/new"]:
        target = bp / subdir
        if not target.is_dir():
            continue
        for f in target.iterdir():
            if f.is_file():
                try:
                    content = f.read_text(encoding="utf-8")
                    msg = parse_message(content)
                    if msg.message_id == message_id or f.name == message_id:
                        seen_dir = bp / "inbox" / "cur" / "seen"
                        seen_dir.mkdir(parents=True, exist_ok=True)
                        import os
                        os.replace(str(f), str(seen_dir / f.name))
                        return {"status": "acked", "message_id": message_id}
                except Exception:
                    continue

    raise HTTPException(status_code=404, detail="Message not found")


class BatchAckRequest(BaseModel):
    files: list[str] = Field(default_factory=list)
    ack_all: bool = False


@router.post("/boxes/{box_id}/inbox/batch-ack")
async def batch_ack(request: Request, box_id: str, body: BatchAckRequest):
    """Ack multiple messages at once, or ack all in folder."""
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    import os
    seen_dir = bp / "inbox" / "cur" / "seen"
    seen_dir.mkdir(parents=True, exist_ok=True)

    results = []
    acked = 0
    not_found = 0

    # Collect files to ack
    files_to_ack: set[str] = set()
    if body.ack_all:
        for subdir_name in ["inbox/new", "inbox/cur"]:
            target = bp / subdir_name
            if target.is_dir():
                for f in target.iterdir():
                    if f.is_file() and not f.name.startswith("."):
                        files_to_ack.add(f.name)
    else:
        files_to_ack = set(body.files)

    for filename in files_to_ack:
        found = False
        for subdir_name in ["inbox/new", "inbox/cur"]:
            target = bp / subdir_name
            if not target.is_dir():
                continue
            src = target / filename
            if src.is_file():
                os.replace(str(src), str(seen_dir / filename))
                results.append({"file": filename, "status": "acked"})
                acked += 1
                found = True
                break
        if not found:
            results.append({"file": filename, "status": "not_found"})
            not_found += 1

    return {"acked": acked, "not_found": not_found, "results": results}


@router.get("/boxes/{box_id}/outbox")
async def list_outbox(
    request: Request,
    box_id: str,
    folder: str = Query(default="sent"),
    limit: int = Query(default=50),
):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    if not registry.get(box_id):
        raise HTTPException(status_code=404, detail=f"Box '{box_id}' not found")

    bp = box_path(registry.root, box_id)
    target = bp / "outbox" / folder
    if not target.is_dir():
        return []

    files = list_messages(target, limit=limit)
    messages = []
    for f in files:
        try:
            content = f.read_text(encoding="utf-8")
            msg = parse_message(content)
            summary = msg.to_summary()
            summary["_file"] = f.name
            messages.append(summary)
        except Exception:
            messages.append({"_file": f.name, "subject": "(parse error)", "type": "unknown"})
    return messages


@router.post("/boxes/{box_id}/outbox")
async def compose_message(request: Request, box_id: str, body: ComposeRequest):
    ctx = authenticate_request(request)
    if ctx.role == "operator":
        if not body.to:
            raise HTTPException(status_code=400, detail="to is required")
    else:
        require_box_access(ctx, box_id)

    registry = request.app.state.registry
    entry = registry.get(box_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Box '{box_id}' not found")
    if entry.get("status") != "active":
        raise HTTPException(status_code=400, detail=f"Box '{box_id}' is not active")

    domain = request.app.state.settings.domain
    from_addr = f"{box_id}@{domain}"
    msg_id = generate_message_id(box_id, domain)
    now = datetime.now(timezone.utc).isoformat()

    msg = Message(
        protocol="agentpost/1",
        message_id=msg_id,
        from_addr=from_addr,
        to=body.to,
        cc=body.cc,
        subject=body.subject,
        date=now,
        type=body.type,
        priority=body.priority,
        in_reply_to=body.in_reply_to,
        thread_id=body.thread_id or f"thr-{int(time.time())}",
        payload_format="markdown",
        routing=Routing(notify=True, ack=body.ack if isinstance(body.ack, bool) else False),
        labels=body.labels,
        body=body.body,
    )

    # Handle attachments
    bp = box_path(registry.root, box_id)
    if body.attachments:
        att_objects = []
        for att_data in body.attachments:
            filename = att_data.get("filename", "attachment")
            content_b64 = att_data.get("content_base64", "")
            if content_b64:
                att_dir = bp / "data" / "outbound" / msg_id.strip("<>")
                att_dir.mkdir(parents=True, exist_ok=True)
                att_path = att_dir / filename
                att_path.write_bytes(base64.b64decode(content_b64))
                att_objects.append(Attachment(
                    name=filename,
                    path=f"../../data/outbound/{msg_id.strip('<>')}/{filename}",
                    media_type=att_data.get("media_type", "application/octet-stream"),
                ))
        msg.attachments = att_objects

    content = msg.serialize()
    filename = generate_filename(box_id)
    atomic_write(bp / "outbox" / "new", filename, content)

    request.app.state.events.emit("mail.outbox_accepted", {
        "box": box_id,
        "message_id": msg_id,
        "to": body.to,
        "subject": body.subject,
    })
    request.app.state.audit.log("accept", message_id=msg_id, box=box_id)

    return {
        "status": "accepted",
        "message_id": msg_id,
        "from": from_addr,
        "filename": filename,
    }


@router.get("/boxes/{box_id}/threads/{thread_id}")
async def get_thread(request: Request, box_id: str, thread_id: str):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    messages = []
    for subdir in ["inbox/cur", "inbox/new", "inbox/cur/seen", "outbox/sent", "outbox/new"]:
        target = bp / subdir
        if not target.is_dir():
            continue
        for f in target.iterdir():
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8")
                msg = parse_message(content)
                if msg.thread_id == thread_id:
                    summary = msg.to_summary()
                    summary["_folder"] = subdir
                    summary["_file"] = f.name
                    messages.append(summary)
            except Exception:
                continue

    messages.sort(key=lambda m: m.get("date", ""))
    return messages


# ── IMP-001: Delivery status query ─────────────────────────────────────────


@router.get("/boxes/{box_id}/outbox/{message_id}/receipt")
async def get_receipt(request: Request, box_id: str, message_id: str):
    """Query delivery receipt status for a sent message."""
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    # Search for a receipt message with matching receipt_for
    for subdir in ["inbox/new", "inbox/cur", "inbox/cur/seen"]:
        target = bp / subdir
        if not target.is_dir():
            continue
        for f in target.iterdir():
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8")
                msg = parse_message(content)
                if msg.type == "receipt" and (msg.receipt_for == message_id or message_id in f.name):
                    return {
                        "message_id": message_id,
                        "status": msg.receipt_status or "unknown",
                        "delivered_to": msg.delivered_to,
                        "failed_to": msg.failed_to,
                        "receipt_date": msg.date,
                        "reason": msg.receipt_reason,
                        "_file": f.name,
                    }
            except Exception:
                continue

    # No receipt found — check if the original message exists in outbox/sent
    sent_dir = bp / "outbox" / "sent"
    if sent_dir.is_dir():
        for f in sent_dir.iterdir():
            if f.is_file() and (message_id in f.name or message_id in f.read_text(errors="ignore")[:200]):
                return {
                    "message_id": message_id,
                    "status": "pending",
                    "delivered_to": [],
                    "failed_to": [],
                    "receipt_date": None,
                    "reason": "Receipt not yet received",
                }

    raise HTTPException(status_code=404, detail="No receipt found for this message")


# ── IMP-004: Message export ────────────────────────────────────────────────


@router.get("/boxes/{box_id}/export")
async def export_messages(
    request: Request,
    box_id: str,
    since: Optional[str] = Query(default=None),
    format: str = Query(default="json"),
    limit: int = Query(default=200),
):
    """Export messages as JSON or Markdown."""
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    collected: list[dict] = []
    scan_dirs = [
        ("inbox/new", bp / "inbox" / "new"),
        ("inbox/cur/seen", bp / "inbox" / "cur" / "seen"),
        ("outbox/sent", bp / "outbox" / "sent"),
    ]

    for folder_name, target in scan_dirs:
        if not target.is_dir():
            continue
        for f in sorted(target.iterdir(), key=lambda p: p.stat().st_mtime):
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8")
                msg = parse_message(content)
                if since and msg.date < since:
                    continue
                entry = {
                    "message_id": msg.message_id,
                    "from": msg.from_addr,
                    "to": msg.to,
                    "subject": msg.subject,
                    "date": msg.date,
                    "type": msg.type,
                    "priority": msg.priority,
                    "labels": msg.labels,
                    "thread_id": msg.thread_id,
                    "in_reply_to": msg.in_reply_to,
                    "body": msg.body,
                    "folder": folder_name,
                }
                collected.append(entry)
            except Exception:
                continue
            if len(collected) >= limit:
                break
        if len(collected) >= limit:
            break

    collected.sort(key=lambda m: m.get("date", ""))

    if format == "markdown":
        from fastapi.responses import PlainTextResponse
        lines = [f"# {box_id} 通信导出\n", f"导出时间: {datetime.now(timezone.utc).isoformat()}\n", f"消息数: {len(collected)}\n", "---\n"]
        for m in collected:
            lines.append(f"\n## {m['date'][:19]} — {m['subject']}\n")
            lines.append(f"- From: {m['from']}\n- To: {', '.join(m['to'])}\n- Type: {m['type']}\n- Folder: {m['folder']}\n")
            lines.append(f"\n{m['body']}\n")
            lines.append("\n---\n")
        return PlainTextResponse("".join(lines), media_type="text/markdown")

    return {
        "box": box_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "count": len(collected),
        "messages": collected,
    }
