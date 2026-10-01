# AgentPost 系统开发提示词（给实现智能体 / 工程团队）

你是资深系统工程师，负责从零实现一个本地优先的多智能体协作运行时：**AgentPost**。

本提示词是唯一规格来源。未写明的能力不要发明成「平台功能」；先把邮件式投递、目录隔离、技能自动预处理做对。实现时优先可运行的最小闭环，再扩展。

---

## 0. 一句话目标

在一台虚拟服务器或 sandbox 里，多个智能体各自待在独立工作区（SubBox）做不同任务。它们**不共享工作目录、不互相扫描、不直接写对方磁盘**。唯一合法通信通道是 AgentPost 提供的「本地邮箱」：注册得到地址，把消息/文件放到自己的 `outbox/`，由系统按消息头转发到对方 `inbox/`，再由该 SubBox 的 skills 做自动预处理，最后由该智能体定时只扫描自己的盒子并响应。

隐喻：**邮局 + 私人邮箱 + 邮件规则（skills）+ 收件人本人（agent loop）**。  
不是群聊，不是共享文件夹，不是中心数据库里的消息表（可用内部索引，但对智能体不可见）。

---

## 1. 设计原则（必须遵守）

1. **文件系统即协议。** 智能体只通过约定目录和约定文件格式交互。任何语言、任何模型、任何框架，只要会读写自己的 SubBox，就能入网。
2. **投递权与读写权分离。** 只有 AgentPost 核心进程（`agentpostd`）有权把文件从 A 的 outbox 移到 B 的 inbox。智能体进程对其他 SubBox 无读、无写、无列目录权限。
3. **先投递，再理解。** 路由只看消息头，不解析正文语义。语义处理交给目标 SubBox 的 skills，再交给智能体。
4. **失败可见、可重试、不丢信。** 投递失败进入 `dead-letter/` 或退回发送方 inbox 的系统回执，禁止静默删除。
5. **最小权限扫描。** 智能体只能看见自己的 SubBox 根路径。连「有哪些其他地址」也只能通过自己 inbox 里的系统目录信，或只读的全局地址簿视图（见第 6 节），不能遍历 `/boxes/`。
6. **脚本不可信。** SubBox 内 `scripts/` 与 skills 钩子默认在受限环境执行（超时、无网或白名单、只挂载本盒子、drop privileges）。
7. **本地、可单机演示。** 第一期不依赖云、不依赖外部邮件服务器、不依赖 LLM 才能转信。没有大模型时，注册、投递、回执、skills 规则仍必须工作。
8. **三端一体、服务常驻。** 系统由常驻服务端（`agentpostd` + HTTP API）、Web 前端、CLI 组成，用 Docker Compose 一键拉起并保持运行。文件系统协议不变：三端都是邮局的窗口，不是另一套消息总线。

---

## 2. 系统角色

| 角色 | 谁 | 权限 | 职责 |
|---|---|---|---|
| `agentpostd` | 系统守护进程 | 可读写所有 boxes（仅用于投递/回收） | 注册、监视 outbox、校验、转发、回执、触发 skills、写日志 |
| SubBox | 每个智能体的家目录 | 仅本盒子 | 存放身份、邮件、数据、记忆、技能、脚本 |
| Agent Worker | 真正干活的智能体进程 | 仅本盒子 + 自己的任务工作区（可选绑定） | 定期扫描 inbox/memory，执行任务，把对外信件写入自己的 outbox |
| Operator | 人 / 部署脚本 | 管理接口 | 创建盒子、吊销、看队列、看死信 |

禁止：Agent Worker 直接 `cp` 到别人 inbox；禁止共享一个「公共 inbox」；禁止用环境变量把所有盒子路径告诉每个智能体。

---

## 3. 目录规范

### 3.1 系统根目录

默认：`$AGENTPOST_ROOT`（例：`/var/lib/agentpost` 或 sandbox 内 `/agentpost`）。

```text
$AGENTPOST_ROOT/
  agentpost.yaml                 # 系统配置
  registry/
    agents.jsonl                # 注册表（追加+快照均可，需可重建）
    revoked.json                # 吊销名单
  boxes/
    <local-part>/               # 一个 SubBox = 一个邮箱地址本地部分
      ...
  spool/                        # 系统投递队列（智能体不可见）
    incoming/
    retry/
    dead-letter/
  logs/
  run/                          # pid, socket
  addrbook/
    public.json                 # 可选：脱敏地址簿（仅 name, address, bio, capabilities）
```

### 3.2 每个 SubBox 的强制目录（创建时一次性建齐）

地址形式：`<local-part>@agentpost.local`  
文件系统名：`boxes/<local-part>/`  
`<local-part>` 只允许 `[a-z0-9][a-z0-9._-]{1,62}`，大小写折叠为小写，禁止 `..`、禁止与系统保留名冲突（`system`, `postmaster`, `agentpost`, `all`, `broadcast` 需显式策略）。

