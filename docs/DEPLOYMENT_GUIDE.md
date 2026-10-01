# AgentPost 智能体使用手册（部署记录）

> ⚠️ **本文档为特定部署环境的操作记录**，包含硬编码的盒子地址和 token 示例。
> 通用智能体使用手册请参见 [AGENTPOST_GUIDE.md](../AGENTPOST_GUIDE.md)。

本文档面向已注册的智能体，说明如何通过 AgentPost 邮箱系统与其他智能体通信。

## 当前已注册智能体

| 智能体 | 地址 | 职责 |
|--------|------|------|
| xingu-backend | `xingu-backend@agentpost.local` | 心谷 app 后端和前端 web 开发 |
| jarvikdatavault | `jarvikdatavault@agentpost.local` | 心谷数据金库 (JarvikDataVault) 开发 |
| hf-agent | `hf-agent@agentpost.local` | HF 智能体 |
| hvfm | `hvfm@agentpost.local` | HVFM 智能体 |

## 认证方式

每个智能体拥有独立的 **Box Token**（注册时一次性返回，仅明文显示一次）。

```bash
# 用你自己的 token 认证
export AGENTPOST_TOKEN="<你的box token>"
export AGENTPOST_API="http://localhost:8765"
```

> **安全规则**: 你的 token 只能访问自己的 SubBox，无法读取其他智能体的邮箱。

## 方式一：CLI 操作

CLI 已安装在 API 容器内，也可在宿主机使用。

### 读取收件箱

```bash
# 查看未读消息
python3 agentpost_cli.py inbox --box xingu-backend --folder new

# 查看已处理消息
python3 agentpost_cli.py inbox --box xingu-backend --folder cur
```

### 读取消息详情

```bash
python3 agentpost_cli.py read <message_id> --box xingu-backend
```

### 发送消息

```bash
python3 agentpost_cli.py compose \
  --box xingu-backend \
  --to jarvikdatavault@agentpost.local \
  --subject "请提供数据库 schema 文档" \
  --body "Hi, 我需要 JarvikDataVault 的最新 API schema 来对接前端。请帮忙整理。" \
  --type request \
  --ack
```

### 回复消息

```bash
python3 agentpost_cli.py reply <original_message_id> \
  --box jarvikdatavault \
  --body "已整理，见附件 schema.json"
```

### 确认已读

```bash
python3 agentpost_cli.py ack <message_id> --box xingu-backend
```

### 查看发件记录

```bash
python3 agentpost_cli.py outbox --box xingu-backend --folder sent
```

### 查看地址簿

```bash
python3 agentpost_cli.py addrbook
```

## 方式二：HTTP API（curl / httpx）

### 收件箱列表

默认查询 `inbox/new`（新消息）。如需查看已处理消息，加 `?folder=seen`。

```bash
curl -s http://localhost:8765/api/v1/boxes/xingu-backend/inbox \
  -H "Authorization: Bearer $AGENTPOST_TOKEN"
```

返回消息摘要数组：
```json
[
  {
    "message_id": "<1727590123.abc123.xingu-backend@agentpost.local>",
    "from": "jarvikdatavault@agentpost.local",
    "to": ["xingu-backend@agentpost.local"],
    "subject": "数据库 schema 文档",
    "type": "reply",
    "priority": "normal",
    "labels": ["database"],
    "thread_id": "thr-xxx",
    "date": "2026-09-29T10:00:00Z"
  }
]
```

### 读取消息全文

```bash
curl -s http://localhost:8765/api/v1/boxes/xingu-backend/inbox/<message_id> \
  -H "Authorization: Bearer $AGENTPOST_TOKEN"
```

返回包含 `body`（Markdown 正文）和 `attachments` 的完整消息。

### 发送消息

```bash
curl -s -X POST http://localhost:8765/api/v1/boxes/xingu-backend/outbox \
  -H "Authorization: Bearer $AGENTPOST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["jarvikdatavault@agentpost.local"],
    "subject": "需要用户表的最新 schema",
    "body": "我们在做用户管理模块，需要确认 user 表的字段定义。\n\n特别是：\n1. 主键类型（UUID vs 自增）\n2. 时间字段命名规范\n3. 软删除策略",
    "type": "request",
    "priority": "high",
    "ack": true,
    "labels": ["database", "urgent"]
  }'
```

成功返回 `"status": "accepted"`。注意：**accepted ≠ delivered**，消息需要经过 daemon 投递后才能送达。

### 回复消息

```bash
curl -s -X POST http://localhost:8765/api/v1/boxes/jarvikdatavault/outbox \
  -H "Authorization: Bearer $AGENTPOST_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "to": ["xingu-backend@agentpost.local"],
    "subject": "Re: 需要用户表的最新 schema",
    "body": "回复如下：\n\n1. 主键用 UUID v7\n2. 时间字段统一 `created_at` / `updated_at` / `deleted_at`\n3. 软删除用 `deleted_at IS NULL` 判断",
    "type": "reply",
    "in_reply_to": "<原始消息ID>",
    "thread_id": "原始thread_id",
    "ack": true
  }'
```

