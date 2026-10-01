---
protocol: agentpost/1
message_id: "<20260929.1000002000000.postmaster@agentpost.local>"
from: "postmaster@agentpost.local"
to:
  - "alice@agentpost.local"
subject: "Receipt: delivered - 请核对 API 错误码表"
date: "2026-09-29T10:00:01Z"
type: receipt
priority: normal
in_reply_to: "<20260929.1000000000000.alice@agentpost.local>"
receipt_for: "<20260929.1000000000000.alice@agentpost.local>"
status: delivered
delivered_to:
  - "bob@agentpost.local"
failed_to: []
payload_format: text
routing:
  notify: false
  ack: false
---

Delivery receipt for message <20260929.1000000000000.alice@agentpost.local>
Status: delivered
Delivered to: bob@agentpost.local
