"""AgentPost SDK - client library for box agents and CLI."""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any, Optional

import httpx


class BoxClient:
    """SDK client for interacting with AgentPost API as a box agent."""

    def __init__(self, api_base: str, token: str, box_id: Optional[str] = None):
        self.api_base = api_base.rstrip("/")
        self.token = token
        self.box_id = box_id
        self._client = httpx.Client(
            base_url=self.api_base,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    def _url(self, path: str) -> str:
        return f"/api/v1{path}"

    def _box_url(self, path: str) -> str:
        bid = self.box_id
        if not bid:
            raise ValueError("box_id not set")
        return self._url(f"/boxes/{bid}{path}")

    # System
    def health(self) -> dict:
        return self._client.get(self._url("/health")).json()

    def version(self) -> dict:
        return self._client.get(self._url("/version")).json()

    # Address book
    def addrbook(self) -> list[dict]:
        return self._client.get(self._url("/addrbook")).json()

    # Inbox
    def list_inbox(self, folder: str = "new", limit: int = 50) -> list[dict]:
        resp = self._client.get(self._box_url(f"/inbox?folder={folder}&limit={limit}"))
        resp.raise_for_status()
        return resp.json()

    def read_message(self, message_id: str) -> dict:
        resp = self._client.get(self._box_url(f"/inbox/{message_id}"))
        resp.raise_for_status()
        return resp.json()

    def ack_message(self, message_id: str) -> dict:
        resp = self._client.post(self._box_url(f"/inbox/{message_id}/ack"))
        resp.raise_for_status()
        return resp.json()

    # Outbox
    def list_outbox(self, folder: str = "sent", limit: int = 50) -> list[dict]:
        resp = self._client.get(self._box_url(f"/outbox?folder={folder}&limit={limit}"))
        resp.raise_for_status()
        return resp.json()

    def compose(
        self,
        to: list[str],
        subject: str,
        body: str = "",
        type: str = "request",
        priority: str = "normal",
        thread_id: str = "",
        in_reply_to: Optional[str] = None,
        ack: bool = True,
        labels: list[str] | None = None,
        attachments: list[dict] | None = None,
    ) -> dict:
        payload = {
            "to": to,
            "subject": subject,
            "body": body,
            "type": type,
            "priority": priority,
            "thread_id": thread_id,
            "in_reply_to": in_reply_to,
            "ack": ack,
            "labels": labels or [],
            "attachments": attachments or [],
        }
        resp = self._client.post(self._box_url("/outbox"), json=payload)
        resp.raise_for_status()
        return resp.json()

    def reply(self, original: dict, body: str) -> dict:
        return self.compose(
            to=[original["from"]],
            subject=f"Re: {original['subject']}",
            body=body,
            type="reply",
            thread_id=original.get("thread_id", ""),
            in_reply_to=original.get("message_id", ""),
            ack=True,
        )

    # Files
    def list_files(self, path: str = "") -> list[dict]:
        resp = self._client.get(self._box_url(f"/files?path={path}"))
        resp.raise_for_status()
        return resp.json()

    def read_file(self, path: str) -> bytes:
        resp = self._client.get(self._box_url(f"/files/content?path={path}"))
        resp.raise_for_status()
        return resp.content

    def write_file(self, path: str, content: str | bytes) -> dict:
        data = content if isinstance(content, bytes) else content.encode()
        resp = self._client.put(self._box_url(f"/files/content?path={path}"), content=data)
        resp.raise_for_status()
        return resp.json()

    # Memory
    def get_memory(self) -> dict:
        resp = self._client.get(self._box_url("/memory"))
        resp.raise_for_status()
        return resp.json()

    # Skills
    def get_skills(self) -> dict:
        resp = self._client.get(self._box_url("/skills"))
        resp.raise_for_status()
        return resp.json()

    # Logs
    def get_logs(self) -> list[dict]:
        resp = self._client.get(self._box_url("/logs"))
        resp.raise_for_status()
        return resp.json()

    # Threads
    def get_thread(self, thread_id: str) -> list[dict]:
        resp = self._client.get(self._box_url(f"/threads/{thread_id}"))
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()


class OperatorClient:
    """SDK client for operator operations."""

    def __init__(self, api_base: str, token: str):
        self.api_base = api_base.rstrip("/")
        self.token = token
        self._client = httpx.Client(
            base_url=self.api_base,
            headers={"Authorization": f"Bearer {token}"},
            timeout=30.0,
        )

    def _url(self, path: str) -> str:
        return f"/api/v1{path}"

    def health(self) -> dict:
        return self._client.get(self._url("/health")).json()

    def metrics(self) -> dict:
        resp = self._client.get(self._url("/metrics"))
        resp.raise_for_status()
        return resp.json()

    def get_config(self) -> dict:
        resp = self._client.get(self._url("/config"))
        resp.raise_for_status()
        return resp.json()

    def doctor(self, repair: bool = False) -> dict:
        resp = self._client.post(self._url("/doctor"), json={"repair": repair})
        resp.raise_for_status()
        return resp.json()

    def register(
        self,
        id: str,
        display_name: str = "",
        summary: str = "",
        capabilities: list[str] | None = None,
        scan_interval_sec: int = 15,
    ) -> dict:
        payload = {
            "id": id,
            "display_name": display_name,
            "summary": summary,
            "capabilities": capabilities or [],
            "scan_interval_sec": scan_interval_sec,
        }
        resp = self._client.post(self._url("/boxes"), json=payload)
        resp.raise_for_status()
        return resp.json()

    def list_boxes(self) -> list[dict]:
        resp = self._client.get(self._url("/boxes"))
        resp.raise_for_status()
        return resp.json()

    def get_box(self, box_id: str) -> dict:
        resp = self._client.get(self._url(f"/boxes/{box_id}"))
        resp.raise_for_status()
        return resp.json()

    def pause_box(self, box_id: str) -> dict:
        resp = self._client.patch(self._url(f"/boxes/{box_id}"), json={"status": "paused"})
        resp.raise_for_status()
        return resp.json()

    def resume_box(self, box_id: str) -> dict:
        resp = self._client.patch(self._url(f"/boxes/{box_id}"), json={"status": "active"})
        resp.raise_for_status()
        return resp.json()

    def revoke_box(self, box_id: str) -> dict:
        resp = self._client.post(self._url(f"/boxes/{box_id}/revoke"))
        resp.raise_for_status()
        return resp.json()

    def rotate_token(self, box_id: str) -> dict:
        resp = self._client.post(self._url(f"/boxes/{box_id}/token/rotate"))
        resp.raise_for_status()
        return resp.json()

    def compose_as(self, box_id: str, **kwargs) -> dict:
        """Compose a message on behalf of a box (operator act-as)."""
        payload = kwargs
        resp = self._client.post(
            self._url(f"/boxes/{box_id}/outbox"),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    def get_spool(self) -> dict:
        resp = self._client.get(self._url("/spool"))
        resp.raise_for_status()
        return resp.json()

    def retry_dead_letter(self, item_id: str) -> dict:
        resp = self._client.post(self._url(f"/spool/dead-letter/{item_id}/retry"))
        resp.raise_for_status()
        return resp.json()

    def drop_dead_letter(self, item_id: str) -> dict:
        resp = self._client.post(self._url(f"/spool/dead-letter/{item_id}/drop"))
        resp.raise_for_status()
        return resp.json()

    def addrbook(self) -> list[dict]:
        resp = self._client.get(self._url("/addrbook"))
        resp.raise_for_status()
        return resp.json()

    def get_box_inbox(self, box_id: str, folder: str = "new", limit: int = 50) -> list[dict]:
        resp = self._client.get(self._url(f"/boxes/{box_id}/inbox?folder={folder}&limit={limit}"))
        resp.raise_for_status()
        return resp.json()

    def get_box_outbox(self, box_id: str, folder: str = "sent", limit: int = 50) -> list[dict]:
        resp = self._client.get(self._url(f"/boxes/{box_id}/outbox?folder={folder}&limit={limit}"))
        resp.raise_for_status()
        return resp.json()

    def close(self) -> None:
        self._client.close()
