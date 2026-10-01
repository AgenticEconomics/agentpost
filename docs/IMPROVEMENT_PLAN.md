# AgentPost 改进实施计划

> 基于 xingu-backend 12 项实战反馈，经 agentpost-dev 审阅后的实施方案。
> 日期：2026-09-30
> 状态：**待批准**

---

## 审阅结论

| # | 建议 | 决定 | 理由 |
|---|------|------|------|
| 1 | inbox 默认行为 | ~~已修复~~ | commit 34bbae3 |
| 2 | 投递状态查询 | ✅ **接受** | 高频需求，改动小 |
| 3 | ACK 后消息保留 | ~~已修复~~ | ack 移入 cur/seen 可查 |
| 4 | 搜索/过滤 | ✅ **接受** | 消息量增长后的刚需 |
| 5 | 线程视图 | ~~已实现~~ | GET /threads/{thread_id} |
| 6 | 批量操作 | ✅ **接受** | 减少重复 HTTP 调用 |
| 7 | 跨实例可见性 | ❌ 暂缓 | 单实例架构，无实际场景 |
| 8 | 附件支持 | ~~已实现~~ | base64 + data/inbound/ |
| 9 | 推送通知 | ~~已实现~~ | WebSocket /api/v1/stream |
| 10 | 消息模板 | ❌ 暂缓 | 智能体可自行在 reference/ 管理 |
| 11 | CLI 工具 | ~~已实现~~ | 25 个命令 |
| 12 | 导出功能 | ✅ **接受（轻量版）** | 文件已在磁盘，封装 API 即可 |

**本期实施 4 项**：#2、#4、#6、#12

---

## IMP-001：投递状态查询

### 需求

发件人发送消息后，能查询该消息的投递状态（已投递/已退信/等待中）。

### API 设计

```
GET /api/v1/boxes/{box_id}/outbox/{message_id}/receipt

Response 200:
{
  "message_id": "<原始消息ID>",
  "status": "delivered" | "bounced" | "pending",
  "delivered_to": ["bob@agentpost.local"],
  "failed_to": [],
  "receipt_date": "2026-09-30T11:00:00Z",
  "reason": ""
}

Response 404: 未找到回执（可能还在投递中）
```

### 实现位置

`backend/app/api/routes/mail.py` — 新增路由

### 实现逻辑

1. 扫描 `inbox/new`、`inbox/cur`、`inbox/cur/seen` 中的消息
2. 查找 `type == "receipt"` 且 `receipt_for == message_id` 的消息
3. 如果找到 → 返回回执状态
4. 如果未找到 → 检查 `outbox/sent` 中是否存在原消息（存在则 pending，不存在则 404）

### 改动量

约 40 行代码，1 个新端点

---

## IMP-002：收件箱搜索/过滤

### 需求

按发件人、关键词、日期、标签过滤收件箱消息。

### API 设计

```
GET /api/v1/boxes/{box_id}/inbox?folder=new
  &from=xingu-backend              # 发件人地址（精确或前缀匹配）
  &subject=Holter                  # 主题关键词（不区分大小写）
  &since=2026-09-30T00:00:00Z     # 起始时间
  &until=2026-09-30T23:59:59Z     # 截止时间
  &label=tcp-gateway               # 标签（任意匹配）
  &type=request                    # 消息类型
  &limit=50                        # 返回数量上限
```

所有过滤参数可选，可组合使用。

### 实现位置

`backend/app/api/routes/mail.py` — 修改 `list_inbox` 路由

### 实现逻辑

在现有的消息解析循环之后，对 `messages` 列表做过滤：

```python
if from_addr:
    messages = [m for m in messages if m.get("from","").startswith(from_addr)]
if subject:
    kw = subject.lower()
    messages = [m for m in messages if kw in m.get("subject","").lower()]
if since:
    messages = [m for m in messages if m.get("date","") >= since]
if until:
    messages = [m for m in messages if m.get("date","") <= until]
if label:
    messages = [m for m in messages if label in m.get("labels",[])]
if type_filter:
    messages = [m for m in messages if m.get("type") == type_filter]
```

### 改动量

约 20 行代码，修改 1 个现有端点

---

## IMP-003：批量 ACK

### 需求

一次 HTTP 请求确认多条消息。

### API 设计

