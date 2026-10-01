"""Reference Agent Worker - a simple scanning loop that processes inbox messages."""
from __future__ import annotations

import json
import os
import signal
import sys
import time
from pathlib import Path

from app.sdk.client import BoxClient


class ReferenceWorker:
    """A reference agent worker that scans inbox and auto-replies."""

    def __init__(self, api_base: str, token: str, box_id: str, scan_interval: int = 15):
        self.client = BoxClient(api_base, token, box_id)
        self.box_id = box_id
        self.scan_interval = scan_interval
        self._running = True
        self._seen: set[str] = set()

    def start(self) -> None:
        print(f"[worker:{self.box_id}] Starting scan loop (interval={self.scan_interval}s)")
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        while self._running:
            try:
                self._scan_once()
            except Exception as e:
                print(f"[worker:{self.box_id}] Scan error: {e}")
            time.sleep(self.scan_interval)

    def _handle_signal(self, signum, frame):
        print(f"[worker:{self.box_id}] Received signal {signum}, stopping...")
        self._running = False

    def _scan_once(self) -> None:
        messages = self.client.list_inbox(folder="new")
        for msg in messages:
            msg_id = msg.get("message_id", "")
            if msg_id in self._seen:
                continue
            self._seen.add(msg_id)

            msg_type = msg.get("type", "")
            if msg_type == "receipt":
                print(f"[worker:{self.box_id}] Got receipt for {msg.get('in_reply_to', '?')}")
                self.client.ack_message(msg_id)
                continue

            if msg_type == "system":
                print(f"[worker:{self.box_id}] Got system message: {msg.get('subject', '')}")
                self.client.ack_message(msg_id)
                continue

            print(f"[worker:{self.box_id}] Processing: {msg.get('subject', '')} from {msg.get('from', '?')}")
            self._handle_message(msg)
            self.client.ack_message(msg_id)

    def _handle_message(self, msg: dict) -> None:
        """Handle an incoming message - auto-reply with acknowledgment."""
        msg_type = msg.get("type", "request")
        subject = msg.get("subject", "")
        from_addr = msg.get("from", "")

        if msg_type == "request":
            reply_body = f"Received your request: {subject}\n\nI'll process this and get back to you."
            reply_type = "reply"
        elif msg_type == "reply":
            reply_body = f"Thanks for your reply regarding: {subject}"
            reply_type = "reply"
        else:
            reply_body = f"Acknowledged: {subject}"
            reply_type = "reply"

        try:
            result = self.client.compose(
                to=[from_addr],
                subject=f"Re: {subject}",
                body=reply_body,
                type=reply_type,
                thread_id=msg.get("thread_id", ""),
                in_reply_to=msg.get("message_id", ""),
                ack=True,
            )
            print(f"[worker:{self.box_id}] Replied: {result.get('message_id', '')}")
        except Exception as e:
            print(f"[worker:{self.box_id}] Reply failed: {e}")


def main():
    api_base = os.environ.get("AGENTPOST_API", "http://localhost:8765")
    token = os.environ.get("AGENTPOST_TOKEN", "")
    box_id = os.environ.get("AGENTPOST_BOX_ID", "")
    scan_interval = int(os.environ.get("AGENTPOST_SCAN_INTERVAL", "15"))

    if not token:
        print("Error: AGENTPOST_TOKEN environment variable required", file=sys.stderr)
        sys.exit(1)
    if not box_id:
        print("Error: AGENTPOST_BOX_ID environment variable required", file=sys.stderr)
        sys.exit(1)

    worker = ReferenceWorker(api_base, token, box_id, scan_interval)
    worker.start()


if __name__ == "__main__":
    main()
