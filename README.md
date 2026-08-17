# 🤖 哆啦A梦 (Doraemon) - 供金打工人

> 基于 Python + FastAPI 的企业级飞书 Agent 平台
> 复刻自 [scf-lark-coco](https://github.com/xxx/scf-lark-coco) 的设计思想

---

## 📋 当前版本: V0.2 (分层架构 + Session 记忆)

| 版本 | 阶段 | 核心特性 | 状态 |
|:---|:---|:---|:---|
| **V0.1** | MVP 单体版 | 飞书 Webhook → Echo 回显 → 飞书回复 | ✅ 已完成 |
| **V0.2** | 分层架构 | Session 记忆、Executor 抽象、Agent 路由、斜杠指令、消息防重 | ✅ **当前版本** |
| V0.3 | 分布式 | Central/Worker 拆分、Worker 注册与心跳 | ⏳ 规划中 |
| V0.4 | 流式体验 | SSE 流式输出、打字机卡片效果 | ⏳ 规划中 |
| V0.5 | 企业级 | SSO、权限、审计、高可用 | ⏳ 规划中 |

---

## 🏗️ 架构概览

```
┌─────────────────────────────────────────────────────────┐
│                     飞书开放平台                         │
│            (消息推送 / SSO / API 调用)                   │
└─────────────────────────┬───────────────────────────────┘
                          │ HTTP Webhook
                          ▼
┌─────────────────────────────────────────────────────────┐
│                Doraemon 核心服务 (FastAPI)              │
│  ┌──────────┐  ┌──────────┐  ┌───────────┐            │
│  │  main.py  │  │ handler  │  │ session_  │            │
│  │  (入口)   │─▶│  (业务)   │─▶│ manager   │            │
│  └──────────┘  └────┬─────┘  └─────┬─────┘            │
│                     │               │                   │
│                ┌────▼─────┐   ┌────▼─────┐            │
│                │  router   │   │  SQLite  │            │
│                │ (Agent路由)│   │  (数据库) │            │
│                └────┬─────┘   └──────────┘            │
│                     │                                   │
│           ┌─────────┼──────────┐                       │
│           ▼         ▼          ▼                       │
│     ┌──────────┐ ┌────────┐ ┌────────┐               │
│     │  Echo    │ │ Codex  │ │ Traex  │               │
│     │ Executor │ │预留接口│ │预留接口│               │
│     └──────────┘ └────────┘ └────────┘               │
└─────────────────────────────────────────────────────────┘
```

---

## 📁 项目结构

```
doraemon/
├── doraemon/
│   ├── __init__.py           # 版本信息
│   ├── main.py               # FastAPI 服务入口
│   ├── config.py             # 全局配置 (Pydantic Settings)
│   ├── db.py                 # 异步数据库引擎 + Session 工厂
│   ├── models.py             # SQLAlchemy ORM 模型
│   ├── session_manager.py    # Session 会话管理器 (粘性路由/重置)
│   ├── executor.py           # Executor 抽象接口 + 具体实现
│   ├── router.py             # Agent 路由器
│   ├── handler.py            # 飞书消息业务处理层
│   └── feishu_client.py      # 飞书 Open API 封装
├── workspace/                # Agent 工作目录 (自动创建)
├── doraemon.db               # SQLite 数据库文件 (自动生成)
├── .env.example              # 环境变量模板
├── .gitignore
├── requirements.txt          # Python 依赖
└── README.md                 # 本文件
```

---

## 🚀 快速开始

### 1. 环境要求

- Python 3.10+ (推荐，3.9 也可以)
- macOS / Linux (Windows 未测试)

### 2. 安装依赖

```bash
cd doraemon

# 创建虚拟环境 (推荐)
python3 -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env` 文件，填入你的配置：

```dotenv
# 飞书应用凭证 (必填 - 去飞书开放平台创建自建应用获取)
APP_ID=cli_xxxxxxxxxxxx
APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx

# 飞书事件校验 Token (可选，安全起见建议配置)
VERIFICATION_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx

# Agent 配置
# 阶段一/二先用 echo 测试链路，装了 Codex 后改成真实路径
AGENT_BINARY=echo
AGENT_WORK_DIR=./workspace

# 数据库 (默认 SQLite，零配置)
DATABASE_URL=sqlite+aiosqlite:///./doraemon.db

# 服务端口
PORT=8000
```

### 4. 启动服务

```bash
python -m doraemon.main
```

启动成功后你会看到：

```
==================================================
  🤖 哆啦A梦 (Doraemon) V0.2 启动中...
==================================================
[DB] Database initialized successfully.
  📦 数据库: sqlite+aiosqlite:///./doraemon.db
  🤖 可用 Agent: ['echo', 'codex']
  🌐 服务地址: http://0.0.0.0:8000
==================================================

INFO:     Uvicorn running on http://0.0.0.0:8000
```

### 5. 验证服务

```bash
# 健康检查
curl http://localhost:8000/

# 查看可用 Agent
curl http://localhost:8000/api/agents

# 查看系统状态
curl http://localhost:8000/api/status
```

---

## 🔗 配置飞书机器人

### 方式一：ngrok 内网穿透 (本地开发推荐)

1. 安装并启动 ngrok：
```bash
ngrok http 8000
```
会得到一个公网地址，例如：`https://abc123.ngrok.io`

2. 前往 [飞书开放平台](https://open.feishu.cn/) → 你的应用 → **事件与回调**：
   - **请求网址**：填入 `https://abc123.ngrok.io/webhook/event`
   - 点击保存，系统会自动验证 URL（`url_verification`）

3. **添加事件**：
   - 进入「事件订阅」→「添加事件」
   - 搜索并订阅：**接收消息 v1** (`im.message.receive_v1`)

4. **申请权限**：
   - 进入「权限管理」
   - 申请：`im:message`、`im:message:send_as_bot`

5. **发布版本**：审核通过后即可在飞书中使用

---

## 💬 飞书指令

在飞书聊天中直接发送以下斜杠指令：

| 指令 | 功能说明 |
|:---|:---|
| `/help` | 显示帮助信息 |
| `/new` | 开启新会话（清空当前对话记忆） |
| `/status` | 查看当前会话状态（SessionID、Agent、创建时间） |
| `/agents` | 查看可用的 Agent 列表 |
| `/echo <文字>` | 测试 Echo 执行器（直接回显文字） |

### 普通对话

直接发送文字消息即可，Bot 会：
1. 自动创建/复用 Session
2. 选择绑定的 Agent（默认 echo）
3. 执行并回复结果

---

## 🧠 核心设计说明

### Session 会话管理

**粘性路由机制**：同一个用户/群聊，始终绑定同一个 Session，Agent 执行时保持上下文。

**SessionID 生成规则**：

| 场景 | 格式 | 示例 |
|:---|:---|:---|
| 私聊 (p2p) | `sess_p2p_{open_id}_{count}` | `sess_p2p_ou_xxx_1` |
| 群聊 (group) | `sess_grp_{chat_id}_{count}` | `sess_grp_oc_xxx_1` |
| 话题 (thread) | `sess_thr_{thread_id}_{count}` | `sess_thr_omt_xxx_1` |

**重置机制**：`/new` 不会删除旧记录，而是将旧 Session 标记为 inactive，创建一个新 Session（保留审计痕迹）。

### Executor 抽象

统一接口，方便接入多种 Agent 后端：

```python
class BaseExecutor(ABC):
    async def execute(self, session_id, prompt, context) -> ExecutorResult: ...
    async def close_session(self, session_id): ...
```

目前内置：
- **EchoExecutor**：调试用，直接回显消息
- **CodexExecutor**：骨架已就绪，V0.3 实现

### 消息防重

两层防护：
1. **内存级**：`_pending_messages` Set 快速拦截
2. **数据库级**：`messages.id` 唯一约束兜底

---

## 🧪 API 接口

### 系统接口

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| GET | `/` | 健康检查 |
| GET | `/api/agents` | 可用 Agent 列表 |
| GET | `/api/status` | 系统状态信息 |

### 飞书回调

| 方法 | 路径 | 说明 |
|:---|:---|:---|
| POST | `/webhook/event` | 飞书事件订阅入口 |

---

## 🔧 开发指南

### 接入新的 Agent

1. 在 `doraemon/executor.py` 中继承 `BaseExecutor`：
```python
class MyAgentExecutor(BaseExecutor):
    name = "myagent"

    async def execute(self, session_id, prompt, context=None):
        # 你的执行逻辑
        return ExecutorResult(exit_code=0, output_text="结果")

    async def close_session(self, session_id):
        pass
```

2. 在 `doraemon/router.py` 的 `_register_defaults()` 中注册：
```python
self.register(MyAgentExecutor())
```

### 代码规范

- 使用 Python `typing` 类型标注
- 异步函数统一用 `async/await`
- 数据库操作使用 SQLAlchemy AsyncSession
- 错误不要抛出到 HTTP 层，在业务层处理并返回友好消息

---

## 🐛 常见问题

### Q: 启动报错 `Address already in use`
端口被占用，杀掉占用进程或改 `.env` 里的 `PORT`：
```bash
lsof -ti:8000 | xargs kill -9
```

### Q: 飞书发消息 Bot 没回复
1. 检查服务是否在运行
2. 检查 ngrok 是否在线
3. 查看服务终端日志是否收到事件
4. 确认 `APP_ID`/`APP_SECRET` 配置正确
5. 确认飞书应用已发布并添加权限

### Q: Token 校验失败 `403 Forbidden`
如果本地测试嫌麻烦，可以把 `.env` 里的 `VERIFICATION_TOKEN` 留空（不推荐生产环境这么做）。

### Q: 飞书返回 `code: 99992354`
这是因为你用 curl 模拟消息时，`message_id` 是假的，飞书找不到那条消息无法回复。这是正常的——只要日志里显示 `[Message]` 收到了消息，就证明链路是通的。

---

## 📊 版本演进路线图

```
V0.1 ──▶ V0.2 ──▶ V0.3 ──▶ V0.4 ──▶ V0.5
 MVP     分层      分布式    流式     企业级
         记忆      Worker    SSE      SSO/权限
```

---

## 📝 License

MIT
