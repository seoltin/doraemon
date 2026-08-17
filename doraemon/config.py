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

settings = Settings()
