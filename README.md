# AgentPost

本地优先的多智能体邮局。多个智能体各自待在独立工作区（SubBox）里干活，不共享目录、不互相扫盘、不直接写对方磁盘。唯一合法通道是 AgentPost 的本地邮箱。

协议版本 `agentpost/1`，软件版本 `0.1.0`。只投递本地域名下已注册的邮箱，默认域名可配置（`agentpost.local`）。

隐喻：邮局（daemon）+ 私人邮箱（SubBox）+ 邮件规则（skills）+ 收件人本人（agent loop）。

| 文档 | 说明 |
|------|------|
| [agentpost_skills.md](agentpost_skills.md) | **📖 完整指南**（自包含）：环境检查 → 部署 → 通信 → Skills → 新 Agent 接入模板 |
| [AGENTPOST_GUIDE.md](AGENTPOST_GUIDE.md) | 智能体收发信速查手册 |
| [SPEC.md](SPEC.md) | 协议与 API 全表 |
| [SECURITY.md](SECURITY.md) | 安全模型 |
| [docs/ACCEPTANCE_REPORT.md](docs/ACCEPTANCE_REPORT.md) | 项目验收总结报告 |

> **给 code agent**：只需读取 `agentpost_skills.md` 一份文件即可完成环境检查、实例部署、消息收发、Skills 构建和新 Agent 接入。无需依赖其他文件。

## 快速开始

### 方式一：从预构建镜像启动（推荐）

无需克隆仓库，直接拉取镜像运行：

```bash
# 1. 创建实例目录
mkdir mypost && cd mypost

# 2. 下载 compose 文件
curl -sL https://raw.githubusercontent.com/AgenticEconomics/agentpost/main/docker-compose.pull.yml \
  -o docker-compose.yml

# 3. 创建 .env
cat > .env <<'ENV'
INSTANCE_NAME=mypost
AGENTPOST_DOMAIN=mypost.local
AGENTPOST_OPERATOR_TOKEN=替换为一长串随机字符串
API_PORT=8765
WEB_PORT=58080
IMAGE_REGISTRY=ghcr.io/AgenticEconomics
IMAGE_TAG=0.1.0
ENV

# 4. 启动
docker compose up -d
```

> **中国大陆加速**：将 `IMAGE_REGISTRY` 改为 `crpi-9dwgg7k88349acd7.cn-hangzhou.personal.cr.aliyuncs.com/agenticeconomics`。

镜像地址：

| 镜像 | 地址 |
|------|------|
| API + 投递引擎 + CLI | `ghcr.io/AgenticEconomics/agentpost-api:0.1.0` |
| 控制台（nginx） | `ghcr.io/AgenticEconomics/agentpost-web:0.1.0` |
| 参考 Worker | `ghcr.io/AgenticEconomics/agentpost-worker:0.1.0` |

> **中国大陆加速**：如 ghcr.io 拉取缓慢，切换到阿里云 ACR 镜像源——在 `.env` 中设置：
> ```
> IMAGE_REGISTRY=crpi-9dwgg7k88349acd7.cn-hangzhou.personal.cr.aliyuncs.com/agenticeconomics
> IMAGE_TAG=0.1.0
> ```
> 镜像名和版本与 ghcr.io 完全一致，仅仓库地址不同。

### 方式二：从源码构建（开发者）

```bash
cp .env.example .env
# 编辑 .env，设置 AGENTPOST_OPERATOR_TOKEN（快捷生成: openssl rand -hex 32）
docker compose up -d --build
```

### 验证

```bash
curl http://localhost:8765/api/v1/health
```

`status: ok` 且 `ready: true` 即可。OpenAPI 文档：http://localhost:8765/docs

| 服务 | 容器 | 宿主机 |
|------|------|--------|
| API + 投递引擎 | `<实例名>-api` | http://localhost:8765 |
| 控制台（nginx） | `<实例名>-web` | http://localhost:58080 |

数据在 Docker 卷 `<实例名>-data`，容器内路径 `/var/lib/agentpost`。

### 打开控制台

浏览器打开 http://localhost:58080 ，用 `.env` 里的 Operator Token 登录。登录页也可以选「盒子」角色，填 Box Token 和盒子 ID，只看自己的邮箱。

### 用 CLI 发一封信

API 容器里已安装命令 `agentpost`（即 `python -m app.cli`）：

```bash
export AGENTPOST_TOKEN='与 .env 中相同的 Operator Token'

docker compose exec -e AGENTPOST_TOKEN api agentpost register \
  --id alice --name "Alice" --summary "研究员"
docker compose exec -e AGENTPOST_TOKEN api agentpost register \
  --id bob --name "Bob" --summary "编码员"
```

注册成功会打印 **Box Token，只此一次**。之后用各自的 Box Token 收发信。

```bash
# 下面改用 alice 的 Box Token
docker compose exec -e AGENTPOST_TOKEN="$ALICE_TOKEN" api agentpost compose \
  --box alice \
  --to bob@<你的域名> \
  --subject "Hello" \
  --body "你好，这是一封测试信。"

# CLI 默认列出 inbox/new（未读信）
docker compose exec -e AGENTPOST_TOKEN="$BOB_TOKEN" api agentpost inbox --box bob
```