```text
boxes/<local-part>/
  AGENT.toml                    # 身份与描述（人类/机器可读）
  inbox/                        # 只收：别人或系统投来的信
    new/                        # 刚投递、尚未被 skills 预处理
    cur/                        # 已预处理、等待智能体处理
    tmp/                        # 投递原子写入暂存（Maildir 风格）
  outbox/
    new/                        # 智能体投放、等待 agentpostd 收走
    tmp/
    sent/                       # 投递成功归档（或只保留索引）
    failed/                     # 被拒信、退信副本
  reference/                    # 只读参考资料、规范、接口说明
  data/                         # 任务数据、附件落盘、工作产物
  scripts/                      # 本盒子可被系统或 skills 调用的脚本
  memory/                       # 长期记忆（笔记、摘要、状态机）
    episodic/                   # 事件记忆
    semantic/                   # 结构化记忆
  skills/                       # 自动处理规则与技能包
    manifest.toml
    on_receive/                 # 入站钩子
    on_send/                    # 出站钩子（投递前本地检查）
    on_bounce/                  # 退信钩子
    builtin/                    # 系统注入的只读基础技能（可选只读挂载）
  work/                         # 可选：该智能体当前任务工作区（与邮箱分离）
  logs/                         # 本盒子审计（智能体可写自己的，系统也可写）
```

说明：

- `inbox/`、`outbox/` 必须用 **Maildir 三态**（`tmp` → `new` → `cur`/`sent`），避免读到半写入文件。
- 智能体**禁止**自己把文件塞进别人的 `inbox/new`。唯一合法出站动作：在自己的 `outbox/tmp` 写完后 `rename` 到 `outbox/new`。
- `reference/` 默认对智能体只读（由注册或管理员投放）。若需更新，走系统信或管理员通道。
- `skills/builtin/` 若由系统提供，对智能体只读，防止智能体改掉基础投递预处理。

### 3.3 AGENT.toml（身份描述，注册时写入）

```toml
[agent]
id = "researcher-01"
address = "researcher-01@agentpost.local"
display_name = "资料研究员"
created_at = "2026-09-29T00:00:00Z"
status = "active"              # active | paused | revoked

[profile]
summary = "负责公开资料检索、摘录与交叉验证"
capabilities = ["research", "summarize"]
languages = ["zh", "en"]
owner = "human-or-system"

[box]
root = "/agentpost/boxes/researcher-01"
scan_interval_sec = 15
max_scan_batch = 20

[security]
token_sha256 = "..."           # 智能体出示的盒子令牌哈希
allow_scripts = true
network_policy = "none"        # none | allowlist
```

---

## 4. 消息协议（文件即邮件）

### 4.1 一封消息 = 一个目录或一个单文件

第一期采用 **单文件消息**，附件用同目录 sidecar 或内嵌清单，便于监视器处理。

推荐文件名：

```text
<unix_ms>.<pid_or_rand>.<local-part>.msg.md
```

例：`1727590000123.a8f3.coder-02.msg.md`

也允许 `.msg.json`（纯结构化）和 `.msg.md`（YAML front matter + Markdown 正文）。系统必须两种都能解析；内部规范以 front matter 为准。

### 4.2 消息头（强制 + 可选）

Front matter 字段：

```yaml
---
protocol: agentpost/1
message_id: "<20260929.1727590000123.coder-02@agentpost.local>"
from: "coder-02@agentpost.local"
to:
  - "researcher-01@agentpost.local"
cc: []
bcc: []                          # 投递后在收件副本中剥离
subject: "请核对 API 错误码表"
date: "2026-09-29T07:34:00Z"
type: request                    # request | reply | event | receipt | artifact | system
priority: normal                 # low | normal | high
in_reply_to: null
references: []
thread_id: "thr-api-errcode"
expires_at: null
payload_format: markdown         # markdown | json | text
attachments:
  - name: "errors.csv"
    path: "./errors.csv"         # 相对该消息暂存包；或 data/ 下由系统拷贝后的相对路径
    sha256: "..."
    media_type: "text/csv"
routing:
  notify: true
  ack: true                      # 要求系统或对方回执
labels: ["api", "docs"]
---

正文……
```

强制头：`protocol`, `message_id`, `from`, `to`, `subject`, `date`, `type`。  
缺强制头 → 拒信，原件移到发送方 `outbox/failed/`，并写系统回执到发送方 `inbox/`。

### 4.3 系统回执

`type: receipt`，`from: postmaster@agentpost.local`。

```yaml
receipt_for: "<原 message_id>"
status: delivered | rejected | bounced | expired
reason: "..."
delivered_to: ["researcher-01@agentpost.local"]
failed_to: []
```

智能体把 `routing.ack: true` 的信投出后，必须能在自己的 inbox 收到至少一次系统回执（成功或失败）。

### 4.4 附件

- 小附件（默认 ≤ 10MB）随消息包复制进收件方 `data/inbound/<message_id>/`。
- 正文 attachments.path 在投递后改写为收件方盒子内的相对路径。
- 超限拒信。禁止 outbox 用绝对路径引用盒子外文件（防止把 `/etc/shadow` 当附件发出）。

---

## 5. 注册系统

### 5.1 注册流程

1. 调用管理 CLI 或本地 socket API：`agentpost register`。
2. 入参：`local_part` 或自动生成、`profile.summary`、`capabilities`、可选公钥/token。
3. 系统校验名称、建目录树、写 `AGENT.toml`、发欢迎信到该 inbox、更新 `registry/agents.jsonl` 与 `addrbook/public.json`。
4. 返回：`address`、`box_root`、`token`（明文只出现一次）、扫描约定。

欢迎信由 `postmaster@agentpost.local` 发送，正文包含：自己的路径、目录含义、如何写一封 outbox 信、示例消息、当前公开地址簿摘要。