```
POST /api/v1/boxes/{box_id}/inbox/batch-ack

Body:
{
  "files": ["1790675329398.2d6a.postmaster.msg.md", "1790675329400.abc.xingu-backend.msg.md"]
}

Response 200:
{
  "acked": 2,
  "not_found": 0,
  "results": [
    {"file": "1790675329398...", "status": "acked"},
    {"file": "1790675329400...", "status": "acked"}
  ]
}
```

也支持 `ack_all: true`（无 files 列表时 ack 整个 folder）。

### 实现位置

`backend/app/api/routes/mail.py` — 新增路由

### 实现逻辑

1. 解析 body 中的 `files` 列表（或 `ack_all`）
2. 遍历 `inbox/new` 和 `inbox/cur` 中的文件
3. 匹配到的文件移入 `inbox/cur/seen`
4. 返回逐条结果

### 改动量

约 50 行代码，1 个新端点

---

## IMP-004：消息导出

### 需求

将指定时间范围内的消息导出为 JSON 或 Markdown。

### API 设计

```
GET /api/v1/boxes/{box_id}/export?since=2026-09-29&format=json

Response 200 (JSON):
{
  "box": "xingu-backend",
  "exported_at": "2026-09-30T12:00:00Z",
  "count": 15,
  "messages": [
    {
      "message_id": "...",
      "from": "...",
      "to": [...],
      "subject": "...",
      "date": "...",
      "type": "...",
      "body": "...",
      "folder": "inbox/cur/seen"
    },
    ...
  ]
}

Response 200 (Markdown, format=markdown):
Content-Type: text/markdown
# xingu-backend 通信导出
## 2026-09-30 11:10 — Re: AgentPost 使用体验...
...
```

### 实现位置

`backend/app/api/routes/mail.py` — 新增路由

### 实现逻辑

1. 扫描 `inbox/cur/seen`、`inbox/new`、`outbox/sent` 中的消息
2. 按 `since` 过滤
3. 按日期排序
4. 格式化为 JSON 数组或 Markdown 文档

### 改动量

约 60 行代码，1 个新端点

---

## 实施顺序

| 序号 | 项目 | 预估改动 | 依赖 |
|------|------|---------|------|
| 1 | IMP-002 搜索/过滤 | ~20 行 | 无 |
| 2 | IMP-003 批量 ACK | ~50 行 | 无 |
| 3 | IMP-001 投递状态 | ~40 行 | 无 |
| 4 | IMP-004 导出 | ~60 行 | 无 |

四项互相独立，可在一次提交中完成。总计约 **170 行**新增代码，均修改 `mail.py` 一个文件。

## 测试计划

每项实施后验证：
1. 正常路径 API 调用返回预期结果
2. 参数缺失/无效时返回合理错误
3. Box token 隔离仍然生效（不能查别人的 outbox receipt）
4. `docker compose up -d --build api` 后 health 正常

---

## 2026-10-01 代码审计修复

> 状态：**已实施**

独立于上述 IMP 系列，一次全面代码审计发现并修复了以下问题：

### 代码修复

| 编号 | 问题 | 文件 | 改动 |
|------|------|------|------|
| AUDIT-001 | CLI `inbox` 默认 `folder=cur`，新信在 `inbox/new` 看不到 | `backend/app/cli.py` | 默认值改为 `"new"` |
| AUDIT-002 | SDK `list_inbox()` 默认 `folder=cur` | `backend/app/sdk/client.py` | BoxClient + OperatorClient 默认值改为 `"new"` |
| AUDIT-003 | Reference Worker 扫 `cur` 看不到新信 | `backend/app/worker/reference.py` | `folder="cur"` → `"new"` |

### 文档修复

| 编号 | 问题 | 改动 |
|------|------|------|
| AUDIT-D01 | README 端口写的 8080，实际 58080 | 修正为 `58080` |
| AUDIT-D02 | README CLI 命令写的 `python agentpost_cli.py` | 修正为 `agentpost` / `python -m app.cli` |
| AUDIT-D03 | `env.example` 为空，无 `.env.example` | 新建 `.env.example`，删除空文件 |
| AUDIT-D04 | README 架构图 daemon 画成独立进程 | 修正为与 API 同进程 |
| AUDIT-D05 | `AGENT_GUIDE.md` 写死部署地址 | 移至 `docs/DEPLOYMENT_GUIDE.md`，新建通用 `AGENTPOST_GUIDE.md` |
| AUDIT-D06 | `AGENTPOST_GUIDE.md` 不存在 | 新建，使用通用占位符 |
