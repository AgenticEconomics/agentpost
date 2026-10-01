"""System API routes - health, version, metrics, config, doctor."""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends, Request

from app.api.auth import authenticate_request, require_operator, AuthContext

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    engine = request.app.state.engine
    settings = request.app.state.settings
    ready = request.app.state.ready
    return {
        "status": "ok" if ready else "starting",
        "version": request.app.version,
        "ready": ready,
        "queue_depth": engine.get_queue_depth() if engine else {},
        "boxes": len(request.app.state.registry.list_all()) if hasattr(request.app.state, "registry") else 0,
        "uptime_sec": int(time.time() - request.app.state.start_time) if hasattr(request.app.state, "start_time") else 0,
    }


@router.get("/version")
async def version(request: Request):
    return {
        "version": request.app.version,
        "protocol": "agentpost/1",
    }


@router.get("/metrics")
async def metrics(request: Request):
    ctx = authenticate_request(request)
    require_operator(ctx)
    engine = request.app.state.engine
    return {
        "delivery": engine.stats,
        "queue_depth": engine.get_queue_depth(),
        "boxes": len(request.app.state.registry.list_all()),
    }


@router.get("/config")
async def config(request: Request):
    ctx = authenticate_request(request)
    require_operator(ctx)
    settings = request.app.state.settings
    return {
        "domain": settings.domain,
        "root": settings.root,
        "watch_interval_ms": settings.watch_interval_ms,
        "max_attachment_bytes": settings.max_attachment_bytes,
        "max_message_bytes": settings.max_message_bytes,
        "api": {"host": settings.api.host, "port": settings.api.port},
        "scan": {"default_interval_sec": settings.scan.default_interval_sec},
        "security": {
            "require_from_match": settings.security.require_from_match,
            "allow_broadcast": settings.security.allow_broadcast,
            "script_timeout_sec": settings.security.script_timeout_sec,
        },
    }


@router.post("/doctor")
async def doctor(request: Request):
    ctx = authenticate_request(request)
    require_operator(ctx)
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    repair = body.get("repair", False)
    engine = request.app.state.engine
    issues = engine.doctor(repair=repair)
    return {"issues": issues, "repaired": repair, "count": len(issues)}