### 5.2 注销 / 暂停

- `paused`：停止为其执行 skills 与投递出站（inbox 仍可收，或按配置拒收）。
- `revoked`：拒绝投递，目录可冻结只读。

### 5.3 地址解析

- `researcher-01@agentpost.local` → `boxes/researcher-01/`
- 一期不支持外部 SMTP。若 `to` 域不是 `agentpost.local`（可用配置改），直接拒信。
- 广播：默认关闭。若开启，仅允许 `to: ["broadcast@agentpost.local"]` 且发送方在白名单；投递为每人一封独立副本，不是共享同一文件。

---

## 6. 投递引擎（agentpostd 的核心）

### 6.1 监视

使用 inotify/FSEvents/`watchdog` 或 1–2 秒扫描 `boxes/*/outbox/new/`。  
必须处理：rename 原子投递、短时间多文件、部分写入（只处理已进入 `new/` 的文件）。

### 6.2 出站管道（对每一封 outbox/new 中的消息）

按顺序：

1. **鉴权**：文件所有者 / 盒子 token / 路径属于该 local-part。`from` 必须等于该盒子地址（禁止伪造发件人）。
2. **运行 `skills/on_send/`**（见第 7 节）。失败则不投递，进 `outbox/failed/`。
3. **校验头与附件路径。**
4. **写入系统 spool**（拷贝，不立刻删源文件）。
5. **对每个收件人**：
   - 解析地址 → 目标盒子存在且 `active`
   - 在目标 `inbox/tmp/` 写完整消息（改写 attachments 路径，剥离 bcc）
   - `rename` 到目标 `inbox/new/`
6. **源文件**移到发送方 `outbox/sent/`（可同时写 sent 索引）。
7. **若 ack**：给发送方投系统回执。
8. **触发收件方 `skills/on_receive/`**（对 `inbox/new`）。

多收件人：部分成功时，成功的算 delivered，失败的写回执 `failed_to`，已成功的不撤回。

### 6.3 入站后状态

```text
inbox/tmp  --rename--> inbox/new  --skills成功--> inbox/cur
                              \--skills失败--> inbox/new 保留 + logs 错误
                                            或 inbox/cur 并打标 needs_agent
```

智能体默认只处理 `inbox/cur`（已预处理）。也可配置「skills 失败仍可见」。

### 6.4 并发

同一消息只被一个投递 worker 处理（文件锁或把 new 中的文件 rename 进 spool 作为认领）。  
同一收件人 inbox 的写入要原子，避免两个 worker 写同名文件。

---

## 7. Skills：盒子级自动预处理

Skills 不是「另一个聊天机器人必选」。第一期必须能用**无 LLM 的规则技能**跑通。

### 7.1 manifest.toml

```toml
[skills]
version = 1
on_receive = ["builtin.classify", "builtin.save_attachments", "local.route_by_label"]
on_send = ["builtin.validate_headers", "local.sign"]
on_bounce = ["builtin.file_bounce"]

[skill."local.route_by_label"]
when_type = ["request"]
when_label_any = ["api"]
action = "copy_body_to"
target = "data/tasks/api/"
```

### 7.2 内置技能（系统提供，必须实现）

| skill | 时机 | 行为 |
|---|---|---|
| `builtin.validate_headers` | on_send | 检查强制头、from 匹配、to 非空 |
| `builtin.classify` | on_receive | 按 type/priority/labels 写 `memory/episodic/` 一行索引 |
| `builtin.save_attachments` | on_receive | 附件落到 `data/inbound/<message_id>/` |
| `builtin.file_bounce` | on_bounce | 退信归档 + 在 memory 记一笔 |
| `builtin.receipt_index` | on_receive | 若 type=receipt，更新 `memory/semantic/outbox-status.json` |

### 7.3 本地技能

- 放在 `skills/on_receive/` 等目录，可为可执行文件或 `.toml` 规则。
- 可执行技能接口（stdin/stdout）：stdin 给消息绝对路径 + JSON 头；stdout 返回 JSON：
  ```json
  {"status":"ok","actions":[{"op":"move_to","path":"data/tasks/api/xxx.md"}],"notes":"..."}
  ```
- 超时默认 5s，CPU/内存上限可配。禁止访问其他 boxes。工作目录 = 该 SubBox 根。
- `scripts/` 仅当 skill 或智能体显式调用时执行，不在每次投递时盲目跑全部脚本。

### 7.4 「首先自动按 skills 处理」的含义

对每一封新入站信，**在智能体扫描之前**：

1. 保存附件  
2. 建立索引  
3. 按标签/类型分拣到 `data/` 子目录（可选）  
4. 把消息从 `inbox/new` 转到 `inbox/cur`  
5. 写 `logs/skills.log`

智能体看到的是已经分拣过的信，而不是原始堆。

---

## 8. 智能体扫描循环（Agent Worker 约定）

AgentPost **不内置某个 LLM 框架**，但必须提供一个参考 Worker（可用 shell + Python）：

```text
loop:
  鉴权：用 token 打开且仅打开自己的 box_root
  列出 inbox/cur 中未处理消息（可用 memory/semantic/seen.json 去重）
  对每封：
      读取头与正文
      如需参考：只读 reference/、memory/
      如需数据：读写自己的 data/、work/
      产生响应：在 outbox/tmp 写新消息（正确填 in_reply_to, thread_id, from）
      rename 到 outbox/new
      把原信标记为已处理（改名加前缀或移到 inbox/cur/seen/）
  定期整理 memory（可选，非 MVP）
  sleep scan_interval_sec
```

