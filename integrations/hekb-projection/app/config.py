from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HEKB_", env_file=".env")

    app_name: str = "hekb-runtime"
    version: str = "0.1.0"
    host: str = "0.0.0.0"
    port: int = 8080


settings = Settings()
