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
    # ADR-0013: hekbd (C++), not hekb-api (Python), is the canonical HEKB
    # backend for Runtime traffic — it is the only one of GemminAI/hekb's
    # two REST surfaces that implements the full object+morphism+query
    # contract (nearest/neighbours/geodesic/relate/stats), and it is what
    # GemminAI/hekb's own reference client (hekb/python/hekb/client.py)
    # itself defaults to. hekb-api remains real and documented but is not
    # the default target — see the ADR for the full Reality Audit.
    hekb_url: str = "http://127.0.0.1:8100"

    # Semantic Anchor capability: real local inference runtime, confirmed
    # present on this host (Reality Audit — Ollama was the only one of
    # Ollama/MLX/vLLM/llama.cpp actually installed). Default matches
    # LOCAL_LLM_BASE_URL's own default in compose/docker-compose.yml
    # (Ollama's standard port). Not the shared low-latency NetworkProfile —
    # see runtime/gateway/ollama_client.py for why LLM inference needs its
    # own timeout profile.
    ollama_url: str = "http://localhost:11434"

    # EXP-Ubuntu011: WAN-aware network profile (LOCAL/GCP_INTERNAL/WAN).
    sensos_env: str = "local"
    network_profile_path: str = "config/network_profile.yaml"


@lru_cache
def get_settings() -> Settings:
    return Settings()