硬约束：

- Worker 启动时只接收 `AGENTPOST_BOX_ROOT` 与 `AGENTPOST_TOKEN`，不接收全局 root。
- 任何 `../` 逃逸、打开其他 local-part 路径，视为安全漏洞，必须在参考实现里拒绝。
- 「只能扫描自己的盒子」既是约定，也要在 OS 层尽量落实：每盒子独立 Unix 用户，或 Linux user namespace，或绑定挂载只把本盒子给 Worker。第一期至少做：独立 uid **或** 路径防火墙（Worker SDK 拒绝越权路径）+ 文档说明生产应上 OS 隔离。

---

## 9. 隔离与鉴权（必须写进实现）

### 9.1 身份

- 每个盒子一个随机 token（256-bit），只存放哈希。
- CLI/`agentpostd` 管理接口用单独的 operator token。
- 消息 `from` 只能是「当前已鉴权盒子的地址」。

### 9.2 路径隔离

- Worker 与 skills 进程的可见根 = 该 SubBox。
- `agentpostd` 是唯一跨盒子进程。
- spool、registry、其他 boxes 对 Worker 不可见。

### 9.3 脚本隔离

执行 `scripts/` 或可执行 skill 时：

- 超时、kill
- 工作目录锁在本盒子
- 默认无网络
- 不以 root 运行

### 9.4 审计

每封信记录：`message_id, from, to, accepted_at, delivered_at, skill_results, worker_seen_at`。  
日志在系统 `logs/`；盒子内可有脱敏副本。

---

## 10. 总体部署形态（三端 + 常驻）

运行时不是「跑完脚本就退出」，而是一组**持续进程**：

| 进程 | 容器建议名 | 职责 | 退出策略 |
|---|---|---|---|
| `agentpostd` | `agentpost-daemon` | 监视 outbox、投递、skills、回执、死信重试 | `restart: unless-stopped` |
| `agentpost-api` | `agentpost-api` | HTTP/JSON + WebSocket，给前端和 CLI 用 | 同上 |
| `agentpost-web` | `agentpost-web` | 静态前端或 SSR，反向代理到 API | 同上 |
| `agentpost-worker`（可选多实例） | `agentpost-worker-<id>` | 某个 SubBox 的参考/真实智能体循环 | 按盒子启停，崩溃重启 |

`agentpost` CLI **不是常驻服务**，它是人在宿主机或 `docker compose exec` 里用的客户工具，所有写操作最终都打到 API 或写入本盒 outbox，由 daemon 投递。

第一期允许 `agentpostd` 与 `agentpost-api` 合在同一进程（同一容器，两个端口或同一端口不同 path），但逻辑模块必须分开，便于以后拆分。

默认入口：

- Web：`http://localhost:8080`
- API：`http://localhost:8080/api/v1`（或 `8765`）
- Health：`GET /api/v1/health`
- 数据卷：`agentpost-data:/var/lib/agentpost`

---

## 11. 服务端详细功能

服务端 = **投递内核 + 控制面 API + 实时事件**。控制面不能绕过投递内核直接把文件塞进别人的 `inbox/`（除集成测试的显式 fixture 开关，默认关闭）。

### 11.1 进程与生命周期

启动顺序：

1. 读取 `AGENTPOST_ROOT/agentpost.yaml` 与环境变量  
2. 若根目录未初始化则自动 `init`（容器首次启动必须幂等）  
3. 加载 registry，重建内存索引  
4. 启动 outbox watcher + spool 重试器  
5. 绑定 HTTP  
6. 对外标记 `ready`（health 变绿）

关闭：停止接收新 HTTP 写 → 排空当前投递（超时可配，默认 10s）→ 把进行中的 tmp 文件留在原地供下次恢复 → 退出。`doctor` 必须能收殓异常关机留下的 `tmp/`。

健康检查：

- `GET /api/v1/health` → `{status, version, ready, queue_depth, boxes, uptime_sec}`
- `ready=false` 时 Compose healthcheck 失败，依赖它的 web 不对外。

### 11.2 身份模型（API）

两种令牌，头统一用 `Authorization: Bearer <token>`。

| 角色 | 令牌 | 能做什么 |
|---|---|---|
| Operator | `OPERATOR_TOKEN`（环境变量注入，不进盒子） | 注册/暂停/吊销盒子、看全局队列与死信、看所有盒子元数据、看系统日志 |
| Box Agent | 注册时下发的 box token | 只读写本盒子：列 inbox/outbox、读信、发信、读自己的 memory/data/skills 清单、看自己的日志 |

禁止用 Operator 令牌在前端「一键以某盒子发信」却不走该盒子 outbox。管理后台代发必须指定 `from` 且写入该 from 的 outbox。

### 11.3 HTTP API 清单（v1）

前缀 `/api/v1`。JSON。错误体：`{error:{code,message,details}}`。

**系统（operator 或公开只读子集）**

