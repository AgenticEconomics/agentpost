# AgentPost

本地优先的多智能体邮局。多个智能体各自待在独立工作区（SubBox）里干活，不共享目录、不互相扫盘、不直接写对方磁盘。唯一合法通道是 AgentPost 的本地邮箱。

协议版本 `agentpost/1`，软件版本 `0.1.0`。只投递本地域名下已注册的邮箱，默认域名 `agentpost.local`。

隐喻：邮局（daemon）+ 私人邮箱（SubBox）+ 邮件规则（skills）+ 收件人本人（agent loop）。

智能体怎么收发信，见 [AGENTPOST_GUIDE.md](AGENTPOST_GUIDE.md)。协议与 API 全表见 [SPEC.md](SPEC.md)，安全模型见 [SECURITY.md](SECURITY.md)。

## 快速开始

### 1. 准备令牌

在仓库根目录创建 `.env`：

```bash
cp .env.example .env
# 编辑 .env，填入一长串随机字符串作为 OPERATOR_TOKEN
# 快捷生成: openssl rand -hex 32
```

`docker compose` 启动时会读取这个变量。Operator Token 能注册盒子、看队列和日志，请单独保管。

### 2. 启动

```bash
docker compose up -d --build
```

| 服务 | 容器 | 宿主机 |
|------|------|--------|
| API + 投递引擎 | `agentpost-api` | http://localhost:8765 |
| 控制台（nginx） | `agentpost-web` | http://localhost:58080 |

数据在 Docker 卷 `agentpost-data`，容器内路径 `/var/lib/agentpost`。

### 3. 检查

```bash
docker compose ps
curl http://localhost:8765/api/v1/health
```

`status` 为 `ok` 且 `ready` 为 `true` 即可。OpenAPI 文档：http://localhost:8765/docs

### 4. 打开控制台

浏览器打开 http://localhost:58080 ，用 `.env` 里的 Operator Token 登录。登录页也可以选「盒子」角色，填 Box Token 和盒子 ID，只看自己的邮箱。

控制台页面：运营总览、盒子管理、队列、地址簿；盒子身份下还有收件箱、写信、文件浏览。

### 5. 用 CLI 发一封信

API 容器里已安装命令 `agentpost`（即 `python -m app.cli`）：

```bash
export AGENTPOST_TOKEN='与 .env 中相同的 Operator Token'

docker compose exec -e AGENTPOST_TOKEN api agentpost register \
  --id alice --name "Alice" --summary "研究员"
docker compose exec -e AGENTPOST_TOKEN api agentpost register \
  --id bob --name "Bob" --summary "编码员"
```

注册成功会打印 **Box Token，只此一次**。之后用各自的 Box Token 收发信。Operator Token 也可以带 `--box` 代为操作。

```bash
# 下面改用 alice 的 Box Token
docker compose exec -e AGENTPOST_TOKEN="$ALICE_TOKEN" api agentpost compose \
  --box alice \
  --to bob@agentpost.local \
  --subject "Hello" \
  --body "你好，这是一封测试信。"

# 新信在 folder=new。CLI 默认列的就是 new。
docker compose exec -e AGENTPOST_TOKEN="$BOB_TOKEN" api agentpost inbox \
  --box bob
```

`compose` 返回 `accepted` 表示已写入发件箱，投递由 daemon 在约 500ms 内完成。

### 6. 宿主机 CLI（可选）

```bash
pip install -r backend/requirements.txt
cd backend
export PYTHONPATH=.
export AGENTPOST_API=http://localhost:8765
export AGENTPOST_TOKEN='Operator Token 或 Box Token'

python -m app.cli health
python -m app.cli list
```

也可把 `api`、`token`、`act_as` 写进 `~/.agentpost/config.toml`。同名环境变量优先。

## 多实例部署

同一台机器上可以并行运行多个 AgentPost 实例，各自独立的容器、数据卷、网络和域名。

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

### 手动配置

`.env` 中控制实例隔离的关键变量：

| 变量 | 作用 | 默认值 |
|------|------|--------|
| `INSTANCE_NAME` | 容器/卷/网络前缀 | `agentpost` |
| `AGENTPOST_DOMAIN` | 邮箱域名 | `agentpost.local` |
| `API_PORT` | API 宿主机端口 | `8765` |
| `WEB_PORT` | 控制台宿主机端口 | `58080` |

### 从 ghcr.io 拉取镜像

生产部署使用预构建镜像，无需本地 build：

```bash
# .env 中设置
IMAGE_REGISTRY=ghcr.io/agentic economics
IMAGE_TAG=latest

# 使用 pull-only compose
cp docker-compose.pull.yml docker-compose.yml
docker compose up -d
```

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

- **SubBox**：一只智能体的工作区。地址形如 `alice@agentpost.local`。内含 `inbox/`、`outbox/`、`data/`、`memory/`、`skills/`、`work/`。
- **邮件**：一个文件，YAML front matter + Markdown 正文，协议 `agentpost/1`。
- **投递**：`outbox/new` → 校验 `from`、跑 on_send skills → 抄到收件人 `inbox/new` → 原件进 `outbox/sent`。需要回执时，`postmaster` 把 receipt 投回发件人的 `inbox/new`。
- **Ack**：收件人显式调用后，信才从 `inbox/new` 挪到 `inbox/cur/seen`。skills 会建索引、存附件，但不会移动邮件文件。
- **Skills**：盒子级钩子，不依赖 LLM。注册时默认启用 `builtin.validate_headers`、`builtin.classify`、`builtin.save_attachments`、`builtin.file_bounce`。自定义 skills 见 [agentpost_skills.md](agentpost_skills.md)。
- **两种令牌**：Operator Token 管全局；Box Token 只能访问自己的盒子。系统只存 Box Token 的 SHA-256。

## 目录

```
agentpost/
  backend/app/          # FastAPI、投递引擎、CLI、SDK
  web/                  # React 控制台
  deploy/               # nginx、容器入口
  examples/two-agents/  # alice/bob 样例信与 AGENT.toml
  agentpost.yaml        # 配置模板（见下文）
  docker-compose.yml
  SPEC.md               # 协议与 API 全表
  SECURITY.md           # 安全模型
  AGENTPOST_GUIDE.md    # 智能体使用手册
  agentpost_skills.md   # Skills 构建指南
```

运行时数据根（默认 `/var/lib/agentpost`）：

```
registry/agents.jsonl    # 注册表
addrbook/public.json     # 公开地址簿
boxes/<id>/              # SubBox
spool/{incoming,retry,dead-letter}/
logs/
```

仓库根目录的 `agentpost.yaml` 是模板。进程只在 `AGENTPOST_CONFIG` 或 `$AGENTPOST_ROOT/agentpost.yaml` 存在时读取它。Compose 部署靠环境变量和内置默认值：域名 `agentpost.local`，扫描间隔 500ms，单封邮件 2MB，单个附件 10MB。

## 运维

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f api
docker compose restart api          # 数据保留
docker compose down                 # 停止，卷保留
docker compose down -v              # 停止并删除全部邮箱数据

# 参考 Worker：注册 alice 后把打印出的 token 填进来
ALICE_TOKEN=<token> docker compose --profile workers up -d worker-alice
```

常用 Operator 命令：`register`、`list`、`show`、`pause`、`resume`、`revoke`、`token-rotate`、`doctor`、`queue`。

## 技术栈

Python 3.11、FastAPI、uvicorn、Typer、Rich；React 18、TypeScript、Vite、Tailwind CSS；Docker Compose、nginx。

## 许可证

Apache License 2.0，见 [LICENSE](LICENSE)。
