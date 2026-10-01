"""Message protocol - parsing and validation of agentpost/1 messages."""
from __future__ import annotations

import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import yaml


REQUIRED_HEADERS = {"protocol", "message_id", "from", "to", "subject", "date", "type"}
VALID_TYPES = {"request", "reply", "event", "receipt", "artifact", "system"}
VALID_PRIORITIES = {"low", "normal", "high"}
VALID_PAYLOAD_FORMATS = {"markdown", "json", "text"}

MSG_ID_RE = re.compile(r"^<[^>]+>$")
LOCAL_PART_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{1,62}$")
RESERVED_NAMES = {"system", "postmaster", "agentpost", "all", "broadcast"}


@dataclass
class Attachment:
    name: str
    path: str
    sha256: str = ""
    media_type: str = "application/octet-stream"


@dataclass
class Routing:
    notify: bool = True
    ack: bool = False


@dataclass
class Message:
    protocol: str = "agentpost/1"
    message_id: str = ""
    from_addr: str = ""
    to: list[str] = field(default_factory=list)
    cc: list[str] = field(default_factory=list)
    bcc: list[str] = field(default_factory=list)
    subject: str = ""
    date: str = ""
    type: str = "request"
    priority: str = "normal"
    in_reply_to: Optional[str] = None
    references: list[str] = field(default_factory=list)
    thread_id: str = ""
    expires_at: Optional[str] = None
    payload_format: str = "markdown"
    attachments: list[Attachment] = field(default_factory=list)
    routing: Routing = field(default_factory=Routing)
    labels: list[str] = field(default_factory=list)
    body: str = ""
    # Receipt-specific fields
    receipt_for: Optional[str] = None
    receipt_status: Optional[str] = None
    receipt_reason: str = ""
    delivered_to: list[str] = field(default_factory=list)
    failed_to: list[str] = field(default_factory=list)

    def to_front_matter(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "protocol": self.protocol,
            "message_id": self.message_id,
            "from": self.from_addr,
            "to": self.to,
            "subject": self.subject,
            "date": self.date,
            "type": self.type,
            "priority": self.priority,
        }
        if self.cc:
            d["cc"] = self.cc
        if self.bcc:
            d["bcc"] = self.bcc
        if self.in_reply_to:
            d["in_reply_to"] = self.in_reply_to
        if self.references:
            d["references"] = self.references
        if self.thread_id:
            d["thread_id"] = self.thread_id
        if self.expires_at:
            d["expires_at"] = self.expires_at
        d["payload_format"] = self.payload_format
        if self.attachments:
            d["attachments"] = [
                {"name": a.name, "path": a.path, "sha256": a.sha256, "media_type": a.media_type}
                for a in self.attachments
            ]
        d["routing"] = {"notify": self.routing.notify, "ack": self.routing.ack}
        if self.labels:
            d["labels"] = self.labels
        if self.receipt_for:
            d["receipt_for"] = self.receipt_for
            d["status"] = self.receipt_status
            if self.receipt_reason:
                d["reason"] = self.receipt_reason
            if self.delivered_to:
                d["delivered_to"] = self.delivered_to
            if self.failed_to:
                d["failed_to"] = self.failed_to
        return d

    def serialize(self) -> str:
        fm = self.to_front_matter()
        yaml_str = yaml.dump(fm, default_flow_style=False, allow_unicode=True, sort_keys=False)
        return f"---\n{yaml_str}---\n\n{self.body}\n"

    def to_summary(self) -> dict[str, Any]:
        return {
            "message_id": self.message_id,
            "from": self.from_addr,
            "to": self.to,
            "subject": self.subject,
            "date": self.date,
            "type": self.type,
            "priority": self.priority,
            "labels": self.labels,
            "thread_id": self.thread_id,
            "has_attachments": len(self.attachments) > 0,
            "in_reply_to": self.in_reply_to,
        }


