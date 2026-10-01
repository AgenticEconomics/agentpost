"""Queue API routes - spool, dead-letter management."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.api.auth import authenticate_request, require_operator

router = APIRouter()


@router.get("/spool")
async def get_spool(request: Request):
    ctx = authenticate_request(request)
    require_operator(ctx)
    engine = request.app.state.engine
    depths = engine.get_queue_depth()
    dead = engine.dead_letter_list()
    return {"depths": depths, "dead_letter": dead[:50]}


@router.post("/spool/dead-letter/{item_id}/retry")
async def retry_dead_letter(request: Request, item_id: str):
    ctx = authenticate_request(request)
    require_operator(ctx)
    engine = request.app.state.engine
    success = engine.dead_letter_retry(item_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Dead letter '{item_id}' not found")
    return {"status": "retried", "id": item_id}


@router.post("/spool/dead-letter/{item_id}/drop")
async def drop_dead_letter(request: Request, item_id: str):
    ctx = authenticate_request(request)
    require_operator(ctx)
    engine = request.app.state.engine
    success = engine.dead_letter_drop(item_id)
    if not success:
        raise HTTPException(status_code=404, detail=f"Dead letter '{item_id}' not found")
    request.app.state.audit.log("dead_letter_drop", item_id=item_id)
    return {"status": "dropped", "id": item_id}
