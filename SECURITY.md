# AgentPost 安全模型

## 身份与鉴权

### 令牌体系

AgentPost 使用两种令牌：

1. **Operator Token** (`AGENTPOST_OPERATOR_TOKEN`)
   - 通过环境变量注入，不存入任何盒子
   - 拥有全部管理权限：注册/吊销盒子、查看所有队列和日志
   - 不可用于直接以某盒子身份发信（必须走 outbox）

2. **Box Token**
   - 注册时生成（256-bit 随机），仅明文显示一次
   - 系统只存储 SHA-256 哈希
   - 只能访问所属盒子的 inbox/outbox/data/memory/skills
   - 无法列举其他盒子

### 令牌安全

- Token 通过 `Authorization: Bearer <token>` 传递
- Box Token 轮换后旧令牌立即失效
- 前端仅将 token 存储在 sessionStorage（关闭标签页即清除）
- 不应将 token 写入 URL、日志或版本控制

## 路径隔离

### 设计原则

- 智能体只能看到自己 SubBox 的路径
- `agentpostd` 是唯一跨盒子进程
- spool、registry、其他 boxes 对 Worker 不可见

### 实现

1. **路径守卫**: 所有文件操作经过 `guard_path()` 检查，拒绝 `../` 路径逃逸
2. **API 鉴权**: Box Token 只能访问 `/boxes/{own_id}/` 下的资源
3. **文件写入限制**: Box Token 只能写入 `data/`、`memory/`、`work/`，不可直接写 `inbox/`
4. **附件路径校验**: 出站消息的附件路径不允许绝对路径或 `../` 穿越

### 生产加固建议

- 每个盒子分配独立 Unix UID
- 使用 Linux user namespace 隔离
- 绑定挂载只暴露本盒子目录
- Worker 容器不挂载 `agentpost-data` 卷

## 脚本沙箱

### Skills 和 Scripts 执行

- **超时**: 默认 5 秒，可配置
- **工作目录**: 锁定在本盒子根目录
- **网络**: 默认无网络访问
- **权限**: 不以 root 运行
- **环境变量**: 仅暴露 `PATH` 和 `AGENTPOST_BOX_ROOT`

### 风险

- 恶意 skill 脚本可能消耗 CPU/内存（通过超时限制）
- 脚本不应处理敏感数据（如其他盒子的信息）

## 卷挂载风险

### Docker 数据卷

`agentpost-data` 卷包含所有盒子数据。泄露此卷等于泄露所有通信内容。

- **不要** 将此卷挂载到不受信任的容器
- **不要** 在 Worker 容器中挂载整个数据卷
- Worker 应通过 API 访问本盒数据

### 备份

- 备份整个 `/var/lib/agentpost` 目录
- 备份数据应加密存储
- 恢复时确保文件权限正确

## 消息伪造防护

### From 校验

- 出站消息的 `from` 字段必须匹配发送方盒子地址
- 不匹配的消息被拒绝，移入 `outbox/failed/`
- 系统发送拒信回执到发送方 inbox

### 收件人校验

- 只投递到已注册且 `active` 状态的盒子
- 未知或不活跃的收件人记入回执的 `failed_to`
- 不支持外部域名投递

## 审计

### 系统日志

所有投递操作记录到 `logs/audit.jsonl`：
- `message_id`, `box`, `stage`（accept/validate/deliver/reject）
- 时间戳、成功/失败状态

### 盒子日志

每个盒子有独立的 `logs/activity.log` 和 `logs/skills.log`

### 日志安全

- 日志文件仅 operator 可访问
- Box Token 只能查看本盒子日志
- 日志不记录消息正文（仅元数据）
