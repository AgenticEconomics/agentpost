"""Daemon engine - the core delivery pipeline for AgentPost."""
from __future__ import annotations

import asyncio
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.boxfs.paths import atomic_write, box_path, is_path_within, list_messages, safe_rename
from app.events.bus import EventBus, Event
from app.message.protocol import (
    Message,
    create_receipt,
    generate_filename,
    generate_message_id,
    parse_message,
    validate_headers,
)
from app.registry.models import Registry
from app.router.resolver import Router
from app.skills.engine import SkillsEngine
from app.audit.logger import AuditLogger, BoxLogger


class DeliveryEngine:
    """The core message delivery engine - watches outboxes and delivers messages."""

    def __init__(
        self,
        root: Path,
        registry: Registry,
        router: Router,
        events: EventBus,
        audit: AuditLogger,
        domain: str = "agentpost.local",
        watch_interval_ms: int = 500,
        max_attachment_bytes: int = 10_485_760,
    ):
        self.root = root
        self.registry = registry
        self.router = router
        self.events = events
        self.audit = audit
        self.domain = domain
        self.watch_interval_ms = watch_interval_ms
        self.max_attachment_bytes = max_attachment_bytes
        self._running = False
        self._stats = {
            "messages_delivered": 0,
            "messages_rejected": 0,
            "messages_bounced": 0,
            "skills_run": 0,
        }
        self.start_time = time.time()

    @property
    def stats(self) -> dict:
        return {**self._stats, "uptime_sec": int(time.time() - self.start_time)}

    async def start(self) -> None:
        self._running = True
        asyncio.create_task(self._watch_loop())
        asyncio.create_task(self._retry_loop())

    async def stop(self) -> None:
        self._running = False

    async def _watch_loop(self) -> None:
        """Periodically scan all outbox/new/ directories for new messages."""
        while self._running:
            try:
                await self._scan_outboxes()
            except Exception as e:
                self.audit.log("watcher_error", error=str(e))
            await asyncio.sleep(self.watch_interval_ms / 1000.0)

    async def _retry_loop(self) -> None:
        """Retry messages in spool/retry/."""
        while self._running:
            try:
                await self._process_retry()
            except Exception:
                pass
            await asyncio.sleep(10)

    async def _scan_outboxes(self) -> None:
        boxes_dir = self.root / "boxes"
        if not boxes_dir.is_dir():
            return
        for box_dir in boxes_dir.iterdir():
            if not box_dir.is_dir():
                continue
            local_part = box_dir.name
            outbox_new = box_dir / "outbox" / "new"
            if not outbox_new.is_dir():
                continue
            entry = self.registry.get(local_part)
            if not entry or entry.get("status") != "active":
                continue
            for msg_file in sorted(outbox_new.iterdir()):
                if not msg_file.is_file():
                    continue
                if msg_file.name.startswith("."):
                    continue
                await self._process_outbox_message(local_part, msg_file)

    async def _process_outbox_message(self, local_part: str, msg_file: Path) -> None:
        box_root = self.root / "boxes" / local_part
        box_address = f"{local_part}@{self.domain}"
        box_logger = BoxLogger(box_root)

        try:
            content = msg_file.read_text(encoding="utf-8")
        except Exception as e:
            self.audit.log("read_error", box=local_part, error=str(e))
            safe_rename(msg_file, box_root / "outbox" / "failed")
            return

        # Parse
        try:
            message = parse_message(content)
        except ValueError as e:
            self.audit.log("parse_error", box=local_part, error=str(e))
            safe_rename(msg_file, box_root / "outbox" / "failed")
            self._send_reject_receipt(box_root, msg_file.name, str(e))
            self._stats["messages_rejected"] += 1
            box_logger.log(f"REJECTED: {msg_file.name} - {e}")
            return

        # Auth: from must match box address
        if message.from_addr != box_address:
            reason = f"from ({message.from_addr}) does not match box ({box_address})"
            self.audit.log("auth_fail", box=local_part, message_id=message.message_id, reason=reason)
            safe_rename(msg_file, box_root / "outbox" / "failed")
            self._send_reject_receipt_message(box_root, message, reason)
            self._stats["messages_rejected"] += 1
            self.events.emit("mail.rejected", {"message_id": message.message_id, "box": local_part, "reason": reason})
            box_logger.log(f"AUTH_FAIL: {message.message_id} - {reason}")
            return

        # Validate headers
        errors = validate_headers(message, box_address, self.domain)
        if errors:
            reason = "; ".join(errors)
            safe_rename(msg_file, box_root / "outbox" / "failed")
            self._send_reject_receipt_message(box_root, message, reason)
            self._stats["messages_rejected"] += 1
            self.events.emit("mail.rejected", {"message_id": message.message_id, "box": local_part, "reason": reason})
            box_logger.log(f"VALIDATION_FAIL: {message.message_id} - {reason}")
            return

        # Validate attachment paths
        for att in message.attachments:
            att_path = msg_file.parent / att.path
            if att.path.startswith("/") or ".." in att.path.split("/"):
                reason = f"Attachment path not allowed: {att.path}"
                safe_rename(msg_file, box_root / "outbox" / "failed")
                self._send_reject_receipt_message(box_root, message, reason)
                self._stats["messages_rejected"] += 1
                return
            if att_path.is_file():
                size = att_path.stat().st_size
                if size > self.max_attachment_bytes:
                    reason = f"Attachment too large: {att.name} ({size} bytes)"
                    safe_rename(msg_file, box_root / "outbox" / "failed")
                    self._send_reject_receipt_message(box_root, message, reason)
                    self._stats["messages_rejected"] += 1
                    return

        # Run on_send skills
        skills_engine = SkillsEngine(box_root)
        send_results = skills_engine.run_on_send(message)
        self._stats["skills_run"] += len(send_results)
        for r in send_results:
            if r.status == "error":
                reason = f"on_send skill failed: {r.notes}"
                safe_rename(msg_file, box_root / "outbox" / "failed")
                self._send_reject_receipt_message(box_root, message, reason)
                self._stats["messages_rejected"] += 1
                self.events.emit("skills.failed", {"box": local_part, "message_id": message.message_id, "reason": reason})
                box_logger.log(f"SKILL_FAIL: {message.message_id} - {reason}")
                return

        # Deliver to each recipient
        delivered_to = []
        failed_to = []
        all_recipients = message.to + message.cc + message.bcc

        for recipient in all_recipients:
            is_bcc = recipient in message.bcc
            result = await self._deliver_to_recipient(
                message, msg_file, recipient, local_part, is_bcc
            )
            if result:
                delivered_to.append(recipient)
            else:
                failed_to.append(recipient)

        # Move source to sent
        sent_dir = box_root / "outbox" / "sent"
        sent_dir.mkdir(parents=True, exist_ok=True)
        safe_rename(msg_file, sent_dir)

        # Send receipt if ack requested
        if message.routing.ack and (delivered_to or failed_to):
            status = "delivered" if not failed_to else ("bounced" if not delivered_to else "delivered")
            receipt = create_receipt(
                message, status,
                delivered_to=delivered_to,
                failed_to=failed_to,
                domain=self.domain,
            )
            receipt_content = receipt.serialize()
            receipt_filename = generate_filename("postmaster")
            atomic_write(box_root / "inbox" / "new", receipt_filename, receipt_content)
            self.events.emit("mail.inbox_new", {
                "box": local_part,
                "message_id": receipt.message_id,
                "type": "receipt",
            })

        self._stats["messages_delivered"] += 1
        self.audit.log(
            "deliver",
            message_id=message.message_id,
            box=local_part,
            delivered_to=delivered_to,
            failed_to=failed_to,
        )
        self.events.emit("mail.delivered", {
            "message_id": message.message_id,
            "from": local_part,
            "delivered_to": delivered_to,
            "failed_to": failed_to,
        })
        box_logger.log(f"DELIVERED: {message.message_id} -> {delivered_to}")

    async def _deliver_to_recipient(
        self, message: Message, src_file: Path, recipient: str, sender_local: str, is_bcc: bool
    ) -> bool:
        recipient_local = self.router.resolve(recipient)
        if not recipient_local:
            self.audit.log("unknown_recipient", message_id=message.message_id, recipient=recipient)
            self._stats["messages_bounced"] += 1
            return False

        entry = self.registry.get(recipient_local)
        if not entry or entry.get("status") != "active":
            self.audit.log("inactive_recipient", message_id=message.message_id, recipient=recipient)
            return False

        recipient_box = self.root / "boxes" / recipient_local

        # Prepare the message copy for the recipient
        msg_copy = Message(
            protocol=message.protocol,
            message_id=message.message_id,
            from_addr=message.from_addr,
            to=[r for r in message.to if r not in message.bcc] if is_bcc else message.to,
            cc=message.cc,
            bcc=[],  # Strip BCC for recipients
            subject=message.subject,
            date=message.date,
            type=message.type,
            priority=message.priority,
            in_reply_to=message.in_reply_to,
            references=message.references,
            thread_id=message.thread_id,
            expires_at=message.expires_at,
            payload_format=message.payload_format,
            attachments=list(message.attachments),
            routing=message.routing,
            labels=message.labels,
            body=message.body,
        )

        # Copy attachments to recipient's data/inbound/
        if message.attachments:
            inbound_dir = recipient_box / "data" / "inbound" / message.message_id.strip("<>")
            inbound_dir.mkdir(parents=True, exist_ok=True)
            sender_box = self.root / "boxes" / sender_local
            new_attachments = []
            for att in message.attachments:
                src_att = src_file.parent / att.path
                if src_att.is_file():
                    dst_att = inbound_dir / att.name
                    shutil.copy2(str(src_att), str(dst_att))
                    rel_path = f"../../data/inbound/{message.message_id.strip('<>')}/{att.name}"
                    new_attachments.append(type(att)(
                        name=att.name,
                        path=rel_path,
                        sha256=att.sha256,
                        media_type=att.media_type,
                    ))
                else:
                    new_attachments.append(att)
            msg_copy.attachments = new_attachments

        # Write to recipient's inbox
        content = msg_copy.serialize()
        filename = generate_filename(sender_local)

        # Atomic write: tmp -> new
        inbox_tmp = recipient_box / "inbox" / "tmp"
        inbox_new = recipient_box / "inbox" / "new"
        inbox_tmp.mkdir(parents=True, exist_ok=True)
        inbox_new.mkdir(parents=True, exist_ok=True)

        tmp_file = inbox_tmp / f".tmp.{int(time.time()*1000)}.{filename}"
        tmp_file.write_text(content, encoding="utf-8")
        final_file = inbox_new / filename
        os.replace(str(tmp_file), str(final_file))

        self.audit.log("inbox_write", message_id=message.message_id, box=recipient_local)

        # Run on_receive skills
        try:
            await self._run_receive_skills(recipient_local, recipient_box, msg_copy, final_file)
        except Exception as e:
            self.audit.log("skills_error", box=recipient_local, error=str(e))
            # Leave in inbox/new, mark as needs_agent
            return True

        self.events.emit("mail.inbox_new", {
            "box": recipient_local,
            "message_id": message.message_id,
            "from": message.from_addr,
            "subject": message.subject,
        })
        return True

    async def _run_receive_skills(
        self, recipient_local: str, recipient_box: Path, message: Message, message_path: Path
    ) -> None:
        """Run on_receive skills but leave message in inbox/new for agent discovery.

        Skills still process the message (classify, save attachments, index, etc.)
        but the file stays in inbox/new. Only an explicit ack by the agent moves
        it to inbox/cur. This ensures agents polling folder=new can always see
        newly delivered messages.
        """
        skills_engine = SkillsEngine(recipient_box)
        results = skills_engine.run_on_receive(message, message_path)
        self._stats["skills_run"] += len(results)

        all_ok = all(r.status in ("ok", "skipped") for r in results)

        if all_ok:
            self.events.emit("skills.finished", {"box": recipient_local, "message_id": message.message_id})
        else:
            errors = [r.notes for r in results if r.status == "error"]
            self.events.emit("skills.failed", {
                "box": recipient_local,
                "message_id": message.message_id,
                "errors": errors,
            })

        BoxLogger(recipient_box).log(
            f"RECEIVED: {message.message_id} from {message.from_addr} skills={[r.to_dict() for r in results]}"
        )

    def _send_reject_receipt(self, box_root: Path, filename: str, reason: str) -> None:
        """Send a simple rejection receipt when we can't parse the message."""
        receipt = Message(
            protocol="agentpost/1",
            message_id=generate_message_id("postmaster", self.domain),
            from_addr=f"postmaster@{self.domain}",
            to=["unknown@agentpost.local"],
            subject=f"Rejected: {filename}",
            date=datetime.now(timezone.utc).isoformat(),
            type="receipt",
            receipt_status="rejected",
            receipt_reason=reason,
            body=f"Your message was rejected: {reason}",
        )
        atomic_write(
            box_root / "inbox" / "new",
            generate_filename("postmaster"),
            receipt.serialize(),
        )

    def _send_reject_receipt_message(self, box_root: Path, original: Message, reason: str) -> None:
        """Send a rejection receipt for a parseable message."""
        receipt = create_receipt(original, "rejected", reason=reason, domain=self.domain)
        atomic_write(
            box_root / "inbox" / "new",
            generate_filename("postmaster"),
            receipt.serialize(),
        )

    async def _process_retry(self) -> None:
        """Process messages in spool/retry/."""
        retry_dir = self.root / "spool" / "retry"
        if not retry_dir.is_dir():
            return
        for f in sorted(retry_dir.iterdir()):
            if f.is_file():
                # Move to dead-letter after retries
                dead = self.root / "spool" / "dead-letter"
                dead.mkdir(parents=True, exist_ok=True)
                safe_rename(f, dead)

    def get_queue_depth(self) -> dict:
        """Get current queue depths."""
        depths = {"incoming": 0, "retry": 0, "dead_letter": 0}
        for name, subdir in [("incoming", "incoming"), ("retry", "retry"), ("dead_letter", "dead-letter")]:
            d = self.root / "spool" / subdir
            if d.is_dir():
                depths[name] = len(list(d.iterdir()))
        return depths

    def doctor(self, repair: bool = False) -> list[dict]:
        """Run system-wide integrity checks."""
        from app.boxfs.paths import doctor_box, repair_box, SYSTEM_DIRS

        issues = []
        # Check system dirs
        for d in SYSTEM_DIRS:
            p = self.root / d
            if not p.exists():
                issues.append({"path": str(d), "issue": "missing_system_directory", "repairable": True})
                if repair:
                    p.mkdir(parents=True, exist_ok=True)

        # Check each box
        boxes_dir = self.root / "boxes"
        if boxes_dir.is_dir():
            for box_dir in boxes_dir.iterdir():
                if box_dir.is_dir():
                    box_issues = doctor_box(box_dir)
                    for issue in box_issues:
                        issue["box"] = box_dir.name
                        issue["path"] = f"boxes/{box_dir.name}/{issue['path']}"
                    issues.extend(box_issues)
                    if repair:
                        repaired = repair_box(box_dir)
                        for r in repaired:
                            issues.append({"path": f"boxes/{box_dir.name}", "issue": f"repaired: {r}", "repairable": False})

        # Check stale tmp files in spool
        for subdir in ["incoming", "retry"]:
            spool_sub = self.root / "spool" / subdir
            if spool_sub.is_dir():
                for f in spool_sub.iterdir():
                    if f.name.startswith(".tmp."):
                        issues.append({"path": f"spool/{subdir}/{f.name}", "issue": "stale_spool_file", "repairable": True})
                        if repair:
                            f.unlink()

        return issues

    def dead_letter_list(self) -> list[dict]:
        dl_dir = self.root / "spool" / "dead-letter"
        if not dl_dir.is_dir():
            return []
        items = []
        for f in sorted(dl_dir.iterdir()):
            if f.is_file():
                items.append({"id": f.stem, "filename": f.name, "size": f.stat().st_size, "date": datetime.fromtimestamp(f.stat().st_mtime).isoformat()})
        return items

    def dead_letter_retry(self, item_id: str) -> bool:
        dl_dir = self.root / "spool" / "dead-letter"
        target = dl_dir / item_id
        if not target.exists():
            # Try finding by stem
            for f in dl_dir.iterdir():
                if f.stem == item_id:
                    target = f
                    break
            else:
                return False
        retry_dir = self.root / "spool" / "retry"
        retry_dir.mkdir(parents=True, exist_ok=True)
        safe_rename(target, retry_dir)
        return True

    def dead_letter_drop(self, item_id: str) -> bool:
        dl_dir = self.root / "spool" / "dead-letter"
        for f in dl_dir.iterdir():
            if f.stem == item_id or f.name == item_id:
                f.unlink()
                return True
        return False