| 方法 | 路径 | 谁 | 功能 |
|---|---|---|---|
| GET | `/health` | 任意 | 存活与就绪 |
| GET | `/version` | 任意 | 版本、协议 `agentpost/1` |
| GET | `/metrics` | operator | 投递计数、失败、队列、skills 耗时（Prometheus text 或 JSON） |
| GET | `/config` | operator | 脱敏后的运行配置 |
| POST | `/doctor` | operator | 跑完整性检查，返回问题列表并可 `repair=true` |

**注册与盒子**

| 方法 | 路径 | 谁 | 功能 |
|---|---|---|---|
| POST | `/boxes` | operator | 注册。body: `{id, display_name, summary, capabilities[], scan_interval_sec}`。返回 `{address, box_root, token}`（token 仅此一次明文） |
| GET | `/boxes` | operator | 列表：地址、状态、未读、最后活动 |
| GET | `/boxes/{id}` | operator 或本盒 | 档案、目录是否完整、队列摘要 |
| PATCH | `/boxes/{id}` | operator | `status=active\|paused`、改 profile |
| POST | `/boxes/{id}/revoke` | operator | 吊销 |
| POST | `/boxes/{id}/token/rotate` | operator 或本盒 | 轮换 token，旧令牌失效 |
| GET | `/addrbook` | 已登录任意角色 | 公开地址簿：address、display_name、summary、capabilities、status。无 token、无内部路径 |

**邮件（本盒 token；operator 代操作时必须带 `X-Act-As-Box` 且仍走 outbox）**

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/boxes/{id}/inbox?folder=cur\|new&unread=1` | 列出消息头，分页 |
| GET | `/boxes/{id}/inbox/{message_id}` | 读全文 |
| POST | `/boxes/{id}/inbox/{message_id}/ack` | 标为已处理（移到 `cur/seen` 或等价） |
| GET | `/boxes/{id}/outbox?folder=new\|sent\|failed` | 列出 |
| POST | `/boxes/{id}/outbox` | 发信。服务端写入该盒 `outbox/tmp`→`new`，**禁止**直接写收件 inbox |
| GET | `/boxes/{id}/threads/{thread_id}` | 按 thread_id 聚合 |

发信 body：

```json
{
  "to": ["bob@agentpost.local"],
  "cc": [],
  "subject": "请核对错误码",
  "type": "request",
  "priority": "normal",
  "thread_id": "thr-api-errcode",
  "in_reply_to": null,
  "ack": true,
  "labels": ["api"],
  "body": "……",
  "attachments": [{"filename": "errors.csv", "content_base64": "..."}]
}
```

服务端补 `from/message_id/date/protocol`，附件落到发送方临时包再随信拷贝。

**盒子内资源（只本盒）**

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/boxes/{id}/files?path=data/inbound` | 列目录，path 必须相对本盒且经守卫 |
| GET | `/boxes/{id}/files/content?path=...` | 读文件（大小上限） |
| PUT | `/boxes/{id}/files/content?path=...` | 写 `data/`、`memory/`、`work/`；禁止写别人盒子；禁止直接写 `inbox/` |
| GET | `/boxes/{id}/memory` | 索引 episodic + semantic 摘要 |
| GET | `/boxes/{id}/skills` | manifest + 各钩子列表 |
| PUT | `/boxes/{id}/skills/manifest` | 更新本盒 manifest（operator 或本盒） |
| GET | `/boxes/{id}/logs?since=` | 本盒审计 |

**队列（operator）**

| 方法 | 路径 | 功能 |
|---|---|---|
| GET | `/spool` | incoming/retry/dead-letter 计数与最近条目 |
| POST | `/spool/dead-letter/{id}/retry` | 重投 |
| POST | `/spool/dead-letter/{id}/drop` | 作废并记审计 |

### 11.4 WebSocket / SSE

`GET /api/v1/stream`（box token 只推本盒；operator 可 `?box=` 过滤）。

事件：

```text
box.registered
box.status_changed
mail.outbox_accepted
mail.delivered
mail.rejected
mail.bounced
mail.inbox_new
skills.finished
skills.failed
worker.heartbeat
queue.depth
```

前端收件箱、CLI `tail` 都走这一路，禁止前端每秒全量轮询目录。

### 11.5 服务端内部模块（必须分开）

```text
api/          HTTP 鉴权、路由、DTO
daemon/       watcher、认领、投递状态机
router/       按消息头解析收件人
skills/       钩子执行器（沙箱）
registry/     盒子生命周期
events/       总线（进程内 channel → WS）
boxfs/        原子写与路径守卫
audit/        结构化日志
```

API 线程与投递线程解耦：API 写完 outbox 即返回 `accepted`；`delivered` 只通过回执和事件通知。

### 11.6 服务端不做的事

- 不在 API 里调用大模型生成回信  
- 不把多个盒子的 inbox 合成一个「全局收件箱」给普通 Agent token  
- 不提供任意路径的静态文件服务（防止把 `/var/lib/agentpost/boxes` 整棵树挂出去）

---

## 12. 前端详细功能

前端是**操作员控制台 + 某盒子的邮箱客户端**，不是 IDE，不是群聊。第一期要求能完成：看系统是否活着、注册盒子、打开一个盒子读信/回信、看投递是否成功。

建议栈：任意现代 SPA（React/Vue/Svelte）+ 官方 API。静态资源由 `agentpost-web` 提供，API 反代到 `agentpost-api`，浏览器只打同源 `/api`。

### 12.1 信息架构

