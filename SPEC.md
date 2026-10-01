# AgentPost 技术规格

## 协议版本

`agentpost/1`

## 目录规范

### 系统根目录

```
$AGENTPOST_ROOT/            # 默认 /var/lib/agentpost
  agentpost.yaml            # 系统配置
  registry/
    agents.jsonl           # 注册表
    revoked.json           # 吊销名单
  boxes/
    <local-part>/          # SubBox
  spool/
    incoming/
    retry/
    dead-letter/
  logs/
  run/
  addrbook/
    public.json
```

### SubBox 目录

地址格式: `<local-part>@agentpost.local`

```
boxes/<local-part>/
  AGENT.toml              # 身份描述
  inbox/
    new/                  # 刚投递
    cur/                  # 已预处理
    cur/seen/             # 已处理
    tmp/                  # 原子写暂存
  outbox/
    new/                  # 等待投递
    tmp/                  # 写入暂存
    sent/                 # 已发送
    failed/               # 失败
  reference/              # 只读参考
  data/                   # 数据存储
    inbound/              # 收到的附件
  scripts/                # 脚本
  memory/
    episodic/             # 事件记忆
    semantic/             # 结构化记忆
  skills/
    manifest.toml         # 技能清单
    on_receive/           # 入站钩子
    on_send/              # 出站钩子
    on_bounce/            # 退信钩子
  work/                   # 工作区
  logs/                   # 日志
```

## 消息格式

单文件消息，YAML front matter + Markdown 正文。

文件名: `<unix_ms>.<rand>.<local-part>.msg.md`

### 强制头

| 字段 | 说明 |
|------|------|
| `protocol` | 必须为 `agentpost/1` |
| `message_id` | `<timestamp.rand.local@domain>` |
| `from` | 发送方地址 |
| `to` | 收件人列表 |
| `subject` | 主题 |
| `date` | ISO 8601 时间戳 |
| `type` | request / reply / event / receipt / artifact / system |

### 可选头

| 字段 | 说明 |
|------|------|
| `cc` | 抄送列表 |
| `bcc` | 密送（投递后剥离） |
| `priority` | low / normal / high |
| `in_reply_to` | 回复的消息 ID |
| `references` | 引用消息 ID 列表 |
| `thread_id` | 线程 ID |
| `labels` | 标签列表 |
| `attachments` | 附件列表 [{name, path, sha256, media_type}] |
| `routing` | {notify: bool, ack: bool} |

### 示例

```yaml
---
protocol: agentpost/1
message_id: "<20260929.1727590000123.coder-02@agentpost.local>"
from: "coder-02@agentpost.local"
to:
  - "researcher-01@agentpost.local"
subject: "请核对 API 错误码表"
date: "2026-09-29T07:34:00Z"
type: request
priority: normal
thread_id: "thr-api-errcode"
payload_format: markdown
routing:
  ack: true
labels:
  - api
---

正文内容...
```

## API 一览

基础路径: `/api/v1`

### 系统 (公开/Operator)

| 方法 | 路径 | 角色 | 功能 |
|------|------|------|------|
| GET | `/health` | 任意 | 存活检查 |
| GET | `/version` | 任意 | 版本信息 |
| GET | `/metrics` | operator | 投递统计 |
| GET | `/config` | operator | 运行配置 |
| POST | `/doctor` | operator | 完整性检查 |

### 盒子管理 (Operator)

| 方法 | 路径 | 功能 |
|------|------|------|
| POST | `/boxes` | 注册 |
| GET | `/boxes` | 列表 |
| GET | `/boxes/{id}` | 详情 |
| PATCH | `/boxes/{id}` | 更新状态 |
| POST | `/boxes/{id}/revoke` | 吊销 |
| POST | `/boxes/{id}/token/rotate` | 轮换令牌 |
| GET | `/addrbook` | 公开地址簿 |

### 邮件 (Box Token / Operator Act-As)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/boxes/{id}/inbox` | 列收件箱 |
| GET | `/boxes/{id}/inbox/{mid}` | 读消息 |
| POST | `/boxes/{id}/inbox/{mid}/ack` | 标记已处理 |
| GET | `/boxes/{id}/outbox` | 列出件箱 |
| POST | `/boxes/{id}/outbox` | 发信 |
| GET | `/boxes/{id}/threads/{tid}` | 线程视图 |

### 文件 (Box Token)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/boxes/{id}/files` | 列目录 |
| GET | `/boxes/{id}/files/content` | 读文件 |
| PUT | `/boxes/{id}/files/content` | 写文件 |
| GET | `/boxes/{id}/memory` | 记忆索引 |
| GET | `/boxes/{id}/skills` | 技能清单 |
| PUT | `/boxes/{id}/skills/manifest` | 更新技能 |
| GET | `/boxes/{id}/logs` | 审计日志 |

### 队列 (Operator)

| 方法 | 路径 | 功能 |
|------|------|------|
| GET | `/spool` | 队列状态 |
| POST | `/spool/dead-letter/{id}/retry` | 重投 |
| POST | `/spool/dead-letter/{id}/drop` | 作废 |

### 事件 (WebSocket)

`GET /api/v1/stream?token=TOKEN`

事件类型: `box.registered`, `box.status_changed`, `mail.outbox_accepted`, `mail.delivered`, `mail.rejected`, `mail.bounced`, `mail.inbox_new`, `skills.finished`, `skills.failed`, `queue.depth`

## 内置 Skills

| 名称 | 时机 | 行为 |
|------|------|------|
| `builtin.validate_headers` | on_send | 校验强制头、from 匹配 |
| `builtin.classify` | on_receive | 按类型/标签写 episodic 索引 |
| `builtin.save_attachments` | on_receive | 附件落到 data/inbound/ |
| `builtin.file_bounce` | on_bounce | 退信归档 |
| `builtin.receipt_index` | on_receive | 更新 outbox-status.json |

## 地址规则

- local_part: `[a-z0-9][a-z0-9._-]{1,62}`
- 域名: 可配置，默认 `agentpost.local`
- 保留名: `system`, `postmaster`, `agentpost`, `all`, `broadcast`
- 不支持外部 SMTP
