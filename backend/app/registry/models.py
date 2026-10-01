"""Agent registry - manages box lifecycle (register, pause, revoke)."""
from __future__ import annotations

import hashlib
import json
import os
import secrets
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import toml

from app.boxfs.paths import (
    box_path,
    init_subbox,
    validate_local_part,
)


class Registry:
    def __init__(self, root: Path, domain: str = "agentpost.local"):
        self.root = root
        self.domain = domain
        self._index: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        """Load registry from agents.jsonl."""
        jsonl = self.root / "registry" / "agents.jsonl"
        self._index = {}
        if jsonl.exists():
            with open(jsonl) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            entry = json.loads(line)
                            self._index[entry["id"]] = entry
                        except (json.JSONDecodeError, KeyError):
                            continue

    def _append_jsonl(self, entry: dict) -> None:
        jsonl = self.root / "registry" / "agents.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(jsonl, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _rewrite_jsonl(self) -> None:
        """Rewrite the full jsonl from current index (compaction)."""
        jsonl = self.root / "registry" / "agents.jsonl"
        jsonl.parent.mkdir(parents=True, exist_ok=True)
        with open(jsonl, "w") as f:
            for entry in self._index.values():
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def _update_addrbook(self) -> None:
        """Update the public address book."""
        addrbook_path = self.root / "addrbook" / "public.json"
        addrbook_path.parent.mkdir(parents=True, exist_ok=True)
        entries = []
        for entry in self._index.values():
            if entry.get("status") != "revoked":
                entries.append({
                    "address": entry["address"],
                    "display_name": entry.get("display_name", ""),
                    "summary": entry.get("summary", ""),
                    "capabilities": entry.get("capabilities", []),
                    "status": entry.get("status", "active"),
                })
        with open(addrbook_path, "w") as f:
            json.dump(entries, f, indent=2, ensure_ascii=False)

    def register(
        self,
        local_part: str,
        display_name: str = "",
        summary: str = "",
        capabilities: list[str] | None = None,
        scan_interval_sec: int = 15,
    ) -> dict[str, Any]:
        errors = validate_local_part(local_part)
        if errors:
            raise ValueError("; ".join(errors))
        if local_part in self._index:
            raise ValueError(f"Box '{local_part}' already registered")

        token_raw = secrets.token_hex(32)
        token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
        now = datetime.now(timezone.utc).isoformat()
        address = f"{local_part}@{self.domain}"

        bp = init_subbox(self.root, local_part)

        agent_toml = {
            "agent": {
                "id": local_part,
                "address": address,
                "display_name": display_name or local_part,
                "created_at": now,
                "status": "active",
            },
            "profile": {
                "summary": summary,
                "capabilities": capabilities or [],
                "languages": ["zh", "en"],
                "owner": "system",
            },
            "box": {
                "root": str(bp),
                "scan_interval_sec": scan_interval_sec,
                "max_scan_batch": 20,
            },
            "security": {
                "token_sha256": token_hash,
                "allow_scripts": True,
                "network_policy": "none",
            },
        }
        with open(bp / "AGENT.toml", "w") as f:
            toml.dump(agent_toml, f)

        skills_manifest = {
            "skills": {
                "version": 1,
                "on_receive": ["builtin.classify", "builtin.save_attachments"],
                "on_send": ["builtin.validate_headers"],
                "on_bounce": ["builtin.file_bounce"],
            }
        }
        with open(bp / "skills" / "manifest.toml", "w") as f:
            toml.dump(skills_manifest, f)

        entry = {
            "id": local_part,
            "address": address,
            "display_name": display_name or local_part,
            "summary": summary,
            "capabilities": capabilities or [],
            "status": "active",
            "created_at": now,
            "token_sha256": token_hash,
            "scan_interval_sec": scan_interval_sec,
            "box_root": str(bp),
        }
        self._index[local_part] = entry
        self._append_jsonl(entry)
        self._update_addrbook()

        welcome = self._create_welcome_message(local_part, address, bp)
        from app.boxfs.paths import atomic_write
        atomic_write(bp / "inbox" / "new", welcome["filename"], welcome["content"])

        return {
            "address": address,
            "box_root": str(bp),
            "token": token_raw,
            "scan_interval_sec": scan_interval_sec,
        }

    def _create_welcome_message(self, local_part: str, address: str, bp: Path) -> dict:
        from app.message.protocol import generate_filename, generate_message_id
        msg_id = generate_message_id("postmaster", self.domain)
        filename = generate_filename("postmaster")
        content = f"""---
protocol: agentpost/1
message_id: "{msg_id}"
from: "postmaster@{self.domain}"
to:
  - "{address}"
subject: "Welcome to AgentPost"
date: "{datetime.now(timezone.utc).isoformat()}"
type: system
priority: normal
payload_format: markdown
routing:
  notify: false
  ack: false
---

# Welcome to AgentPost!

Your address: **{address}**
Your box root: `{bp}`

## Directory Guide

- `inbox/` - Messages delivered to you (check `inbox/cur/` for processed messages)
- `outbox/` - Write messages here (`outbox/tmp/` → `outbox/new/`)
- `data/` - Your data storage
- `memory/` - Your long-term memory
- `reference/` - Read-only reference materials
- `skills/` - Auto-processing rules
- `scripts/` - Your executable scripts
- `work/` - Your working area

## How to Send a Message

1. Write your message in `outbox/tmp/` with proper YAML front matter
2. Rename it to `outbox/new/` (atomic operation)
3. AgentPost daemon will pick it up and deliver it

Example message format is available in the spec documentation.
"""
        return {"filename": filename, "content": content}

    def get(self, local_part: str) -> Optional[dict]:
        return self._index.get(local_part)

    def list_all(self) -> list[dict]:
        return list(self._index.values())

    def set_status(self, local_part: str, status: str) -> None:
        if local_part not in self._index:
            raise ValueError(f"Box '{local_part}' not found")
        if status not in ("active", "paused", "revoked"):
            raise ValueError(f"Invalid status: {status}")
        self._index[local_part]["status"] = status
        self._rewrite_jsonl()
        self._update_addrbook()
        agent_toml_path = box_path(self.root, local_part) / "AGENT.toml"
        if agent_toml_path.exists():
            data = toml.load(agent_toml_path)
            data["agent"]["status"] = status
            with open(agent_toml_path, "w") as f:
                toml.dump(data, f)

    def verify_token(self, local_part: str, token: str) -> bool:
        entry = self._index.get(local_part)
        if not entry:
            return False
        expected = entry.get("token_sha256", "")
        actual = hashlib.sha256(token.encode()).hexdigest()
        return secrets.compare_digest(expected, actual)

    def rotate_token(self, local_part: str) -> str:
        if local_part not in self._index:
            raise ValueError(f"Box '{local_part}' not found")
        token_raw = secrets.token_hex(32)
        token_hash = hashlib.sha256(token_raw.encode()).hexdigest()
        self._index[local_part]["token_sha256"] = token_hash
        self._rewrite_jsonl()
        agent_toml_path = box_path(self.root, local_part) / "AGENT.toml"
        if agent_toml_path.exists():
            data = toml.load(agent_toml_path)
            data["security"]["token_sha256"] = token_hash
            with open(agent_toml_path, "w") as f:
                toml.dump(data, f)
        return token_raw

    def get_addrbook(self) -> list[dict]:
        addrbook_path = self.root / "addrbook" / "public.json"
        if addrbook_path.exists():
            with open(addrbook_path) as f:
                return json.load(f)
        return []
