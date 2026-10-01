"""Structured audit logging for AgentPost."""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


class AuditLogger:
    def __init__(self, logs_dir: Path):
        self.logs_dir = logs_dir
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self._logger = logging.getLogger("agentpost.audit")
        handler = logging.FileHandler(logs_dir / "audit.jsonl")
        handler.setFormatter(logging.Formatter("%(message)s"))
        self._logger.addHandler(handler)
        self._logger.setLevel(logging.INFO)

    def log(
        self,
        stage: str,
        message_id: str = "",
        box: str = "",
        **extra: Any,
    ) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "stage": stage,
            "message_id": message_id,
            "box": box,
            **extra,
        }
        self._logger.info(json.dumps(entry, ensure_ascii=False))

    def get_recent(self, box: Optional[str] = None, limit: int = 50) -> list[dict]:
        log_file = self.logs_dir / "audit.jsonl"
        if not log_file.exists():
            return []
        entries = []
        with open(log_file) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entry = json.loads(line)
                        if box and entry.get("box") != box:
                            continue
                        entries.append(entry)
                    except json.JSONDecodeError:
                        continue
        return entries[-limit:]


class BoxLogger:
    """Per-box audit logger that writes to the box's own logs/ directory."""

    def __init__(self, box_root: Path):
        self.log_dir = box_root / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._log_file = self.log_dir / "activity.log"

    def log(self, message: str) -> None:
        ts = datetime.now(timezone.utc).isoformat()
        with open(self._log_file, "a") as f:
            f.write(f"[{ts}] {message}\n")
