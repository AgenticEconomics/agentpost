"""Files API routes - box file access, memory, skills, logs."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile, File
from fastapi.responses import FileResponse

from app.api.auth import authenticate_request, require_box_access
from app.boxfs.paths import box_path, guard_path, is_path_within

router = APIRouter()

WRITABLE_DIRS = {"data", "memory", "work"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB


@router.get("/boxes/{box_id}/files")
async def list_files(
    request: Request,
    box_id: str,
    path: str = Query(default=""),
):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    if not path:
        target = bp
    else:
        try:
            target = guard_path(bp, path)
        except PermissionError as e:
            raise HTTPException(status_code=403, detail=str(e))

    if not target.is_dir():
        raise HTTPException(status_code=404, detail=f"Directory not found: {path}")

    items = []
    for item in sorted(target.iterdir()):
        rel = str(item.relative_to(bp))
        if item.is_dir():
            items.append({"name": item.name, "type": "dir", "path": rel})
        elif item.is_file():
            stat = item.stat()
            items.append({
                "name": item.name,
                "type": "file",
                "path": rel,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
    return items


@router.get("/boxes/{box_id}/files/content")
async def read_file_content(
    request: Request,
    box_id: str,
    path: str = Query(...),
):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    try:
        target = guard_path(bp, path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    if not target.is_file():
        raise HTTPException(status_code=404, detail=f"File not found: {path}")

    if target.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="File too large")

    return FileResponse(str(target))


@router.put("/boxes/{box_id}/files/content")
async def write_file_content(
    request: Request,
    box_id: str,
    path: str = Query(...),
):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    # Only allow writing to data/, memory/, work/
    top_dir = path.split("/")[0] if "/" in path else path
    if top_dir not in WRITABLE_DIRS:
        raise HTTPException(status_code=403, detail=f"Writing to '{top_dir}/' is not allowed")

    try:
        target = guard_path(bp, path)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))

    # Prevent writing directly into inbox/
    if "inbox" in str(target.relative_to(bp)).split("/"):
        raise HTTPException(status_code=403, detail="Cannot write directly to inbox/")

    body = await request.body()
    if len(body) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Content too large")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(body)
    return {"status": "written", "path": path, "size": len(body)}


@router.get("/boxes/{box_id}/memory")
async def get_memory(request: Request, box_id: str):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    result = {"episodic": [], "semantic": {}}

    episodic_index = bp / "memory" / "episodic" / "inbox-index.jsonl"
    if episodic_index.exists():
        with open(episodic_index) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        result["episodic"].append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        result["episodic"] = result["episodic"][-50:]

    semantic_dir = bp / "memory" / "semantic"
    if semantic_dir.is_dir():
        for f in semantic_dir.iterdir():
            if f.is_file() and f.suffix == ".json":
                try:
                    with open(f) as fh:
                        result["semantic"][f.stem] = json.load(fh)
                except (json.JSONDecodeError, OSError):
                    pass

    return result


@router.get("/boxes/{box_id}/skills")
async def get_skills(request: Request, box_id: str):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    from app.skills.engine import SkillsEngine
    engine = SkillsEngine(bp)
    manifest = engine.get_manifest()

    # Get recent skill executions
    log_file = bp / "logs" / "skills.log"
    recent = []
    if log_file.exists():
        with open(log_file) as f:
            lines = f.readlines()
        for line in lines[-20:]:
            try:
                recent.append(json.loads(line.strip()))
            except json.JSONDecodeError:
                pass

    return {"manifest": manifest, "recent": recent}


@router.put("/boxes/{box_id}/skills/manifest")
async def update_skills_manifest(request: Request, box_id: str):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)
    registry = request.app.state.registry
    bp = box_path(registry.root, box_id)

    body = await request.json()
    import toml
    manifest_path = bp / "skills" / "manifest.toml"
    with open(manifest_path, "w") as f:
        toml.dump(body, f)

    return {"status": "updated"}


@router.get("/boxes/{box_id}/logs")
async def get_box_logs(request: Request, box_id: str, since: Optional[str] = None):
    ctx = authenticate_request(request)
    require_box_access(ctx, box_id)

    audit = request.app.state.audit
    entries = audit.get_recent(box=box_id, limit=100)
    return entries
