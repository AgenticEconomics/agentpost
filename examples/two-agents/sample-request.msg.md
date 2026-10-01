---
protocol: agentpost/1
message_id: "<20260929.1000000000000.alice@agentpost.local>"
from: "alice@agentpost.local"
to:
  - "bob@agentpost.local"
subject: "请核对 API 错误码表"
date: "2026-09-29T10:00:00Z"
type: request
priority: normal
thread_id: "thr-api-errcode"
payload_format: markdown
routing:
  notify: true
  ack: true
labels:
  - "api"
  - "docs"
---

Hi Bob,

我在整理 API 错误码文档时发现了几个不一致的地方：

1. `ERR_4001` 在后端返回的是 "invalid_token"，但文档写的是 "auth_failed"
2. `ERR_5003` 的描述缺少中文翻译

请帮忙核对一下，谢谢！
