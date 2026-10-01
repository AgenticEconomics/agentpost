"""Skills engine - box-level auto-processing hooks."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import toml

from app.boxfs.paths import atomic_write, guard_path, is_path_within
from app.message.protocol import Message, parse_message


class SkillResult:
    def __init__(self, status: str = "ok", actions: list[dict] | None = None, notes: str = ""):
        self.status = status
        self.actions = actions or []
        self.notes = notes

    def to_dict(self) -> dict:
        return {"status": self.status, "actions": self.actions, "notes": self.notes}


class SkillsEngine:
    def __init__(self, box_root: Path, timeout_sec: int = 5, domain: str = ""):
        self.box_root = box_root
        self.timeout_sec = timeout_sec
        self.domain = domain
        self._manifest: dict = {}
        self._load_manifest()

    def _load_manifest(self) -> None:
        manifest_path = self.box_root / "skills" / "manifest.toml"
        if manifest_path.exists():
            self._manifest = toml.load(manifest_path)
        else:
            self._manifest = {"skills": {"version": 1, "on_receive": [], "on_send": [], "on_bounce": []}}

    def get_manifest(self) -> dict:
        return self._manifest

    def run_on_send(self, message: Message) -> list[SkillResult]:
        hooks = self._manifest.get("skills", {}).get("on_send", [])
        return self._run_hooks(hooks, message, "on_send")

    def run_on_receive(self, message: Message, message_path: Path) -> list[SkillResult]:
        hooks = self._manifest.get("skills", {}).get("on_receive", [])
        return self._run_hooks(hooks, message, "on_receive", message_path=message_path)

    def run_on_bounce(self, message: Message) -> list[SkillResult]:
        hooks = self._manifest.get("skills", {}).get("on_bounce", [])
        return self._run_hooks(hooks, message, "on_bounce")

    def _run_hooks(
        self, hooks: list[str], message: Message, phase: str, message_path: Optional[Path] = None
    ) -> list[SkillResult]:
        results = []
        for hook_name in hooks:
            try:
                result = self._execute_hook(hook_name, message, phase, message_path)
                results.append(result)
            except Exception as e:
                results.append(SkillResult(status="error", notes=f"{hook_name}: {e}"))
                self._log_skill_result(message.message_id, hook_name, "error", str(e))
        return results

    def _execute_hook(
        self, hook_name: str, message: Message, phase: str, message_path: Optional[Path] = None
    ) -> SkillResult:
        if hook_name.startswith("builtin."):
            return self._run_builtin(hook_name, message, phase, message_path)

        # Local executable skill
        phase_dir = {"on_receive": "on_receive", "on_send": "on_send", "on_bounce": "on_bounce"}.get(phase, phase)
        skill_path = self.box_root / "skills" / phase_dir / hook_name.replace(".", "/")
        if skill_path.is_file() and os.access(skill_path, os.X_OK):
            return self._run_executable(skill_path, message, message_path)

        self._log_skill_result(message.message_id, hook_name, "skipped", "hook not found")
        return SkillResult(status="skipped", notes=f"Hook '{hook_name}' not found")

    def _run_builtin(
        self, name: str, message: Message, phase: str, message_path: Optional[Path] = None
    ) -> SkillResult:
        builtin_name = name.replace("builtin.", "")

        if builtin_name == "validate_headers":
            from app.message.protocol import validate_headers
            errors = validate_headers(message, message.from_addr, self.domain)
            if errors:
                return SkillResult(status="error", notes="; ".join(errors))
            return SkillResult(status="ok", notes="Headers valid")

        elif builtin_name == "classify":
            index_line = json.dumps({
                "message_id": message.message_id,
                "type": message.type,
                "priority": message.priority,
                "labels": message.labels,
                "from": message.from_addr,
                "subject": message.subject,
                "date": message.date,
            })
            episodic_dir = self.box_root / "memory" / "episodic"
            episodic_dir.mkdir(parents=True, exist_ok=True)
            index_file = episodic_dir / "inbox-index.jsonl"
            with open(index_file, "a") as f:
                f.write(index_line + "\n")
            return SkillResult(status="ok", actions=[{"op": "indexed", "path": str(index_file)}])

        elif builtin_name == "save_attachments":
            if not message.attachments:
                return SkillResult(status="ok", notes="No attachments")
            actions = []
            for att in message.attachments:
                att_dir = self.box_root / "data" / "inbound" / message.message_id.strip("<>")
                att_dir.mkdir(parents=True, exist_ok=True)
                if message_path and att.path:
                    src = message_path.parent / att.path
                    if src.is_file() and is_path_within(src, self.box_root):
                        dst = att_dir / att.name
                        shutil.copy2(str(src), str(dst))
                        actions.append({"op": "saved", "path": str(dst), "name": att.name})
            return SkillResult(status="ok", actions=actions)

        elif builtin_name == "file_bounce":
            bounce_dir = self.box_root / "data" / "bounced"
            bounce_dir.mkdir(parents=True, exist_ok=True)
            bounce_file = bounce_dir / f"{message.message_id.strip('<>')}.md"
            with open(bounce_file, "w") as f:
                f.write(message.serialize())
            semantic_dir = self.box_root / "memory" / "semantic"
            semantic_dir.mkdir(parents=True, exist_ok=True)
            bounce_log = semantic_dir / "bounces.jsonl"
            with open(bounce_log, "a") as f:
                f.write(json.dumps({"message_id": message.message_id, "date": message.date}) + "\n")
            return SkillResult(status="ok", actions=[{"op": "filed_bounce", "path": str(bounce_file)}])

        elif builtin_name == "receipt_index":
            if message.type == "receipt" and message.receipt_for:
                semantic_dir = self.box_root / "memory" / "semantic"
                semantic_dir.mkdir(parents=True, exist_ok=True)
                status_file = semantic_dir / "outbox-status.json"
                statuses = {}
                if status_file.exists():
                    with open(status_file) as f:
                        statuses = json.load(f)
                statuses[message.receipt_for] = {
                    "status": message.receipt_status,
                    "reason": message.receipt_reason,
                    "delivered_to": message.delivered_to,
                    "failed_to": message.failed_to,
                    "receipt_date": message.date,
                }
                with open(status_file, "w") as f:
                    json.dump(statuses, f, indent=2, ensure_ascii=False)
                return SkillResult(status="ok", actions=[{"op": "updated_status"}])
            return SkillResult(status="ok", notes="Not a receipt")

        return SkillResult(status="skipped", notes=f"Unknown builtin: {name}")

    def _run_executable(self, skill_path: Path, message: Message, message_path: Optional[Path] = None) -> SkillResult:
        input_data = json.dumps({
            "message_path": str(message_path) if message_path else "",
            "headers": message.to_summary(),
        })
        try:
            result = subprocess.run(
                [str(skill_path)],
                input=input_data,
                capture_output=True,
                text=True,
                timeout=self.timeout_sec,
                cwd=str(self.box_root),
                env={"PATH": os.environ.get("PATH", "/usr/bin"), "AGENTPOST_BOX_ROOT": str(self.box_root)},
            )
            if result.returncode != 0:
                return SkillResult(status="error", notes=f"Exit {result.returncode}: {result.stderr[:200]}")
            output = json.loads(result.stdout)
            return SkillResult(
                status=output.get("status", "ok"),
                actions=output.get("actions", []),
                notes=output.get("notes", ""),
            )
        except subprocess.TimeoutExpired:
            return SkillResult(status="error", notes=f"Timeout after {self.timeout_sec}s")
        except json.JSONDecodeError:
            return SkillResult(status="error", notes="Invalid JSON output from skill")

    def _log_skill_result(self, message_id: str, skill_name: str, status: str, notes: str) -> None:
        log_dir = self.box_root / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / "skills.log"
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "message_id": message_id,
            "skill": skill_name,
            "status": status,
            "notes": notes,
        }
        with open(log_file, "a") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