```text
/login                      粘贴 operator token 或 box token
/ops                        运营总览（operator）
/ops/boxes                  盒子列表与注册
/ops/boxes/:id              盒子档案、启停、轮换 token、目录健康
/ops/queue                  spool / dead-letter
/ops/logs                   系统日志流
/mail                       选盒子后的邮箱（operator 选盒或 box token 锁定）
/mail/inbox
/mail/outbox
/mail/thread/:threadId
/mail/compose
/box/files                  浏览 data / reference / memory（只读+有限上传到 data）
/box/skills                 查看 manifest 与最近 skill 结果
/addrbook                   公开地址簿
```

### 12.2 页面功能

**登录**

- 两种身份入口：Operator / Box  
- token 只存内存或 sessionStorage，刷新需重贴或由本地 dev 配置注入  
- 过期或 401 回登录，不把 token 写进 URL

**运营总览 `/ops`**

- 守护进程 ready、uptime、今日投递/失败、队列深度、活跃盒子数  
- 各盒未读数、最后心跳  
- 一键 `doctor`，结果用表格列出 path + issue + 能否 repair

**盒子管理**

- 注册表单：id、显示名、简介、capabilities 标签、扫描间隔  
- 创建成功弹出**一次性 token**，必须能复制，关闭后不再显示明文  
- 列表：状态灯（active/paused/revoked）、未读、sent/failed  
- 详情：AGENT.toml 可视化、目录树是否缺文件夹、最近 20 封  
- 动作：暂停、恢复、吊销、轮换 token、下载本盒日志

**邮箱 Inbox**

- 文件夹切换：new（预处理中）/ cur（待处理）/ seen  
- 列：from、subject、type、priority、date、labels、是否有附件  
- 点开：头字段、Markdown 正文、附件下载（走 API 而非直接静态盘）  
- 动作：回复（自动带 in_reply_to、thread_id、to=原 from）、标记已处理  
- 实时：WS 推到则插入列表顶部，不整页刷新

**Outbox**

- new / sent / failed 三栏或 Tab  
- failed 显示拒信原因，支持「打开原信另存再发」  
- sent 可对照 receipt 状态（delivered/rejected/bounced）

**写信**

- 收件人从地址簿选，禁止自由填任意文件系统路径  
- type、priority、ack、labels、附件  
- 提交后显示 accepted + message_id，随后用事件更新投递结果  
- 预览即将写入的 front matter，便于调试协议

**文件与记忆**

- 树形看 `data/`、`reference/`、`memory/`  
- `reference/` 只读  
- 允许向 `data/` 上传（大小与类型限制与服务端一致）  
- 禁止 UI 提供「打开 /boxes/其他id」的入口

**Skills**

- 展示 manifest 钩子顺序  
- 最近执行：message_id、skill 名、status、耗时、notes  
- 第一期可只读 manifest；在线编辑属加分项

### 12.3 前端鉴权与隔离

- Box token 登录后，路由被锁在该 `id`，地址栏改别人的 id 应 403  
- Operator 切换「以某盒子查看」是显式 Act-As，界面有横幅提示当前身份  
- 不在浏览器保存整个 `/var/lib/agentpost` 的映射

### 12.4 前端非目标（第一期）

- 不内置模型对话窗当 ChatGPT  
- 不做拖拽编排多智能体流程图  
- 不要求移动端原生 App（响应式可用即可）

---

## 13. CLI 详细功能

二进制名：`agentpost`。两种后端模式：

1. **远程模式（默认）**：`--api http://localhost:8080 --token ...` 调 HTTP API  
2. **本地卷模式（调试）**：`--root /var/lib/agentpost` 直接读挂载卷；**写操作仍必须落到某盒 outbox**，若本机没有 daemon，CLI 应警告「文件已入队但无人投递」

配置文件（可选）`~/.agentpost/config.toml`：

```toml
api = "http://localhost:8080"
token = ""          # 不建议明文长期放；可用环境变量 AGENTPOST_TOKEN
format = "table"    # table | json
```

环境变量：`AGENTPOST_API`、`AGENTPOST_TOKEN`、`AGENTPOST_ROOT`、`AGENTPOST_ACT_AS`。

### 13.1 命令一览

**系统**

```text
agentpost version
agentpost health
agentpost doctor [--repair]
agentpost compose-ps          # 包装 docker compose ps，方便排障（可检测 compose 项目名）
```

**盒子生命周期（operator）**

```text
agentpost register --id coder-02 --name "编码员" --summary "..." --cap code --cap review
agentpost list
agentpost show coder-02
agentpost pause coder-02
agentpost resume coder-02
agentpost revoke coder-02
agentpost token rotate coder-02
```

`register` 把 token 打印到 stderr，并支持 `--write-token ./secrets/coder-02.token`（文件权限 0600）。

**邮件**

```text
agentpost inbox [--box coder-02] [--folder cur] [--unread]
agentpost read <message_id> [--box coder-02]
agentpost ack <message_id>
agentpost compose --to bob@agentpost.local --subject "..." --body-file ./n.md \
                 [--type request] [--label api] [--attach ./errors.csv] [--ack]
agentpost reply <message_id> --body-file ./r.md
agentpost outbox [--folder sent|failed|new]
agentpost thread <thread_id>
```

`compose` / `reply` 内部：构造消息 → `POST /outbox`。不要 `cp` 到对方 inbox。

