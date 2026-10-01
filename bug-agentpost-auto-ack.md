---
title: "AgentPost Bug: daemon 自动 ack 导致收件箱 new/ 始终为空"
doc_id: JV-BUG-2026-001
date: 2026-09-29
author: Jerry Zhang
status: open
severity: high
affected_component: AgentPost daemon / inbox delivery
reporter_box: hf-agent@agentpost.local
---

# AgentPost Bug: daemon 自动 ack 导致收件箱 new/ 始终为空

## 1. 摘要

发送到 `hf-agent@agentpost.local` 的所有消息在 daemon 投递后**立即出现在 `cur/`（已处理）文件夹**，而非预期的 `new/`（未读）文件夹。收件方从未调用 ack API，但消息已被系统自动标记为已读。此问题导致基于 `folder=new` 的消息轮询机制**完全失效**。

## 2. 预期行为

根据 AgentPost 用户指南（`AGENTPOST_GUIDE.md`）：

- 新消息投递后应进入 `inbox/new/`
- 消息仅在收件方**显式调用** `POST /api/v1/boxes/{box}/inbox/{file}/ack` 后才从 `new/` 移到 `cur/`
- ack 是收件方的**主动行为**，不应由系统自动执行
- 推荐工作循环为：检查 `new/` → 读取 → 处理 → 回复 → 手动 ack

## 3. 实际行为

消息投递后**立即**出现在 `cur/`，跳过 `new/` 阶段。具体表现：

```
1. 发送方 POST /outbox → status: "accepted"
2. daemon 投递 → 投递回执确认 Status: "delivered"
3. 收件方 GET /inbox?folder=new → []（空）
4. 收件方 GET /inbox?folder=cur → 消息已在此处（已被自动 ack）
```

## 4. 复现步骤

```bash
# 步骤 1：从任意 box 向 hf-agent 发送消息
curl -s -X POST http://localhost:8765/api/v1/boxes/hvfm/outbox \
  -H "Authorization: Bearer <hvfm-token>" \
  -H "Content-Type: application/json" \
  -d '{"to":["hf-agent@agentpost.local"],"subject":"Test","body":"test","type":"event","ack":true}'

# 步骤 2：等待 2-3 秒（daemon 投递）

# 步骤 3：检查 hf-agent 的 new/ 文件夹
curl -s "http://localhost:8765/api/v1/boxes/hf-agent/inbox?folder=new" \
  -H "Authorization: Bearer <hf-agent-token>"
# 预期：返回包含刚发送消息的数组
# 实际：返回 []

# 步骤 4：检查 hf-agent 的 cur/ 文件夹
curl -s "http://localhost:8765/api/v1/boxes/hf-agent/inbox?folder=cur" \
  -H "Authorization: Bearer <hf-agent-token>"
# 实际：消息已在此处
```

## 5. 受影响消息清单

以下为 2026-09-29 10:00 UTC 前后 hf-agent 收到的**全部消息**，无一例外被自动 ack：

| # | 时间 (UTC) | 发送方 | 主题 | 类型 |
|---|------------|--------|------|------|
| 1 | 09:48:49 | postmaster | Welcome to AgentPost | system |
| 2 | 09:51:18 | postmaster | Receipt: delivered（xingu 连通测试回执） | receipt |
| 3 | 09:56:08 | jarvikdatavault | DataVault 平台进度通报（2026-09-29） | event |
| 4 | 09:57:09 | postmaster | Receipt: delivered（jarvikdatavault 回复回执） | receipt |
| 5 | 09:58:15 | xingu-backend | Re: HF-Agent 邮箱连通性测试 | reply |
| 6 | 10:06:58 | postmaster | Receipt: delivered（部署通报回执） | receipt |
| 7 | 10:14:20 | hvfm | Connection Test | event |
| 8 | 10:19:12 | postmaster | Receipt: delivered（Connection Test 回复回执） | receipt |
| 9 | 10:21:31 | hvfm | Phase K 启动：HVFM 侧进展 + 你的下一步任务 | request |
| 10 | 10:23:58 | postmaster | Receipt: delivered（Phase K 回复回执） | receipt |
| 11 | 10:25:28 | hvfm | Re: Phase K（确认任务完成） | reply |

**受影响比例：11/11 = 100%**

涵盖全部 4 种消息来源（postmaster / jarvikdatavault / xingu-backend / hvfm）和全部 5 种消息类型（system / receipt / event / request / reply）。

## 6. 影响分析

### 6.1 功能影响

| 影响 | 严重程度 | 说明 |
|------|---------|------|
| 新消息不可见 | 🔴 严重 | `GET /inbox?folder=new` 始终返回空，收件方无法发现新消息 |
| 未读/已读无法区分 | 🔴 严重 | 所有消息都在 `cur/`，无法判断哪些是新的、哪些已处理 |
| 轮询机制失效 | 🔴 严重 | 依赖 `folder=new` 的定时检查逻辑完全无效 |
| 消息遗漏风险 | 🟡 中等 | 收件方可能完全不知道有消息到达，除非主动检查 `cur/` 并逐条比对 |

### 6.2 实际后果

- hf-agent 在 10:14 收到 HVFM 的 Connection Test，但检查 `new/` 返回空，**用户被告知"没有新消息"**
- hf-agent 在 10:21 收到 HVFM 的高优先级任务分配（Phase K），同样不在 `new/` 中
- hf-agent 在 10:25 收到 HVFM 的回复确认，同样不在 `new/` 中
- 每次都需要用户提示"去 `cur/` 里找"才能发现消息

## 7. 环境信息

| 项目 | 值 |
|------|-----|
| API base | `http://localhost:8765` |
| 受影响 Box | `hf-agent@agentpost.local` |
| Box 注册时间 | 2026-09-29 09:48 UTC |
| 发送方 | jarvikdatavault / xingu-backend / hvfm / postmaster |
| 发送方投递状态 | 全部正常（`status: accepted` + 回执 `Status: delivered`） |
| 其他 Box 是否受影响 | **未测试**（jarvikdatavault / xingu-backend / hvfm 未做同等检查） |

## 8. 排查建议

1. **检查 hf-agent box 配置**：是否存在 `auto_ack` 或类似配置项被默认开启
2. **检查 daemon 投递逻辑**：确认投递到 `inbox/new/` 后是否有额外的自动 ack 步骤
3. **检查 box 注册流程**：hf-agent 是新注册的 box（2026-09-29），确认注册时是否有特殊默认设置
4. **交叉验证**：向其他 box（如 hvfm）发送测试消息，检查是否也自动进入 `cur/`
5. **检查 postmaster 回执投递路径**：回执消息（`type: receipt`）是否与普通消息走不同路径

## 9. 临时规避方案

在修复前，hf-agent 的邮箱检查流程已改为同时检查 `new/` 和 `cur/`：

```bash
# 同时检查两个文件夹
curl -s "http://localhost:8765/api/v1/boxes/hf-agent/inbox?folder=new" -H "..."
curl -s "http://localhost:8765/api/v1/boxes/hf-agent/inbox?folder=cur" -H "..."
# 对比已读列表，找出未处理的消息
```

此方案增加了复杂度且无法可靠区分"新消息"和"已处理消息"（因为所有消息都在 `cur/` 中）。

## 10. 期望修复

1. 消息投递后应停留在 `inbox/new/`，直到收件方显式 ack
2. 已投递到 `cur/` 的历史消息是否需要回移到 `new/`（取决于修复策略）
3. 确认修复后应对所有 box 进行端到端验证

---

*报告人：hf-agent@agentpost.local*
*日期：2026-09-29*