### 宿主机 CLI（可选）

```bash
pip install -r backend/requirements.txt
cd backend && export PYTHONPATH=.
export AGENTPOST_API=http://localhost:8765
export AGENTPOST_TOKEN='Operator Token 或 Box Token'

python -m app.cli health
python -m app.cli list
```

也可把 `api`、`token`、`act_as` 写进 `~/.agentpost/config.toml`。同名环境变量优先。

## 多实例部署

同一台机器上可以并行运行多个 AgentPost 实例，各自独立的容器、数据卷、网络和域名。适合不同团队或项目的智能体分组通信。

### 快速创建实例

```bash
./scripts/new-instance.sh xingu 8765 58080
./scripts/new-instance.sh jarvik 18765 58081
```

每个实例生成独立目录，包含 `.env` 和 `docker-compose.yml`：

```bash
cd xingu && docker compose up -d    # xingu.local → :8765 / :58080
cd jarvik && docker compose up -d   # jarvik.local → :18765 / :58081
```

### 实例隔离维度

| 变量 | 作用 | 默认值 |
|------|------|--------|
| `INSTANCE_NAME` | 容器/卷/网络前缀 | `agentpost` |
| `AGENTPOST_DOMAIN` | 邮箱域名 | `agentpost.local` |
| `API_PORT` | API 宿主机端口 | `8765` |
| `WEB_PORT` | 控制台宿主机端口 | `58080` |
| `IMAGE_REGISTRY` | 镜像源 | `ghcr.io/AgenticEconomics` |
| `IMAGE_TAG` | 镜像版本 | `0.1.0` |

## 架构

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
           alice           bob            ...
           SubBox         SubBox         SubBox
```

API 进程同时跑投递引擎。智能体通过 HTTP 读写自己的盒子；引擎是唯一把信从一只盒子搬到另一只盒子的进程。

## 核心概念

- **SubBox**：一只智能体的工作区。地址形如 `alice@<域名>`。内含 `inbox/`、`outbox/`、`data/`、`memory/`、`skills/`、`work/`。
- **邮件**：一个文件，YAML front matter + Markdown 正文，协议 `agentpost/1`。
- **投递**：`outbox/new` → 校验 `from`、跑 on_send skills → 抄到收件人 `inbox/new` → 原件进 `outbox/sent`。需要回执时，`postmaster` 把 receipt 投回发件人的 `inbox/new`。
- **Ack**：收件人显式调用后，信才从 `inbox/new` 挪到 `inbox/cur/seen`。skills 会建索引、存附件，但不会移动邮件文件。
- **Skills**：盒子级钩子，不依赖 LLM。默认启用 `builtin.validate_headers`、`builtin.classify`、`builtin.save_attachments`、`builtin.file_bounce`。自定义 skills 见 [agentpost_skills.md](agentpost_skills.md)。
- **两种令牌**：Operator Token 管全局；Box Token 只能访问自己的盒子。系统只存 Box Token 的 SHA-256。

## 目录

```
agentpost/
  backend/app/          # FastAPI、投递引擎、CLI、SDK
  web/                  # React 控制台
  deploy/               # nginx、容器入口
  scripts/              # new-instance.sh 等运维脚本
  examples/two-agents/  # alice/bob 样例信与 AGENT.toml
  agentpost.yaml        # 配置模板
  docker-compose.yml    # 开发/本地构建用
  docker-compose.pull.yml  # 生产部署用（纯 ghcr.io 镜像）
  SPEC.md               # 协议与 API 全表
  SECURITY.md           # 安全模型
  AGENTPOST_GUIDE.md    # 智能体收发信速查手册
  agentpost_skills.md   # 📖 完整自包含指南（环境检查 + 部署 + 通信 + Skills + 接入模板）
```

运行时数据根（默认 `/var/lib/agentpost`）：

```
registry/agents.jsonl    # 注册表
addrbook/public.json     # 公开地址簿
boxes/<id>/              # SubBox
spool/{incoming,retry,dead-letter}/
logs/
```

## CI/CD

推送至 `main` 分支或打 `v*` 标签时，GitHub Actions 自动构建三镜像并推送至 `ghcr.io/AgenticEconomics`：

- `agentpost-api` — FastAPI + 投递引擎 + CLI
- `agentpost-web` — React 控制台（nginx）
- `agentpost-worker` — 参考 Worker

Workflow 定义：`.github/workflows/build-push.yml`

## 运维

```bash
docker compose up -d          # 启动（pull 镜像或 build）
docker compose ps
docker compose logs -f api
docker compose restart api    # 数据保留
docker compose down           # 停止，卷保留
docker compose down -v        # ⚠️ 停止并删除全部邮箱数据

# 参考 Worker
ALICE_TOKEN=<token> docker compose --profile workers up -d worker-alice
```

常用 Operator 命令：`register`、`list`、`show`、`pause`、`resume`、`revoke`、`token-rotate`、`doctor`、`queue`。

## 技术栈

Python 3.11、FastAPI、uvicorn、Typer、Rich；React 18、TypeScript、Vite、Tailwind CSS；Docker Compose、nginx。

## 许可证

Apache License 2.0，见 [LICENSE](LICENSE)。
