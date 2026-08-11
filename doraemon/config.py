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

settings = Settings()
