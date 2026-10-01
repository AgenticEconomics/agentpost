"""WebSocket route for real-time event streaming."""
from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.auth import AuthContext
from app.events.bus import Event

router = APIRouter()


@router.websocket("/stream")
async def event_stream(websocket: WebSocket):
    """WebSocket endpoint for real-time events.

    Supports query params:
    - token: authentication token
    - box: filter events for a specific box (operator only)
    """
    await websocket.accept()

    # Authenticate
    params = websocket.query_params
    token = params.get("token", "")
    box_filter = params.get("box", "")

    app_state = websocket.app.state
    registry = app_state.registry
    settings = app_state.settings

    ctx: AuthContext | None = None

    # Try operator token
    import secrets
    if settings.operator_token and secrets.compare_digest(token, settings.operator_token):
        ctx = AuthContext(role="operator", act_as_box=box_filter if box_filter else None)
    else:
        # Try box tokens
        for entry in registry.list_all():
            local_part = entry["id"]
            if registry.verify_token(local_part, token):
                ctx = AuthContext(role="box", box_id=local_part)
                break

    if not ctx:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # Subscribe to events
    queue = app_state.events.subscribe("*")

    try:
        while True:
            try:
                event: Event = await asyncio.wait_for(queue.get(), timeout=30)
            except asyncio.TimeoutError:
                # Send keepalive
                await websocket.send_json({"type": "keepalive"})
                continue

            # Filter events based on role
            if ctx.role == "box" and ctx.box_id:
                event_box = event.data.get("box", "")
                if event_box and event_box != ctx.box_id:
                    continue
            elif ctx.role == "operator" and ctx.act_as_box:
                event_box = event.data.get("box", "")
                if event_box and event_box != ctx.act_as_box:
                    continue

            await websocket.send_json(event.to_dict())

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        app_state.events.unsubscribe(queue, "*")
