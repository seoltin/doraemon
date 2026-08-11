# 🐱 Doraemon - 飞书 AI Agent 机器人后端

> 一个极简的飞书机器人 + AI Agent 调度平台（MVP 版本）。用户在飞书里给机器人发消息，后端调用 AI Agent（如 Codex）执行任务，再把结果回给用户。就像哆啦A梦的口袋，说一句话，帮你搞定。

---

## ✨ 核心功能

- 🎛️ **飞书 Webhook 接入**：接收飞书消息事件，校验签名，解析消息内容
- 🤖 **Agent 调度引擎**：异步子进程方式调用外部 AI Agent，自带超时保护和错误处理
- 📮 **飞书 API 客户端**：自动获取/缓存 access_token，回复消息，支持自动截断和转义
- 🧪 **演示模式**：未接入真实 AI Agent 时，用 `echo` 命令模拟回复，方便调试
- ⚡ **全异步架构**：基于 FastAPI + asyncio，高并发不阻塞

---

## 🏗️ 架构概览

```
┌─────────────┐      Webhook 推送       ┌─────────────────┐
│   飞书用户   │ ──────────────────────▶ │  Doraemon 后端   │
│  (发消息)    │                          │  (FastAPI 服务)  │
└─────────────┘                          └────────┬────────┘
       ▲                                          │
       │                                          ▼
       │                                   调用外部 Agent 子进程
       │            回复执行结果                    │
       │                                          ▼
       │                               ┌─────────────────────┐
       └───────────────────────────────│   Agent 程序 (Codex) │
              飞书 API 回复消息          └─────────────────────┘
```

**数据流向**：

```
用户消息 → 飞书服务器 → POST /webhook/event → Doraemon
                                                    ↓
                                           agent_executor.run()
                                                    ↓
                                          创建子进程执行 Agent
                                                    ↓
                                         读取 stdout → 返回结果
                                                    ↓
                                         feishu_client 回复用户
```

---

## 📋 环境要求

| 依赖 | 版本要求 | 说明 |
|------|----------|------|
| Python | ≥ 3.10 | 使用了异步语法和类型注解新特性 |
| pip | ≥ 21.x | 安装依赖 |
| Node.js | ≥ 22 | （可选）安装 Codex CLI 时需要 |
| 公网可访问的服务器 | 任意 | 飞书 Webhook 需要能从公网访问你的服务 |

> 💡 本地开发没有公网 IP？可以用 `ngrok` 或 `frp` 做内网穿透。

---

## 🚀 快速开始（5 分钟跑起来）

### 第 1 步：克隆项目

```bash
git clone <your-repo-url> doraemon
cd doraemon
```

### 第 2 步：创建虚拟环境并安装依赖

```bash
# 创建虚拟环境（推荐）
python3 -m venv venv
source venv/bin/activate   # macOS/Linux
# .\venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt
```

### 第 3 步：配置环境变量

复制模板文件，然后根据你的实际情况修改：

```bash
cp .env.example .env
```

`.env` 配置说明（后面有详细版）：

```env
# 飞书应用凭证（从飞书开放平台获取）
APP_ID=cli_xxxxxxxxxxxx
APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
VERIFICATION_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxx

# Agent 配置（先用 echo 演示模式，后面接真的 Agent 再改）
AGENT_BINARY=echo
AGENT_WORK_DIR=./workspace

# 服务端口
PORT=8000
```

### 第 4 步：启动服务

```bash
# 方式 1：直接用 Python 启动（开发模式，带热重载）
python -m doraemon.main

# 方式 2：用 uvicorn 启动（生产推荐）
uvicorn doraemon.main:app --host 0.0.0.0 --port 8000 --reload
```

启动成功后，你会看到：

```
Starting Doraemon on http://0.0.0.0:8000
```

### 第 5 步：验证服务是否正常

浏览器访问 `http://localhost:8000/`，应该返回：

```json
{
    "status": "ok",
    "service": "Doraemon MVP",
    "agent_binary": "echo"
}
```

✅ 服务起来了！接下来配置飞书应用。

---

## 🔧 飞书应用配置（详细步骤）

这一步是新手最容易卡壳的地方，跟着一步一步来：

### 1️⃣ 创建飞书企业自建应用