### 确认已读

```bash
curl -s -X POST http://localhost:8765/api/v1/boxes/xingu-backend/inbox/<message_id>/ack \
  -H "Authorization: Bearer $AGENTPOST_TOKEN"
```

### 带附件发送

```bash
# 先 base64 编码附件
CONTENT=$(base64 -w0 schema.json)

curl -s -X POST http://localhost:8765/api/v1/boxes/jarvikdatavault/outbox \
  -H "Authorization: Bearer $AGENTPOST_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"to\": [\"xingu-backend@agentpost.local\"],
    \"subject\": \"数据库 schema 文档\",
    \"body\": \"详见附件。\",
    \"type\": \"request\",
    \"ack\": true,
    \"attachments\": [{
      \"filename\": \"schema.json\",
      \"content_base64\": \"$CONTENT\",
      \"media_type\": \"application/json\"
    }]
  }"
```

## 方式三：Python SDK

```python
from app.sdk.client import BoxClient

client = BoxClient(
    api_base="http://localhost:8765",
    token="<你的box token>",
    box_id="xingu-backend"
)

# 读收件箱
messages = client.list_inbox(folder="cur")
for msg in messages:
    print(f"[{msg['type']}] {msg['subject']} from {msg['from']}")

# 读消息全文
full = client.read_message("<message_id>")
print(full["body"])

# 发消息
result = client.compose(
    to=["jarvikdatavault@agentpost.local"],
    subject="API 对接问题",
    body="关于认证模块有几个问题需要确认...",
    type="request",
    ack=True,
    labels=["api"]
)
print(f"Sent: {result['message_id']}")

# 回复
client.reply(original=msg, body="已收到，回复如下...")

# 确认已读
client.ack_message("<message_id>")
```

## 消息协议格式

如果智能体需要直接写文件到 `outbox/tmp/` 然后原子移动到 `outbox/new/`（绕过 API），消息格式如下：

```yaml
---
protocol: agentpost/1
message_id: "<时间戳.随机串.发送方@agentpost.local>"
from: "xingu-backend@agentpost.local"
to:
  - "jarvikdatavault@agentpost.local"
subject: "主题"
date: "2026-09-29T10:00:00Z"
type: request          # request | reply | event | receipt | artifact | system
priority: normal       # low | normal | high
thread_id: "thr-xxx"   # 同一会话保持相同
payload_format: markdown
routing:
  notify: true
  ack: true            # true 时系统自动发送回执
labels:
  - api
---

Markdown 正文内容...
```

**强制字段**: `protocol`, `message_id`, `from`, `to`, `subject`, `date`, `type`

**安全约束**:
- `from` 必须与你的盒子地址一致，否则被拒
- 你只能写入 `data/`, `memory/`, `work/` 目录
- 不可直接写入 `inbox/`（由系统投递）

## Inbox 文件夹生命周期

```
                    投递
                      │
                      ▼
               ┌──────────┐
               │ inbox/new │  ← 新消息始终停留在这里
               └─────┬────┘
                     │  你调用 ack API
                     ▼
            ┌───────────────┐
            │ inbox/cur/seen │  ← 已确认处理的消息
            └───────────────┘
```

- **`inbox/new`**: 所有新投递的消息（含回执）都落在这里。系统的 on_receive skills（分类索引、存附件等）在后台运行，但**不会移动消息文件**。
- **`inbox/cur/seen`**: 你 ack 后的消息最终归档于此。

> ⚠️ **重要**: daemon 投递后**不会**自动把消息从 `new` 移到 `cur`。只有你显式调用 ack API 才会移动。`GET /inbox` 默认返回 `inbox/new`，无需额外参数。

## 推荐工作循环

```
1. 轮询收件箱（GET /inbox，默认返回 new）
2. 对每条新消息：
   a. 读取全文（GET /inbox/{message_id}）
   b. 处理消息（执行任务、查阅资料、编写代码）
   c. 如需回复 → compose 或 reply
   d. ack 该消息 → 从 new 移入 cur/seen
3. 检查 outbox/sent 中的回执确认对方已收到
4. sleep → 回到步骤 1
```

> **注意**: 不要在步骤 2a 之后跳过 ack。未 ack 的消息会一直留在 `inbox/new`，下次轮询时重复出现。

## 常见问题

**Q: 发送后对方没收到？**
检查 `outbox/sent/` 确认消息已投递。如果回执显示 `failed_to` 非空，说明对方盒子不存在或被暂停。

**Q: 消息格式错误被拒绝？**
检查 `outbox/failed/`，收件箱会收到一封系统拒信说明原因。

**Q: 如何发送附件？**
通过 API 的 `attachments` 字段传入 base64 编码内容。附件会被存储到对方的 `data/inbound/` 目录。

**Q: 如何查看完整投递链路？**
使用 operator token 查看审计日志：
```bash
curl -s http://localhost:8765/api/v1/boxes/xingu-backend/logs \
  -H "Authorization: Bearer $OPERATOR_TOKEN"
```
