"""Application settings loaded from environment / .env."""

from functools import lru_cache
from typing import List

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_env: str = "development"
    log_level: str = "INFO"
    tz: str = "Asia/Shanghai"

    kernel_host: str = "0.0.0.0"
    kernel_port: int = 8001
    orchestrator_host: str = "0.0.0.0"
    orchestrator_port: int = 8002
    adapters_host: str = "0.0.0.0"
    adapters_port: int = 8000

    kernel_rpc_url: str = "http://127.0.0.1:8001"
    orchestrator_rpc_url: str = "http://127.0.0.1:8002"

    redis_url: str = "redis://127.0.0.1:6379/0"
    redis_task_queue: str = "nlm:tasks"
    redis_event_channel: str = "nlm:events"
    redis_session_prefix: str = "nlm:session:"

    database_url: str = "sqlite+aiosqlite:///data/nexus.db"

    default_model_provider: str = "glm"
    default_model_name: str = "glm-4.7-flash"

    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_default_model: str = "gpt-4o-mini"
    openai_models: str = "gpt-4o-mini,gpt-4o,gpt-4.1-mini,gpt-4.1"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_default_model: str = "deepseek-chat"
    deepseek_models: str = "deepseek-chat,deepseek-reasoner"

    glm_api_key: str = ""
    glm_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    glm_default_model: str = "glm-4.7-flash"
    glm_models: str = "glm-4.7-flash,glm-4-flash,glm-4.5-flash,glm-z1-flash,glm-4-plus"

    anthropic_api_key: str = ""
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_default_model: str = "claude-3-5-sonnet-20241022"
    anthropic_models: str = "claude-3-5-sonnet-20241022,claude-3-5-haiku-20241022,claude-sonnet-4-20250514"

    model_max_retries: int = 8
    model_retry_base_seconds: float = 2.0
    model_retry_max_seconds: float = 60.0
    model_timeout_seconds: int = 120
    model_circuit_failure_threshold: int = 5
    model_circuit_reset_seconds: int = 60

    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_verification_token: str = ""
    feishu_encrypt_key: str = ""
    feishu_use_long_connection: bool = True

    plugins_dir: str = "plugins_volume"
    plugin_isolation: bool = True
    cli_auto_register: bool = True

    # Optional web search (Tavily). If empty, CLI web_search falls back to DuckDuckGo.
    tavily_api_key: str = ""
    tavily_search_depth: str = "basic"
    brave_api_key: str = ""

    web_static_dir: str = "web-static"
    cors_origins: str = "*"

    @property
    def cors_origin_list(self) -> List[str]:
        if self.cors_origins.strip() == "*":
            return ["*"]
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
