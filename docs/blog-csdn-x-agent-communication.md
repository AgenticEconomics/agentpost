# 多智能体不会说话：我们为什么做了一个本地邮局

> 适合发表在 CSDN 的完整长文。文末附 X / Twitter 短帖与线程版。
>
> 项目：[github.com/AgenticEconomics/agentpost](https://github.com/AgenticEconomics/agentpost)
> 协议：`agentpost/1`　软件版本：`0.1.0`　许可：Apache 2.0

---

单智能体已经够用了吗？对写一段脚本、改一个函数、总结一份文档，够了。一旦任务跨出一个人的工作台——调研要交结论、编码要接需求、审查要回意见、运维要收告警——问题立刻变成另一件事：

**Agent 之间怎么通信？**

这不是「再加一个 LLM 调用」能解决的。它是身份、隔离、投递、回执、审计，一整个通信层的问题。AgentPost 就是为这一层做的：一个本地优先的多智能体邮局。

---

## 一、Agent 通信，为什么突然变成问题

2024–2026，智能体从「对话框里的助手」变成「能长时间干活的进程」。一个人可以同时跑研究员、编码员、审查员、运维员。框架也越来越多：LangGraph、AutoGen、CrewAI、各种自研 loop。

但通信这一层，现场往往还是这几种做法：

**1. 共享目录**

几个 Agent 扫同一个 `workspace/`，谁先写谁算、谁覆盖谁倒霉。没有身份，没有收件箱，没有「这封信是谁发给谁的」。调试时只能翻 git diff 和散落的 markdown。

**2. 共享上下文 / 共享内存**

把所有人的对话塞进同一个 context window，或者塞进 Redis。短期能跑通，长期不可审计：谁在什么时候对谁说了什么，事后很难还原。上下文一长，幻觉和串台一起出现。

**3. 直接调对方的 API / 函数**

同步 RPC。调用方必须知道被调方活着、接口没变、超时怎么处理。Agent 的节奏偏偏是异步的：它可能在想、在跑命令、在等人。把异步工作者硬接成同步调用，系统会又脆又吵。

**4. Slack / 飞书 / Discord 当总线**

能用，而且人能看见。但频道是广播，权限是平台的，消息是平台的，附件和审计也是平台的。你要的是「alice 只给 bob 一封带附件的请求，并拿到投递回执」，不是「再开一个群」。

**5. MCP、A2A 等新协议**

方向是对的：给工具和智能体一个标准接口。它们解决的是「怎么连上模型和工具」，不是「一屋子本地 Agent 如何像人一样写信、回信、归档，并且互不进对方的磁盘」。

把这些做法叠在一起，现场会变成这样：

```
researcher ──扫──► /shared/docs
coder      ──写──► /shared/src     ← 两人同时改同一份文件
reviewer   ──读──► /shared/*       ← 看见还没写完的半成品
ops        ──听──► webhook / slack ← 告警和任务混在一个频道
```

没有信封，没有投递，没有回执。出了问题，你甚至说不清「那句话」是请求、回复，还是某次误扫产生的副作用。

人解决过这个问题。答案不是再发明一种 RPC，而是**邮局**。

---

## 二、人已经用过正确答案：写信，而不是共用一张桌子

电子邮件能活到今天，不是因为它快，而是因为它把几件事拆开了：

| 人的邮局 | 对应到 Agent |
|---------|--------------|
| 每人一个邮箱地址 | `alice@team.local` |
| 信有 From / To / Subject | 身份、意图、线程都可检索 |
| 投递是邮局的事，不是发件人自己塞进对方抽屉 | 唯一跨盒子的进程是 daemon |
| 回执、退信、抄送 | 投递可验证，失败可归档 |
| 附件是信的一部分，不是共享盘上的幽灵文件 | 附件进对方的 `data/inbound/` |
| 处理完标记已读 | 显式 ack，消息才离开未读 |

Agent 需要的正是这些，而不是「更快的共享文件夹」。

所以 AgentPost 的隐喻非常克制：

> **邮局（daemon）+ 私人邮箱（SubBox）+ 邮件规则（skills）+ 收件人本人（agent loop）。**

多个智能体各自待在独立工作区里干活，不共享目录、不互相扫盘、不直接写对方磁盘。**唯一合法通道是本地邮箱。**

这不是复古，是把通信从「副作用」变回「一等公民」。

---

## 三、为什么要专门做这个开源项目

如果只是 demo，用 Redis 队列加两行 prompt 也能演一出「多智能体」。做成开源邮局，是因为生产里缺的不是 demo，而是下面这些可检查的性质。

### 1. 本地优先，数据在你自己的磁盘上

默认域名是可配置的本地域（例如 `agentpost.local` / `mypost.local`）。只投递本域已注册的邮箱，不把信送到公网。API、投递引擎、控制台都可以在一台机器的 Docker Compose 里跑起来。

数据在 Docker 卷里，容器内路径是 `/var/lib/agentpost`。备份就是备份这个目录。没有「对话被某一家云记了一份」的默认假设。

对研究团队、内部工具链、不能出境的业务数据，这是前提，不是特性列表里的一行小字。

### 2. 隔离是默认值，不是事后补丁

每个 Agent 一只 **SubBox**：

```
boxes/<id>/
  AGENT.toml          # 身份
  inbox/new|cur/seen  # 收件
  outbox/new|sent|failed
  data/               # 附件与产物
  memory/             # 索引与结构化记忆
  skills/             # 收发钩子
  work/               # 自己的工作区
```

Box Token 只能访问 `/boxes/{自己的id}/...`，读别人的盒子是 403。系统只存 Token 的 SHA-256，明文只在注册时出现一次。`from` 必须等于自己的地址，伪造发件人会进 `outbox/failed`，并由 `postmaster` 拒信。

路径有 `guard_path()`，拒绝 `../` 逃逸。Worker 不应该挂上整卷数据盘——它通过 API 访问自己的盒子。投递引擎是**唯一**把信从一只盒子搬到另一只盒子的进程。

这些约束让「多智能体」不再等于「多进程共享一个 root」。

### 3. 消息是文件，协议是邮件，而不是瞬时 JSON

一封信是一个文件：YAML front matter + Markdown 正文。协议名就叫 `agentpost/1`。

```yaml
---
protocol: agentpost/1
message_id: "<20260929.1727590000123.alice@agentpost.local>"
from: "alice@agentpost.local"
to:
  - "bob@agentpost.local"
subject: "请核对 API 错误码表"
date: "2026-09-29T07:34:00Z"
type: request
priority: normal
thread_id: "thr-api-errcode"
routing:
  ack: true
labels:
  - api
---

ERR_4001 后端返回 invalid_token，文档写的是 auth_failed。请核对。
```

`type` 只有几种：`request` / `reply` / `event` / `receipt` / `artifact` / `system`。线程靠 `thread_id` 和 `in_reply_to`。附件带名字、路径、sha256。

这意味着：

- 人可以用编辑器打开任何一封信
- Agent 可以用同一套 CLI / HTTP / SDK 读写
- 出了问题可以按文件做审计，而不是在日志里拼 JSON 碎片
- 备份、导出、diff、grep 全部免费获得

### 4. 投递和「看过」是两件事

发信成功返回的是 `accepted`：信进了 `outbox/new`，daemon 大约每 500ms 扫一次。投完后原件进 `outbox/sent`；需要回执时，`postmaster` 把 `receipt` 投回发件人的 `inbox/new`。

收件人必须**显式 ack**，信才从 `inbox/new` 挪到 `inbox/cur/seen`。Skills 可以建索引、存附件，但不会替你把信移走。不 ack，下一次轮询还是同一封。

这避免了一种常见事故：预处理脚本「顺手」把未处理的任务标成已读，主循环永远看不见。

推荐循环只有四步，刻意写进了手册：

```
1. 列 inbox/new
2. 读全文 → 干活 → 必要时回复
3. ack
4. 若请求了回执，在自己的 inbox 里查 type=receipt
```

### 5. Skills 是邮局规则，不是又一个 Agent

信进出时可以跑钩子：`on_send` / `on_receive` / `on_bounce`。默认就有校验头、分类索引、保存附件、退信归档、回执索引。

自定义 skill 是盒子里的可执行文件，stdin/stdout 走 JSON，超时 5 秒，工作目录锁在本盒，默认无网络。它不调用 LLM。该过滤的过滤，该抄到 `data/tasks/api/` 的抄过去，该给高优先级写 `data/alerts/latest.json` 的写下去。

主循环仍然是「收件人本人」。Skills 只做邮件规则该做的事。

### 6. 人要能看见，Agent 要能接入

同一套系统有三副面孔：

- **Web 控制台**：Operator Token 看全局盒子、队列、地址簿；Box Token 只看自己的邮箱。登录态放在 sessionStorage，关标签即清。
- **CLI `agentpost`**：register / inbox / compose / reply / ack / doctor / queue……
- **HTTP API + Python SDK + WebSocket**：Agent 用 `BoxClient` 写十行就能进主循环；控制台和脚本可以订 ` /api/v1/stream`。

给人看的界面和给 Agent 用的接口，操作的是同一只盒子、同一封文件。这很重要：协作出了问题，人可以打开那封信，而不是猜 prompt。

### 7. 多实例是团队边界，不是微服务秀

同一台机器可以并行跑多个实例，各自独立的容器、数据卷、网络和域名：

```bash
./scripts/new-instance.sh xingu 8765 58080
./scripts/new-instance.sh jarvik 18765 58081
```

`xingu.local` 和 `jarvik.local` 互不可见。适合不同项目、不同安全域，避免「全公司 Agent 挤进同一个邮局」。当前刻意不做跨实例投递——单实例边界清晰，比过早做联邦更诚实。

---

## 四、它在架构上长什么样

```
浏览器 :58080          CLI / SDK / Worker
      │                      │
      ▼                      ▼
 nginx (web)            FastAPI :8765
      │                      │
      └──────── /api ────────┤
                             │  同进程
                      DeliveryEngine
                      每 500ms 扫 outbox/new
                             │
              ┌──────────────┼──────────────┐
              ▼              ▼              ▼
           alice           bob            reviewer
           SubBox         SubBox         SubBox
```

API 进程同时跑投递引擎。智能体只通过 HTTP 读写自己的盒子。引擎是唯一的搬运工。

鉴权是两种令牌，而不是「一个上帝密钥加注释」：

| 令牌 | 谁用 | 能做什么 |
|------|------|----------|
| Operator Token | 人 / 运维 | 注册、暂停、吊销、轮换、看队列和指标 |
| Box Token | 某只盒子 | 只读写自己的 inbox / outbox / data / memory / skills |

技术栈也很普通，这是有意的：Python 3.11、FastAPI、Typer；React 18、Vite、Tailwind；Docker Compose、nginx。普通意味着 Agent 容易接、人容易修、机器容易部署。

镜像在 GitHub Container Registry，国内可以切到阿里云 ACR。不必先克隆仓库：

```bash
mkdir mypost && cd mypost
curl -sL https://raw.githubusercontent.com/AgenticEconomics/agentpost/main/docker-compose.pull.yml \
  -o docker-compose.yml
# 写好 .env 里的 INSTANCE_NAME / DOMAIN / OPERATOR_TOKEN / 端口
docker compose up -d
curl http://localhost:8765/api/v1/health
```

`status: ok` 且 `ready: true` 就可以注册前两只盒子，开始写信。

---

## 五、应用实例

下面几个场景都来自项目真实能力，不是路线图幻想。

### 实例 1：研究员写信，编码员回信

仓库里的 `examples/two-agents/` 就是这个最小闭环。

Alice 的职责是检索和交叉验证，Bob 负责代码和文档。Alice 不进 Bob 的 `work/`，Bob 也不扫 Alice 的 `memory/`。Alice 发出一封 `type: request`：

> 主题：请核对 API 错误码表  
> 标签：`api` `docs`  
> 线程：`thr-api-errcode`  
> 正文：`ERR_4001` 后端是 `invalid_token`，文档是 `auth_failed`；`ERR_5003` 缺中文。

Daemon 把文件抄到 Bob 的 `inbox/new`。Bob 的 loop 读信、改代码、回一封 `type: reply`，`in_reply_to` 指回原信。Alice 在同一线程里看到结论和 PR 说明，然后各自 ack。

人打开控制台，看到的就是这两封信，而不是两段缠在一起的 chain-of-thought。

用 CLI 写出来是这样的：

```bash
# 注册（Operator Token；Box Token 只打印一次）
agentpost register --id alice --name "Alice" --summary "研究员"
agentpost register --id bob   --name "Bob"   --summary "编码员"

# Alice 发信
agentpost compose \
  --box alice \
  --to bob@mypost.local \
  --subject "请核对 API 错误码表" \
  --body "ERR_4001 文档与实现不一致，请核对。" \
  --type request \
  --ack \
  --label api --label docs

# Bob 未读
agentpost inbox --box bob
agentpost read '<message_id>' --box bob
agentpost reply '<message_id>' --box bob --body "已核对，PR 见正文。"
agentpost ack '<message_id>' --box bob
```

Python SDK 同样短：

```python
from app.sdk.client import BoxClient

bob = BoxClient(api_base, bob_token, "bob")
for msg in bob.list_inbox():          # 默认 folder="new"
    full = bob.read_message(msg["message_id"])
    if full["type"] == "request":
        bob.reply(full, body="已核对，修复见正文。")
    bob.ack_message(msg["message_id"])
```

这是 Agent 通信最小、也最有用的形状：**带着身份的异步信件，而不是共享一个文件夹。**

### 实例 2：一个本地软件小队

把角色拆开，仍然共用同一个邮局、同一本地址簿：

| 盒子 | 职责 | 典型信件 |
|------|------|----------|
| `pm` | 拆任务、收齐回执 | `request` 派工，读各人 `receipt` / `reply` |
| `researcher` | 查资料、写摘录 | 向 `coder` 发带附件的需求 |
| `coder` | 改代码 | `reply` + `artifact`（补丁、schema） |
| `reviewer` | 审 diff | 高优先级 `request`，不同意就回 `reply` |
| `docs` | 收结论写文档 | 只订阅带 `docs` 标签的信 |

附件走消息，不走共享盘。schema.json、错误码表、一小段补丁，都可以作为附件投到对方的 `data/inbound/<message_id>/`。需要回执就 `ack: true`，发件人在自己的 inbox 里等 `type: receipt`，或查 outbox 状态。

地址簿是公开的，但只有地址、显示名、摘要、capabilities、状态，**没有 token**。新来的 Agent 先看谁在线、谁会 `review`，再写信——和人加入项目组的方式一样。

### 实例 3：Skills 当分拣员，主循环只处理该看的信

真实团队里不是每封信都值得叫醒 LLM。可以把分拣交给 skill。

例如入站按标签抄到任务目录（项目文档里的完整示例）：

```python
# skills/on_receive/route_by_label
# 按 labels 把信复制到 data/tasks/<label>/
```

再加一个高优先级告警钩子：只有 `priority == high` 时写 `data/alerts/latest.json`。出站用 `builtin.validate_headers` 挡住缺头、假 From、空收件人。退信用 `builtin.file_bounce` 归档。

主 Agent 的 loop 于是可以很窄：

1. 先看 `data/alerts/latest.json` 有没有火情
2. 再处理 `data/tasks/api/` 里的请求
3. 系统欢迎信和 receipt 读完就 ack，不必调用模型

这是邮局该有的能力：**规则在信封上执行，智能花在正文上。**

### 实例 4：人在回路里——控制台就是第三种收件人

不是所有决定都该自动回。审查意见、对外发布、涉及密钥的操作，可以规定：某类信只送到 `human@mypost.local`，或者抄送一只给人用的盒子。

人用浏览器打开 `:58080`，用 Operator Token 看全局，或用 Box Token 只进自己的邮箱：读信、回复、看队列、看文件。WebSocket 推送新信和 skill 结果，不必死刷页面。

同一封 `request`，Agent 可以起草 `reply` 到 `outbox` 之前先停住，等人在控制台确认——协议不用改，只是收件人换成了人。

### 实例 5：两个项目，两座邮局

`xingu` 跑业务后端的智能体，`jarvik` 跑实验模型评测。端口、卷、域名都分开。泄露一只 Operator Token，最坏也只是一座邮局。评测集不会出现在业务 Agent 的 inbox 里。

这比「一个超级 Agent 配复杂 ACL」更接近现实组织：房间分开，门牌分开，信送错了会退回，而不是默默写进隔壁的磁盘。

### 实例 6：把现有 Agent 接进来，而不是重写它

AgentPost 不要求你换成某一种框架。只要进程能发 HTTP，就能成为一只盒子。仓库甚至准备了「给新 Agent 的接入指南模板」：管理员 register 一次，把 Box Token 和域名发给对方，对方按 inbox → read → reply → ack 循环即可。

参考 Worker 已经按这个循环实现：扫 `inbox/new`，系统信和回执直接 ack，业务信处理后再 ack。你可以把它换成 LangGraph 节点、换成自己的 CLI Agent、换成定时脚本。邮局不关心收件人用什么模型。

---

## 六、和常见方案差在哪

| | 共享目录 | 消息队列 | 聊天软件 | AgentPost |
|--|----------|----------|----------|-----------|
| 身份 | 文件名靠自觉 | topic 靠约定 | 账号在平台 | 本域邮箱 + Box Token |
| 隔离 | 几乎没有 | 按队列，磁盘仍共享 | 平台隔离 | SubBox + 路径守卫 |
| 异步 | 靠文件锁 | 天生异步 | 异步 | 异步投递 + 回执 |
| 人可读 | 看文件 | 看 payload | 看聊天记录 | 打开 `.msg.md` |
| 审计 | 无 | 要自建 | 在平台侧 | `logs/audit.jsonl`，不含正文 |
| 本地部署 | 是 | 可以 | 通常不是 | 默认就是 |
| Agent 接入 | 自己扫盘 | 自己写消费者 | Bot API | CLI / HTTP / SDK |

队列仍然有价值，AgentPost 自己也有 spool（incoming / retry / dead-letter）。差别在于：**对 Agent 暴露的不是「请消费这个 topic」，而是「这是你的邮箱」。** 心智模型和人一致，协作接口才能稳定。

---

## 七、现在就能做的最小实验

1. 拉镜像，起一个实例（国内把 `IMAGE_REGISTRY` 换成文档里的 ACR）。
2. 注册 `alice`、`bob`，保存两次出现的 Box Token。
3. 用 CLI 发一封 `request`，在控制台用 Bob 的身份打开 inbox。
4. 回复、ack，回到 Alice 的 inbox 看 receipt。
5. （可选）给 Bob 加一个 `route_by_label` skill，再发一封带 `api` 标签的信，看 `data/tasks/api/`。

十分钟足够建立直觉：信是文件，投递是邮局的事，ack 是收件人的责任。

文档入口：

- 完整自包含指南：仓库根目录 `agentpost_skills.md`（部署、通信、Skills、接入模板）
- 协议与 API：`SPEC.md`
- 安全模型：`SECURITY.md`
- 智能体速查：`AGENTPOST_GUIDE.md`

---

## 八、写在后面

多智能体热起来之后，大家花了很多时间讨论模型、记忆、工具、规划。通信被当成管道，越细越好、越快越好。

管道会泄漏。共享盘会串台。同步调用会把一个慢思考的 Agent 变成整张图的单点。平台聊天记录不属于你。

AgentPost 选择把通信做慢一点、显式一点、本地一点：有地址，有信封，有投递，有回执，有私人抽屉。智能体继续当收件人本人；邮局只做邮局该做的事。

如果你也在让两个以上的 Agent 一起干活，并且已经厌烦了「谁又改了我的文件」，欢迎来用，欢迎来骂，欢迎来补协议。

仓库：https://github.com/AgenticEconomics/agentpost  
许可：Apache License 2.0

---

## 附录 A：CSDN 发布建议

- **标题**：多智能体不会说话：我们为什么开源了一个本地邮局 AgentPost
- **标签**：人工智能、Agent、开源、后端、Docker
- **摘要**（可作文章开头加粗）：单智能体已经能写代码，多智能体却还在共享文件夹里互相踩脚。本文从 Agent 通信的五种常见做法讲起，介绍开源项目 AgentPost——本地优先的多智能体邮局：独立邮箱、异步投递、显式回执，以及几个能直接跑的应用实例。
- **封面**：控制台收件箱截图，或文中的架构 ASCII 图导出。
- 文中 GitHub 链接保持可点；代码块语言标 `yaml` / `bash` / `python`。

---

## 附录 B：X / Twitter 短帖（可直接发）

**单条版（约 280 字，适合中文站）：**

单智能体已经能写代码。多智能体真正缺的不是更强的模型，是通信层。

共享目录会互相覆盖，共享上下文会串台，同步 RPC 等不住一个还在思考的 Agent，把 Slack 当总线则数据和权限都不在你这。

我们开源了 AgentPost：本地优先的多智能体邮局。每只 Agent 一只 SubBox，不共享磁盘；唯一合法通道是邮箱。信是 YAML + Markdown 文件，投递由 daemon 做，处理完必须显式 ack。Skills 是邮件规则，不调用 LLM。

人看控制台，Agent 走 CLI / HTTP / SDK。Apache 2.0。
https://github.com/AgenticEconomics/agentpost

**线程版（8 条，可一条条贴）：**

1/8 多智能体项目里，我见过最常见的事故不是模型笨，而是两个 Agent 共用一个目录。谁先写谁算，出了问题无法回答「这是谁发给谁的」。

2/8 共享内存、同步 RPC、Slack 当总线，各自能跑通 demo。它们缺的是同一组性质：身份、隔离、异步投递、回执、人可以打开原文审计。

3/8 人已经有过答案：邮局。地址、信封、投递、退信、已读。AgentPost 把这套搬到本地：每只智能体一只 SubBox，不扫别人的盘，不写别人的文件。

4/8 一封信就是一个 `.msg.md`：YAML 头 + Markdown 正文。type 只有 request / reply / event / receipt / artifact / system。线程、附件、优先级都在头上。人用编辑器能读，Agent 用同一套 API 能读。

5/8 发信返回 accepted，不是 delivered。daemon 扫 outbox，抄到对方 inbox/new。收件人必须 ack，信才进 seen。Skills 可索引、可存附件，但不准替你把未处理的任务标成已读。

6/8 安全是默认值：Box Token 只能进自己的盒子；from 必须是自己；路径拒绝 .. ；skill 默认无网、5 秒超时。Operator 管邮局，盒子管自己的信。

7/8 能直接跑的用法：研究员写信给编码员；PM / coder / reviewer 小队；skill 按标签分拣；人在控制台当第三收件人；一台机器上 xingu、jarvik 两座互不可见的邮局。

8/8 不绑定任何 Agent 框架。能发 HTTP 就能成为一只盒子。本地 Docker 拉起来就能写第一封信。Apache 2.0。
https://github.com/AgenticEconomics/agentpost
