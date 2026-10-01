"""Boxes API routes - register, list, show, pause, revoke, token rotate."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.auth import authenticate_request, require_operator, require_box_access, AuthContext
from app.boxfs.paths import box_path, cleanup_tmp

router = APIRouter()


class RegisterRequest(BaseModel):
    id: str
    display_name: str = ""
    summary: str = ""
    capabilities: list[str] = Field(default_factory=list)
    scan_interval_sec: int = 15


class PatchBoxRequest(BaseModel):
    status: str | None = None
    display_name: str | None = None
    summary: str | None = None


@router.post("/boxes")
async def register_box(request: Request, body: RegisterRequest):
    ctx = authenticate_request(request)
    require_operator(ctx)
    registry = request.app.state.registry
    try:
        result = registry.register(
            local_part=body.id,
            display_name=body.display_name,
            summary=body.summary,
            capabilities=body.capabilities,
            scan_interval_sec=body.scan_interval_sec,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    request.app.state.events.emit("box.registered", {"box": body.id, "address": result["address"]})
    request.app.state.audit.log("register", box=body.id)
    return result


@router.get("/boxes")
async def list_boxes(request: Request):
    ctx = authenticate_request(request)
    require_operator(ctx)
    registry = request.app.state.registry
    boxes = []
    for entry in registry.list_all():
        local_part = entry["id"]
        bp = box_path(registry.root, local_part)
        unread = 0
        inbox_cur = bp / "inbox" / "cur"
        if inbox_cur.is_dir():
            unread = len([f for f in inbox_cur.iterdir() if f.is_file() and not f.name.startswith(".")])
        inbox_new = bp / "inbox" / "new"
        if inbox_new.is_dir():
            unread += len([f for f in inbox_new.iterdir() if f.is_file() and not f.name.startswith(".")])

        sent = 0
        sent_dir = bp / "outbox" / "sent"
        if sent_dir.is_dir():
            sent = len([f for f in sent_dir.iterdir() if f.is_file()])

        failed = 0
        failed_dir = bp / "outbox" / "failed"
        if failed_dir.is_dir():
            failed = len([f for f in failed_dir.iterdir() if f.is_file()])

        boxes.append({
            "id": local_part,
            "address": entry["address"],
            "display_name": entry.get("display_name", ""),
            "status": entry.get("status", "active"),
            "summary": entry.get("summary", ""),
            "capabilities": entry.get("capabilities", []),
            "unread": unread,
            "sent": sent,
            "failed": failed,
        })
    return boxes


@router.get("/boxes/{box_id}")
async def get_box(request: Request, box_id: str):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    entry = registry.get(box_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Box '{box_id}' not found")

    bp = box_path(registry.root, box_id)
    from app.boxfs.paths import doctor_box
    issues = doctor_box(bp)

    inbox_new = bp / "inbox" / "new"
    inbox_cur = bp / "inbox" / "cur"
    outbox_new = bp / "outbox" / "new"
    outbox_sent = bp / "outbox" / "sent"
    outbox_failed = bp / "outbox" / "failed"

    return {
        **entry,
        "issues": issues,
        "queue": {
            "inbox_new": len([f for f in inbox_new.iterdir() if f.is_file()]) if inbox_new.is_dir() else 0,
            "inbox_cur": len([f for f in inbox_cur.iterdir() if f.is_file()]) if inbox_cur.is_dir() else 0,
            "outbox_new": len([f for f in outbox_new.iterdir() if f.is_file()]) if outbox_new.is_dir() else 0,
            "outbox_sent": len([f for f in outbox_sent.iterdir() if f.is_file()]) if outbox_sent.is_dir() else 0,
            "outbox_failed": len([f for f in outbox_failed.iterdir() if f.is_file()]) if outbox_failed.is_dir() else 0,
        },
    }


@router.patch("/boxes/{box_id}")
async def patch_box(request: Request, box_id: str, body: PatchBoxRequest):
    ctx = authenticate_request(request)
    require_operator(ctx)
    registry = request.app.state.registry
    entry = registry.get(box_id)
    if not entry:
        raise HTTPException(status_code=404, detail=f"Box '{box_id}' not found")

    if body.status:
        try:
            registry.set_status(box_id, body.status)
            request.app.state.events.emit("box.status_changed", {"box": box_id, "status": body.status})
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

    return {"id": box_id, "status": body.status or entry.get("status")}


@router.post("/boxes/{box_id}/revoke")
async def revoke_box(request: Request, box_id: str):
    ctx = authenticate_request(request)
    require_operator(ctx)
    registry = request.app.state.registry
    try:
        registry.set_status(box_id, "revoked")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    request.app.state.events.emit("box.status_changed", {"box": box_id, "status": "revoked"})
    return {"id": box_id, "status": "revoked"}


@router.post("/boxes/{box_id}/token/rotate")
async def rotate_token(request: Request, box_id: str):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    if not registry.get(box_id):
        raise HTTPException(status_code=404, detail=f"Box '{box_id}' not found")
    try:
        new_token = registry.rotate_token(box_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"id": box_id, "token": new_token}


@router.get("/addrbook")
async def addrbook(request: Request):
    ctx = authenticate_request(request)
    registry = request.app.state.registry
    return registry.get_addrbook()