def parse_message(content: str) -> Message:
    """Parse a message from YAML front matter + body format."""
    content = content.strip()
    if not content.startswith("---"):
        raise ValueError("Message must start with YAML front matter delimiter '---'")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid message format: missing front matter delimiters")

    yaml_str = parts[1].strip()
    body = parts[2].strip()

    try:
        headers = yaml.safe_load(yaml_str) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in front matter: {e}")

    if not isinstance(headers, dict):
        raise ValueError("Front matter must be a YAML mapping")

    attachments_raw = headers.get("attachments", []) or []
    attachments = []
    for a in attachments_raw:
        if isinstance(a, dict):
            attachments.append(Attachment(
                name=a.get("name", ""),
                path=a.get("path", ""),
                sha256=a.get("sha256", ""),
                media_type=a.get("media_type", "application/octet-stream"),
            ))

    routing_raw = headers.get("routing", {}) or {}
    routing = Routing(
        notify=routing_raw.get("notify", True),
        ack=routing_raw.get("ack", False),
    )

    return Message(
        protocol=headers.get("protocol", "agentpost/1"),
        message_id=headers.get("message_id", ""),
        from_addr=headers.get("from", ""),
        to=headers.get("to", []) or [],
        cc=headers.get("cc", []) or [],
        bcc=headers.get("bcc", []) or [],
        subject=headers.get("subject", ""),
        date=headers.get("date", ""),
        type=headers.get("type", "request"),
        priority=headers.get("priority", "normal"),
        in_reply_to=headers.get("in_reply_to"),
        references=headers.get("references", []) or [],
        thread_id=headers.get("thread_id", ""),
        expires_at=headers.get("expires_at"),
        payload_format=headers.get("payload_format", "markdown"),
        attachments=attachments,
        routing=routing,
        labels=headers.get("labels", []) or [],
        body=body,
        receipt_for=headers.get("receipt_for"),
        receipt_status=headers.get("status"),
        receipt_reason=headers.get("reason", ""),
        delivered_to=headers.get("delivered_to", []) or [],
        failed_to=headers.get("failed_to", []) or [],
    )


def validate_headers(msg: Message, box_address: str, domain: str) -> list[str]:
    """Validate message headers. Returns list of error strings (empty = valid)."""
    errors = []
    if msg.protocol != "agentpost/1":
        errors.append(f"Invalid protocol: {msg.protocol}")
    if not msg.message_id:
        errors.append("Missing message_id")
    if not msg.from_addr:
        errors.append("Missing from")
    elif msg.from_addr != box_address:
        errors.append(f"from ({msg.from_addr}) does not match box address ({box_address})")
    if not msg.to:
        errors.append("Missing to (at least one recipient required)")
    if not msg.subject:
        errors.append("Missing subject")
    if not msg.date:
        errors.append("Missing date")
    if msg.type not in VALID_TYPES:
        errors.append(f"Invalid type: {msg.type}")
    if msg.priority not in VALID_PRIORITIES:
        errors.append(f"Invalid priority: {msg.priority}")
    for addr in msg.to + msg.cc + msg.bcc:
        local = addr.split("@")[0] if "@" in addr else addr
        if not LOCAL_PART_RE.match(local):
            errors.append(f"Invalid address format: {addr}")
    return errors


def generate_message_id(local_part: str, domain: str) -> str:
    ts = int(time.time() * 1000)
    rand = uuid.uuid4().hex[:8]
    return f"<{ts}.{rand}.{local_part}@{domain}>"


def generate_filename(local_part: str) -> str:
    ts = int(time.time() * 1000)
    rand = uuid.uuid4().hex[:4]
    return f"{ts}.{rand}.{local_part}.msg.md"


def create_receipt(
    original: Message,
    status: str,
    reason: str = "",
    delivered_to: list[str] | None = None,
    failed_to: list[str] | None = None,
    domain: str = "agentpost.local",
) -> Message:
    """Create a system receipt message."""
    return Message(
        protocol="agentpost/1",
        message_id=generate_message_id("postmaster", domain),
        from_addr=f"postmaster@{domain}",
        to=[original.from_addr],
        subject=f"Receipt: {status} - {original.subject}",
        date=datetime.now(timezone.utc).isoformat(),
        type="receipt",
        priority="normal",
        in_reply_to=original.message_id,
        thread_id=original.thread_id,
        receipt_for=original.message_id,
        receipt_status=status,
        receipt_reason=reason,
        delivered_to=delivered_to or [],
        failed_to=failed_to or [],
        body=f"Delivery receipt for message {original.message_id}\nStatus: {status}\n{reason}",
    )