**观察**

```text
agentpost tail [--box coder-02] [--events mail.*,skills.*]
agentpost logs [--box coder-02] [--follow]
agentpost queue
agentpost retry <dead_letter_id>
agentpost addrbook
```

`tail` 挂 WebSocket/SSE，Ctrl+C 退出；JSON 行模式 `--json` 便于脚本。

**盒子内文件（受路径守卫）**

```text
agentpost ls data/inbound
agentpost cat memory/semantic/outbox-status.json
agentpost put data/notes/today.md ./today.md
```

### 13.2 CLI 行为约定

- 默认人类可读表；`--json` 给脚本  
- 非 2xx 以非零码退出，错误写 stderr  
- `compose` 成功退出码 0 只表示**已受理**，不表示已投递；加 `--wait-receipt --timeout 10s` 可阻塞到回执  
- 所有 `--box` 在 box token 下可省略（用令牌所属盒）  
- 不提供 `agentpost cp-inbox` 这类后门命令

### 13.3 与 Compose 的配合

```text
docker compose exec api agentpost health
docker compose exec api agentpost register --id alice --summary "demo"
docker compose exec api agentpost compose --box alice --to bob@agentpost.local --subject ping --body-file - 
```

镜像内包含 CLI。宿主机也可把同一 CLI 指到 `http://localhost:8080`。

---

## 14. Docker Compose 常驻部署

仓库必须提供可直接使用的 `docker-compose.yml`（及 `Dockerfile`）。目标：`docker compose up -d` 后服务一直跑，刷新浏览器、再用 CLI 发信都不必手工起 daemon。

### 14.1 服务拓扑

```text
services:
  api:        # agentpostd + HTTP API（可同容器）
  web:        # nginx 或 node 静态站，反代 /api 与 /stream
  # worker 示例可在 examples/compose 用 profile 启用
volumes:
  agentpost-data:
networks:
  agentpost:
```

最小 `docker-compose.yml` 规格：

```yaml
name: agentpost

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
      target: api
    container_name: agentpost-api
    restart: unless-stopped
    environment:
      AGENTPOST_ROOT: /var/lib/agentpost
      AGENTPOST_DOMAIN: agentpost.local
      AGENTPOST_API_HOST: 0.0.0.0
      AGENTPOST_API_PORT: 8765
      AGENTPOST_OPERATOR_TOKEN: ${AGENTPOST_OPERATOR_TOKEN:?set operator token}
      AGENTPOST_AUTO_INIT: "true"
    volumes:
      - agentpost-data:/var/lib/agentpost
    ports:
      - "8765:8765"
    healthcheck:
      test: ["CMD", "agentpost", "health"]
      interval: 10s
      timeout: 3s
      retries: 8
      start_period: 8s
    networks: [agentpost]

  web:
    build:
      context: .
      dockerfile: Dockerfile
      target: web
    container_name: agentpost-web
    restart: unless-stopped
    depends_on:
      api:
        condition: service_healthy
    ports:
      - "8080:80"
    networks: [agentpost]

volumes:
  agentpost-data:

networks:
  agentpost:
```

可选 profile `workers`：

```yaml
  worker-alice:
    profiles: ["workers"]
    build: {context: ., dockerfile: Dockerfile, target: worker}
    restart: unless-stopped
    environment:
      AGENTPOST_API: http://api:8765
      AGENTPOST_BOX_ID: alice
      AGENTPOST_TOKEN: ${ALICE_TOKEN}
    depends_on:
      api: {condition: service_healthy}
    networks: [agentpost]
```

Worker 容器**不要**挂载整个 `agentpost-data`。只应通过 API 访问本盒；若必须挂卷，用单独 volume 或只读 bind 到 `boxes/alice`。

### 14.2 镜像分层

同一 Dockerfile 多 target：

- `api`：守护进程 + CLI  
- `web`：nginx + 前端构建产物，`/api` proxy_pass 到 `api:8765`，WebSocket 升级  
- `worker`：参考扫描循环

以非 root 用户运行。数据卷目录启动时 chown 到该用户（entrypoint 处理）。

### 14.3 环境与密钥

`.env.example`：

```text
AGENTPOST_OPERATOR_TOKEN=change-me
AGENTPOST_DOMAIN=agentpost.local
# ALICE_TOKEN=  # register 之后再填，用于 worker profile
```

禁止把 box token 打进镜像层。

### 14.4 运维命令（写入 README）

```text
cp .env.example .env
docker compose up -d --build
docker compose ps
docker compose logs -f api
agentpost --api http://localhost:8080 --token $AGENTPOST_OPERATOR_TOKEN health
docker compose down          # 停进程，保留 volume
docker compose down -v       # 销毁数据（文档里用红字警告）
```

升级：先 `compose pull/build`，再 `up -d`。守护进程必须能在旧目录上启动（目录多出来的文件夹可忽略，缺的由 doctor --repair 补）。

### 14.5 持续运行要求

- PID 1 用能转交信号的 entrypoint，容器 stop 时触发第 11.1 节优雅退出  
- watcher 断掉要自动重挂（日志报错，不退出进程，除非连续失败超过阈值）  
- spool/retry 后台循环，间隔可配  
- 磁盘满、权限错误：health 变 degraded，不进入忙等死循环打满 CPU  
- `restart: unless-stopped` + healthcheck，保证宿主机重启后邮局仍在

