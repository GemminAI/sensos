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

    nvs_kernel_url: str = "http://nvs-kernel:8100"
    # Superseded by config/network_profile.yaml (EXP-Ubuntu011) as the source
    # of transport timeout/retry for KernelGateway. Kept as the pre-profile
    # fallback default (network_profile.py) — not read by KernelGateway.
    kernel_forward_timeout: float = 10.0
    kernel_retry_max: int = 5

    event_stream_maxlen: int = 10000
    dedup_ttl_seconds: int = 3600

    semantic_annotator_url: str = "http://localhost:8011"

    # EXP-Ubuntu011: outbound legs the ForwardWorker/http_pool can reach.
    # CLE/HEKB are transport-only extension points today (no payload mapping
    # — see runtime/gateway/cle_client.py, hekb_client.py).
    cle_url: str = "http://localhost:8000"
    # Default matches integrations/hekb-mcp/client.py's DEFAULT_BASE_URL —
    # the only confirmed HEKB REST port in this repo today. Override via env
    # for the actual local HEKB API host in a given deployment.
    hekb_url: str = "http://localhost:8080"
    # GemminAI/hekb ships two REST surfaces (docs/API.md, docs/hekb-api.md):
    # the C++ `hekbd` (default port 8100, `hekb/python/hekb/client.py`'s own
    # DEFAULT_BASE_URL) implements the full object+morphism+query contract
    # (nearest/neighbours/geodesic/relate/stats via /metrics); the Python
    # `hekb-api` at `hekb_url` above implements only object create/read/
    # search. Read MCP tools that need query/graph operations target this
    # URL, not `hekb_url` — confirmed by reading both servers' route tables.
    hekb_query_url: str = "http://127.0.0.1:8100"

    # EXP-Ubuntu011: WAN-aware network profile (LOCAL/GCP_INTERNAL/WAN).
    sensos_env: str = "local"
    network_profile_path: str = "config/network_profile.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
