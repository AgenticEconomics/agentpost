"""AgentPost API - FastHTTP application with auth middleware."""
from __future__ import annotations

import secrets
from typing import Optional

from fastapi import HTTPException, Request


class AuthContext:
    """Holds the authenticated identity for a request."""

    def __init__(self, role: str, box_id: Optional[str] = None, act_as_box: Optional[str] = None):
        self.role = role  # "operator" or "box"
        self.box_id = box_id  # For box tokens: the box local_part
        self.act_as_box = act_as_box  # For operator acting as a box

    @property
    def effective_box_id(self) -> Optional[str]:
        if self.role == "box":
            return self.box_id
        return self.act_as_box


def authenticate_request(request: Request) -> AuthContext:
    """Extract and validate authentication from the request."""
    app_state = request.app.state
    registry = app_state.registry
    operator_token = app_state.settings.operator_token

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")

    token = auth_header[7:]
    act_as = request.headers.get("X-Act-As-Box", "")

    # Check operator token
    if operator_token and secrets.compare_digest(token, operator_token):
        return AuthContext(role="operator", act_as_box=act_as if act_as else None)

    # Check box tokens
    for entry in registry.list_all():
        local_part = entry["id"]
        if registry.verify_token(local_part, token):
            if act_as and act_as != local_part:
                raise HTTPException(status_code=403, detail="Box token cannot act as another box")
            return AuthContext(role="box", box_id=local_part)

    raise HTTPException(status_code=401, detail="Invalid token")


def require_operator(ctx: AuthContext) -> None:
    if ctx.role != "operator":
        raise HTTPException(status_code=403, detail="Operator token required")


def require_box_access(ctx: AuthContext, box_id: str) -> None:
    """Ensure the authenticated user can access the specified box."""
    if ctx.role == "box" and ctx.box_id != box_id:
        raise HTTPException(status_code=403, detail="Access denied to this box")