1. 打开 [飞书开放平台](https://open.feishu.cn/)，登录企业管理员账号
2. 点击「开发者后台」→「创建应用」→「企业自建应用」
3. 填应用名称：比如 "Doraemon 机器人"，上传头像，点「创建」

### 2️⃣ 配置应用凭证（获取 APP_ID 和 APP_SECRET）

1. 应用创建好后，进入「凭证与基础信息」页面
2. 你会看到 **App ID** 和 **App Secret**
3. 把它们复制到 `.env` 文件的 `APP_ID` 和 `APP_SECRET` 字段

### 3️⃣ 添加机器人能力

1. 左侧菜单 →「添加应用能力」→ 找到「机器人」→ 点击「添加」
2. 添加成功后，你的应用就有了机器人能力

### 4️⃣ 配置事件订阅（Webhook 配置）

进入应用详情页后，左侧菜单点击「开发配置」→「事件与回调」，页面顶部有 3 个 Tab：**【事件配置】【回调配置】【加密策略】**。

#### 步骤 1：在【加密策略】Tab 复制 Verification Token ⚠️（先做这步！）

点击【加密策略】Tab，你会看到两个字段：
- **Encrypt Key（加密密钥）**：可以留空（Doraemon 目前没做消息加密，不用填）
- **Verification Token（校验令牌）**：**这就是你要的！** 复制这一串随机字符串

把复制到的 Token 粘贴到你本地 `.env` 文件的这一行：
```env
VERIFICATION_TOKEN=刚才复制的那串Token
```
保存 `.env`，然后**重启 Doraemon 服务**（改配置必须重启）。

> 💡 **实在找不到？→ 本地调试直接跳过校验**：把 `.env` 的 `VERIFICATION_TOKEN=` 留空（等号后面什么都不写），Doraemon 代码会自动跳过 Token 校验。但正式上线必须配置。

#### 步骤 2：在【事件配置】Tab 配置 Request URL

切回【事件配置】Tab：

1. 在「请求网址（Request URL）」处填入你的服务地址：
   ```
   https://你的公网地址/webhook/event
   ```
   > ⚠️ 必须是**公网可访问**的地址！
   > - 有服务器：填 `http://服务器公网IP:8000/webhook/event`
   > - 本地开发（没有公网IP）：看本文「Q7 本地开发没有公网IP怎么办？」用 ngrok/cpolar 做内网穿透，把穿透工具给你的地址 + `/webhook/event` 填进去

2. 「添加事件」→ 搜索并勾选 `接收消息 v1.0`（事件代码 `im.message.receive_v1`）→ 确定

3. 点击「保存」，飞书会发送一次 URL 验证请求（challenge 校验），如果一切正常会显示「验证成功」
   > 如果验证失败：依次检查
   > 1. 你的 Doraemon 服务启动了吗？（`curl http://localhost:8000/` 有响应吗？）
   > 2. URL 是否完整？最后有没有带 `/webhook/event`？
   > 3. 内网穿透工具（ngrok/cpolar）还在运行吗？窗口关了隧道就断了
   > 4. `.env` 的 `VERIFICATION_TOKEN` 和飞书后台复制的完全一致吗？（不要多复制了空格）
   > 5. 打开内网穿透工具的请求面板（ngrok 是 http://localhost:4040），看飞书的验证请求有没有到达

### 5️⃣ 配置权限范围

1. 左侧菜单 →「权限管理」
2. 搜索并开通以下权限：
   - `im:message` - 获取与发送单聊、群组消息
   - `im:message.group_at_msg` - 获取群组中@机器人的消息（群聊用）
   - `im:message.p2p_msg` - 获取用户发给机器人的单聊消息

### 6️⃣ 发布应用（企业可用）

1. 左侧菜单 →「版本管理与发布」→「创建版本」
2. 填版本号（0.1.0）和更新说明
3. 点击「申请发布」
4. 企业管理员审批通过后，机器人就能用了
   > 💡 测试阶段可以用「测试企业和人员」功能，先只给自己用，不用走审批

---

## 📝 配置项详解（.env 每个字段都讲清楚）

| 变量 | 必填 | 默认值 | 说明 |
|------|------|--------|------|
| `APP_ID` | ✅ 是 | 空 | 飞书应用 App ID，格式 `cli_xxxxxx`，从飞书后台获取 |
| `APP_SECRET` | ✅ 是 | 空 | 飞书应用 App Secret，**绝对不要提交到 Git** |
| `VERIFICATION_TOKEN` | 推荐 | 空 | Webhook 校验令牌，飞书后台事件配置里能看到。为空则跳过校验（不安全，生产必须配） |
| `AGENT_BINARY` | ✅ 是 | `echo` | AI Agent 可执行程序的路径 |
| | | | - `echo` = 演示模式，原样返回提示，方便本地调试 |
| | | | - `/path/to/codex` = 正式模式，调用 Codex CLI 执行任务 |
| `AGENT_WORK_DIR` | 否 | `./workspace` | Agent 的工作目录，Agent 产生的文件都会落在这。服务启动时自动创建 |
| `HOST` | 否 | `0.0.0.0` | 服务监听地址。`127.0.0.1` = 仅本机访问，`0.0.0.0` = 外部可访问 |
| `PORT` | 否 | `8000` | 服务监听端口，注意防火墙/安全组要放行 |

---

## 🎮 使用方法

### 🔹 演示模式（开箱即用）

默认 `AGENT_BINARY=echo`，不需要任何 AI Agent 就能跑通全流程，用来验证飞书接入是否正常：

1. 确保服务启动、飞书配置完成
2. 在飞书里找到你的机器人 → 发送消息：「你好」
3. 你会收到回复：
   ```
   [Doraemon-MVP]
   Received your instruction: 你好
   I'm still learning, waiting for Codex installation!
   ```

✅ 看到这条消息 = 飞书 Webhook → Doraemon → Agent 调用 → 飞书回复，**整条链路通了！**

### 🔹 正式模式（接入 Codex CLI）

> ⚠️ 注意：项目里写死的调用格式 `codex query -p "xxx"` **不是官方格式**，真实 Codex CLI 的正确用法是 `codex exec "xxx"`。使用前请参考下面的"常见问题"修正 executor.py 的代码。

#### 安装 Codex CLI

```bash
# 方式 1：npm 安装（需要 Node.js 22+）
npm install -g @openai/codex

# 方式 2：macOS Homebrew
brew install codex

# 验证安装
codex --version
```

#### 登录 Codex

```bash
# 用 ChatGPT 账号登录（弹出浏览器 OAuth）
codex login

# 或用 API Key（适合服务器环境）
echo "sk-xxxxxxxxxxxx" | codex login --with-api-key
```

#### 修改 .env 配置

```env
AGENT_BINARY=codex
```

#### （重要）修正 executor.py 的调用格式

打开 `doraemon/executor.py`，把第 22-26 行改成：

```python
else:
    cmd = [
        self.binary,
        "exec",       # 官方非交互子命令是 exec，不是 query
        prompt        # 直接位置参数传，不是 -p
    ]
```

#### 重启服务，测试

在飞书里给机器人发：「帮我写一个 Python 快速排序函数」

你会收到 Codex 真正写的代码！✅

---

## 📂 项目结构

```
doraemon/
├── doraemon/                 # 主包目录
│   ├── __init__.py           # 包初始化，定义版本号
│   ├── main.py               # 🔴 主入口：FastAPI 应用 + 路由注册 + Webhook 处理
│   ├── config.py             # 🟡 配置中心：pydantic-settings 读取 .env
│   ├── executor.py           # 🟢 Agent 执行器：异步子进程调用外部 Agent
│   └── feishu_client.py      # 🔵 飞书客户端：获取 token + 回复消息
├── workspace/                # Agent 工作目录（启动时自动创建）
├── .env.example              # 环境变量模板
├── .env                      # 实际环境变量（自己创建，不要提交 Git）
├── .gitignore
├── requirements.txt          # Python 依赖
└── README.md                 # 本文件
```

---

## ❓ 常见问题 FAQ

### Q1: 启动后飞书消息发了没反应？

**排查清单**（从上到下检查）：

1. **服务活着吗？**
   ```bash
   curl http://localhost:8000/
   ```
   → 应该返回 JSON，不是连接错误。

2. **飞书的 Webhook 请求到达了吗？**
   看 Doraemon 的终端输出，有没有打印 `[New Message]` 开头的日志？
   - ❌ 没有 → 飞书没推过来，检查 URL、端口、防火墙
   - ✅ 有 → 消息收到了，继续往下查

3. **飞书 URL 验证失败？**
   - 确认 `.env` 的 `VERIFICATION_TOKEN` 和飞书后台一致
   - 确认你的服务公网能访问（`curl 公网IP:8000/` 能通）
   - ngrok 用的是 http 还是 https？飞书支持 http

4. **Agent 执行报错？**
   看飞书回复的内容里有没有 `[Agent Error]` 或 `[Agent System Error]` 字样：
   - `Binary not found` → AGENT_BINARY 路径不对
   - `Exit Code` 非 0 → Agent 本身执行失败，手动在终端执行一下命令看报错

### Q2: echo 模式好用，换成 Codex 就报错？

大概率是 **executor.py 的调用格式和 Codex 官方不匹配**。先在终端手动测试：

```bash
# 看 Codex 支持的所有命令
codex --help

# 看 exec 子命令的参数
codex exec --help
```

然后对应修改 executor.py 第 22-26 行的 `cmd` 列表。

### Q3: Agent 执行时间很长（超过 10 分钟）怎么办？

10 分钟超时是写死的，代码在 [executor.py 第42行](file:///Users/bytedance/Documents/scf/doraemon/doraemon/executor.py#L42-L44)：

```python
timeout=600
```

你可以改成更大的值，比如 3600 秒 = 1 小时。

但更好的方案是：**收到消息立刻返回 200，后台慢慢跑，跑完了主动调 API 回复**。这样飞书不会因为超时重试，用户体验也更好。

### Q4: 同一条消息被回复了好几次？

飞书 Webhook 有**重试机制**：如果你的服务没在超时时间（3-5 秒）内返回 HTTP 200，飞书会认为投递失败然后重试。

两种解决办法：
1. 上面说的异步处理 + 立即返回
2. 用 `message_id` 做去重：用 Redis 或内存存一下已处理的 message_id，重复请求直接跳过

### Q5: 想支持图片、文件、语音消息？

目前 [main.py 第64-69行](file:///Users/bytedance/Documents/scf/doraemon/doraemon/main.py#L64-L69) 直接拦截了非文本消息。你可以在这里扩展：
- `image` 类型 → 调飞书 API 下载图片，传给支持多模态的 Agent
- `voice` 类型 → 转文字后再给 Agent
- `file` 类型 → 下载到 workspace 目录，传给 Agent 处理

### Q6: .env 文件会被 Git 提交吗？

不会。`.env` 在 `.gitignore` 里（你可以检查一下）。但一定要确认 `APP_SECRET` 等敏感信息**确实没落到 Git 仓库里**。

### Q7: 本地开发没有公网 IP，怎么测试飞书？

用内网穿透工具：

**Ngrok（推荐，最快）**：
```bash
# 安装
brew install ngrok

# 启动，把本地 8000 映射到公网
ngrok http 8000
```
启动后 ngrok 会给你一个类似 `https://xxxx.ngrok-free.app` 的公网地址，把飞书 Webhook URL 填成 `https://xxxx.ngrok-free.app/webhook/event` 即可。

其他工具：frp、cpolar、花生壳等。

---

## 🛣️ 后续优化方向

这个项目是 MVP 版本，如果要上生产，建议按优先级做以下优化：

1. **消息去重 + 幂等**：防止飞书重试导致 Agent 重复执行
2. **异步立即返回**：不等待 Agent 执行完就先回飞书 200
3. **中间态回复**：Agent 执行中回复"正在思考..."，执行完再回最终结果
4. **结构化日志**：把 print 换成 logging + JSON 格式，接入 ELK/Loki
5. **并发控制**：加 Semaphore 限制同时执行的 Agent 数量，防刷屏打爆机器
6. **对话上下文**：把历史对话存数据库，支持多轮对话
7. **Docker 部署**：写 Dockerfile + docker-compose，一键部署
8. **健康检查 + 监控**：加 Prometheus metrics，接入 Grafana 监控

---

## 🤝 贡献

有问题或改进建议？欢迎提 Issue / MR！

---

## 📄 License

MIT License