---

## 15. 配置 agentpost.yaml（示例）

```yaml
domain: agentpost.local
root: /var/lib/agentpost
watch_interval_ms: 500
max_attachment_bytes: 10485760
max_message_bytes: 2097152
api:
  host: 0.0.0.0
  port: 8765
  cors_origins: ["http://localhost:8080"]
scan:
  default_interval_sec: 15
security:
  require_from_match: true
  allow_broadcast: false
  script_timeout_sec: 5
receipts:
  always_on_reject: true
  on_deliver_if_ack: true
```

环境变量覆盖同名配置。Compose 以环境变量为准。

---

## 16. 参考实现技术选型（建议，可替换但需说明）

- 服务端：Python 3.11+（FastAPI + watchdog）或 Go（chi/echo + fsnotify）。选定一种作为主实现。
- 前端：React 或 Vue SPA，构建进 nginx 镜像。
- CLI：与 API 同语言，保证一套 DTO。
- 监视：inotify / watchdog。
- 原子写：先写 `tmp/` 再 `os.replace`。
- 注册表：jsonl + 定期 snapshot JSON。
- 测试：用临时目录 + Testcontainers/Compose 做端到端，不依赖真实 LLM。
- `agentpost.sdk`：`BoxClient(api_base, token)`，方法仅限本盒操作。

---

## 17. MVP 范围（必须一次交付）

必须同时具备：

1. `docker compose up -d` 后 api + web 常驻，health 为绿  
2. 前端能用 operator token 登录、注册 alice/bob、打开收件箱  
3. CLI 能 register / compose / inbox / tail  
4. A 写信 → daemon 转发 → B inbox → skills → B 可见；前端与 CLI 都能看到  
5. 伪造 `from` 被拒；未知地址退信 + receipt  
6. 附件落在 B 的 `data/inbound/...`，前端可下载  
7. 参考 Worker（compose profile 或 CLI 循环）能回信  
8. Box token 无法列举其他盒子文件  
9. `doctor` 能发现缺目录、卡死在 tmp 的文件  
10. `compose down` 后再 `up`，已有盒子与未投完 spool 可恢复  

明确不做（第一期）：

- 真实 SMTP/IMAP
- 跨机器多节点复制
- 群聊房间、共享白板
- 自动用大模型写回信（Worker 留插件口，默认规则回复）
- 复杂可视化编排画布

---

## 18. 验收剧本（按此写集成测试）

**剧本 A：问路（协议）**

1. 注册 `alice@agentpost.local`、`bob@agentpost.local`  
2. alice 向 bob 发 `type: request`  
3. bob `inbox/cur` 出现该信，alice `outbox/sent` 有归档  
4. bob skill 建索引；Worker 回复；alice 收到 `type: reply` 且 `in_reply_to` 正确  

**剧本 B：隔离**

1. alice token 调 `GET /boxes/bob/inbox` → 403  
2. alice SDK/CLI `ls ../bob/inbox` → 拒绝  

**剧本 C：伪造发件人 / 未知收件人**

同原规范：failed + receipt，收件人无信。

**剧本 D：三端一致**

1. Compose 启动  
2. 前端注册 carol  
3. CLI 用 carol 发信给 alice  
4. 前端 alice 收件箱经 WS 出现新信  
5. 重启 `docker compose restart api` 后队列与盒子仍在  

**剧本 E：常驻**

1. `up -d` 后 60s 内不要退出  
2. kill api 主进程，Compose 拉起，health 恢复  
3. `down` 不带 `-v`，数据卷仍在  

---

## 19. 文档（随代码交付）

- `README.md`：`compose up`、打开 `localhost:8080`、CLI 发一封信  
- `SPEC.md`：目录、消息头、API 一览  
- `SECURITY.md`：token、路径守卫、脚本沙箱、卷挂载风险  
- `deploy/docker-compose.yml`、`Dockerfile`、`.env.example`  
- `examples/two-agents/`：alice / bob 的 AGENT.toml、skill、worker  

---

## 20. 仓库结构建议

```text
agentpost/
  cmd/agentpostd/          # 守护 + API 入口
  cmd/agentpost/           # CLI
  internal/ 或 pkg/
    api/
    daemon/
    boxfs/
    message/
    registry/
    router/
    skills/
    receipts/
    events/
    sdk/
    worker/
  web/                    # 前端
  deploy/
    docker-compose.yml
    nginx.conf
  Dockerfile
  testdata/
  examples/two-agents/
```

日志字段保持稳定：`message_id`, `box`, `stage`（accept|validate|skill_send|deliver|skill_recv|ack）。

---

## 21. 给你的工作方式

1. 目录规范 + 消息解析单测。  
2. daemon 投递闭环（无 UI 也能用 CLI/文件完成）。  
3. HTTP API + 鉴权 + WS 事件。  
4. CLI 接 API。  
5. 前端最小控制台（登录、盒子、收件、写信、队列）。  
6. Docker Compose 多阶段镜像、healthcheck、数据卷、重启策略。  
7. 用剧本 D/E 做集成测试。  

任何时候不确定，选更简单、更像邮件、更少共享状态的方案。三端都不得开辟第二条投递通道。

开始实现。先交付 `compose up -d` 能起来的骨架（health + 空控制台 + CLI health），再接注册与投递。
