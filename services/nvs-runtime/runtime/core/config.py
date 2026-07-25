from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "nvs-runtime"
    api_prefix: str = "/api/v1"
    host: str = "0.0.0.0"
    port: int = 8020

    database_url: str = "postgresql://nvs:nvs@postgres:5432/nvs_runtime"
    redis_url: str = "redis://redis:6379/0"

    nvs_kernel_url: str = "http://localhost:8000"
    kernel_forward_timeout: float = 10.0
    kernel_retry_max: int = 5

    event_stream_maxlen: int = 10000
    dedup_ttl_seconds: int = 3600

    semantic_annotator_url: str = "http://localhost:8011"


@lru_cache
def get_settings() -> Settings:
    return Settings()
