"""Filesystem operations for AgentPost - atomic writes, path guards, directory management."""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import time
from pathlib import Path
from typing import Optional

LOCAL_PART_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")
RESERVED_NAMES = {"system", "postmaster", "agentpost", "all", "broadcast"}

SUBBOX_DIRS = [
    "inbox/new",
    "inbox/cur",
    "inbox/cur/seen",
    "inbox/tmp",
    "outbox/new",
    "outbox/tmp",
    "outbox/sent",
    "outbox/failed",
    "reference",
    "data",
    "data/inbound",
    "scripts",
    "memory/episodic",
    "memory/semantic",
    "skills/on_receive",
    "skills/on_send",
    "skills/on_bounce",
    "skills/builtin",
    "work",
    "logs",
]

SYSTEM_DIRS = [
    "registry",
    "boxes",
    "spool/incoming",
    "spool/retry",
    "spool/dead-letter",
    "logs",
    "run",
    "addrbook",
]


def validate_local_part(name: str) -> list[str]:
    errors = []
    if not name:
        errors.append("local_part cannot be empty")
    elif not LOCAL_PART_RE.match(name):
        errors.append(f"Invalid local_part '{name}': must match [a-z0-9][a-z0-9._-]{{1,62}}")
    if name.lower() in RESERVED_NAMES:
        errors.append(f"'{name}' is a reserved name")
    if ".." in name:
        errors.append("local_part must not contain '..'")
    return errors


def init_root(root: Path) -> None:
    """Initialize the AgentPost root directory structure."""
    root.mkdir(parents=True, exist_ok=True)
    for d in SYSTEM_DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)


def init_subbox(root: Path, local_part: str) -> Path:
    """Create a complete SubBox directory tree."""
    box_path = root / "boxes" / local_part
    for d in SUBBOX_DIRS:
        (box_path / d).mkdir(parents=True, exist_ok=True)
    return box_path


def box_path(root: Path, local_part: str) -> Path:
    return root / "boxes" / local_part


def resolve_address(root: Path, address: str, domain: str) -> Optional[Path]:
    """Resolve an email address to a SubBox path."""
    if "@" not in address:
        return None
    local, dom = address.rsplit("@", 1)
    if dom != domain:
        return None
    bp = box_path(root, local)
    if bp.is_dir():
        return bp
    return None


def atomic_write(target_dir: Path, filename: str, content: str | bytes) -> Path:
    """Write content atomically: write to tmp/ then rename to target_dir."""
    tmp_dir = target_dir.parent / "tmp" if target_dir.name != "tmp" else target_dir
    tmp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = tmp_dir / f".tmp.{int(time.time()*1000)}.{filename}"
    mode = "wb" if isinstance(content, bytes) else "w"
    with open(tmp_path, mode) as f:
        f.write(content)
    final_path = target_dir / filename
    os.replace(str(tmp_path), str(final_path))
    return final_path


def safe_rename(src: Path, dst_dir: Path, new_name: Optional[str] = None) -> Path:
    """Atomically move a file from src to dst_dir."""
    name = new_name or src.name
    dst = dst_dir / name
    dst_dir.mkdir(parents=True, exist_ok=True)
    os.replace(str(src), str(dst))
    return dst


def is_path_within(path: Path, root: Path) -> bool:
    """Check if a resolved path is within a root directory (path traversal guard)."""
    try:
        resolved = path.resolve()
        root_resolved = root.resolve()
        return str(resolved).startswith(str(root_resolved) + os.sep) or resolved == root_resolved
    except (OSError, ValueError):
        return False


def guard_path(base: Path, relative: str) -> Path:
    """Resolve a relative path within base, raising if it escapes."""
    if ".." in relative.split("/"):
        raise PermissionError(f"Path traversal detected: {relative}")
    full = (base / relative).resolve()
    if not is_path_within(full, base.resolve()):
        raise PermissionError(f"Path escapes box root: {relative}")
    return full


def compute_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def list_messages(directory: Path, limit: int = 100) -> list[Path]:
    """List message files in a directory, sorted by modification time (newest first)."""
    if not directory.is_dir():
        return []
    files = []
    for f in directory.iterdir():
        if f.is_file() and (f.suffix in (".md", ".json") or ".msg." in f.name):
            files.append(f)
    files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return files[:limit]


def cleanup_tmp(box_root: Path) -> list[str]:
    """Clean up stale tmp files (from crashed writes). Returns list of cleaned paths."""
    cleaned = []
    for tmp_dir_name in ["inbox/tmp", "outbox/tmp"]:
        tmp_dir = box_root / tmp_dir_name
        if not tmp_dir.is_dir():
            continue
        for f in tmp_dir.iterdir():
            if f.is_file() and f.name.startswith(".tmp."):
                age = time.time() - f.stat().st_mtime
                if age > 300:  # 5 minutes
                    f.unlink()
                    cleaned.append(str(f))
    return cleaned


def doctor_box(box_root: Path) -> list[dict]:
    """Check a SubBox for structural issues."""
    issues = []
    for d in SUBBOX_DIRS:
        p = box_root / d
        if not p.exists():
            issues.append({"path": str(d), "issue": "missing_directory", "repairable": True})
    for tmp_name in ["inbox/tmp", "outbox/tmp"]:
        tmp_dir = box_root / tmp_name
        if tmp_dir.is_dir():
            for f in tmp_dir.iterdir():
                if f.is_file():
                    issues.append({"path": str(tmp_name / f.name), "issue": "stale_tmp_file", "repairable": True})
    agent_toml = box_root / "AGENT.toml"
    if not agent_toml.exists():
        issues.append({"path": "AGENT.toml", "issue": "missing_identity_file", "repairable": False})
    return issues


def repair_box(box_root: Path) -> list[str]:
    """Repair missing directories in a SubBox."""
    repaired = []
    for d in SUBBOX_DIRS:
        p = box_root / d
        if not p.exists():
            p.mkdir(parents=True, exist_ok=True)
            repaired.append(f"Created {d}")
    return repaired
