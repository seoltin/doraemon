from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    app_id: str = ""
    app_secret: str = ""
    verification_token: str = ""
    agent_binary: str = "echo"
    agent_work_dir: str = "./workspace"
    host: str = "0.0.0.0"
    port: int = 8000

    # V0.2 新增: 数据库配置
    database_url: str = "sqlite+aiosqlite:///./doraemon.db"
    session_idle_timeout_hours: int = 24

    # V0.2 新增: 默认 Agent (新建会话时绑定)
    default_agent: str = "echo"
    # 多轮上下文最大轮数 (一轮 = user+assistant 各一条)
    max_history_rounds: int = 10

    # V0.3 新增: Worker 分布式配置
    worker_mode: str = "distributed"  # "local" = V0.2单体模式, "distributed" = V0.3分布式
    central_url: str = ""             # Worker 注册到 Central 的地址, 例: http://127.0.0.1:8000
    worker_port: int = 9001           # Worker 监听端口
    worker_host: str = "0.0.0.0"
    worker_token: str = ""            # Worker 与 Central 通信的认证 Token
    heartbeat_interval: int = 10      # 心跳间隔(秒)
    worker_health_timeout: int = 60   # Worker 心跳超时(秒), 超过则标记为不健康
    worker_drain_timeout: int = 300   # Drain 等待超时(秒)
    max_concurrent_turns: int = 5     # Worker 最大并发执行数

settings = Settings()
