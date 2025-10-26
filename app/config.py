from __future__ import annotations

import os
import json
from typing import List, Optional, Any

from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_json_loads(value: str) -> Any:
    """Try JSON, otherwise return the raw string for validators to handle."""
    try:
        return json.loads(value)
    except Exception:
        return value


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        case_sensitive=False,
        env_json_loads=_env_json_loads,
    )

    # Auth
    api_keys: List[str] = Field(default_factory=list)  # supports comma-separated or JSON via APP_API_KEYS
    api_key: Optional[str] = None  # single key via env: APP_API_KEY

    # Storage
    storage_root: str = os.getenv("APP_STORAGE_ROOT", "data/jobs")
    max_job_retention: int = 1000
    publish_backend: str = os.getenv("APP_PUBLISH_BACKEND", "local")
    auto_publish: bool = os.getenv("APP_AUTO_PUBLISH", "false").lower() == "true"

    # OSS
    oss_endpoint: Optional[str] = os.getenv("APP_OSS_ENDPOINT")
    oss_bucket: Optional[str] = os.getenv("APP_OSS_BUCKET")
    oss_access_key_id: Optional[str] = os.getenv("APP_OSS_ACCESS_KEY_ID")
    oss_access_key_secret: Optional[str] = os.getenv("APP_OSS_ACCESS_KEY_SECRET")
    oss_prefix: str = os.getenv("APP_OSS_PREFIX", "deepseek-ocr")
    oss_sign_expire_seconds: int = int(os.getenv("APP_OSS_SIGN_EXPIRE_SECONDS", "3600"))

    # Token
    token_store_path: str = os.getenv("APP_TOKEN_STORE_PATH", "data/tokens/tokens.json")

    # Workers / scheduling
    max_workers: int = int(os.getenv("APP_MAX_WORKERS", "1"))
    dynamic_workers: bool = os.getenv("APP_DYNAMIC_WORKERS", "true").lower() == "true"
    mem_per_job_gb: float = float(os.getenv("APP_MEM_PER_JOB_GB", "8.0"))
    reserve_gpu_mem_gb: float = float(os.getenv("APP_RESERVE_GPU_MEM_GB", "1.0"))
    gpu_index: int = int(os.getenv("APP_GPU_INDEX", "0"))
    idle_unload_seconds: int = int(os.getenv("APP_IDLE_UNLOAD_SECONDS", "600"))
    load_timeout_seconds: int = int(os.getenv("APP_LOAD_TIMEOUT_SECONDS", "180"))
    force_cpu: bool = os.getenv("APP_FORCE_CPU", "false").lower() == "true"
    max_queue_size: int = int(os.getenv("APP_MAX_QUEUE_SIZE", "100"))  # 队列最大长度
    min_system_memory_gb: float = float(os.getenv("APP_MIN_SYSTEM_MEMORY_GB", "2.0"))  # 系统内存最小可用量

    # IO streaming
    upload_chunk_mb: int = int(os.getenv("APP_UPLOAD_CHUNK_MB", "1"))
    download_chunk_mb: int = int(os.getenv("APP_DOWNLOAD_CHUNK_MB", "4"))
    max_upload_mb: int = int(os.getenv("APP_MAX_UPLOAD_MB", "200"))  # 降低默认值防止 OOM
    max_pages: int = int(os.getenv("APP_MAX_PAGES", "500"))  # 降低默认值防止 OOM
    enable_auto_batch: bool = os.getenv("APP_ENABLE_AUTO_BATCH", "true").lower() == "true"  # 大文件自动分批
    batch_page_size: int = int(os.getenv("APP_BATCH_PAGE_SIZE", "50"))  # 每批处理页数

    # Backend
    backend: str = os.getenv("APP_BACKEND", "hf")  # hf | vllm
    enable_model: bool = os.getenv("APP_ENABLE_DS_MODEL", "true").lower() == "true"
    enable_mcp: bool = os.getenv("APP_ENABLE_MCP", "false").lower() == "true"

    # DeepSeek-OCR options (Transformers/hf)
    ds_model_path: str = os.getenv("APP_DS_MODEL_PATH", "deepseek-ai/DeepSeek-OCR")
    ds_use_flash_attn: bool = os.getenv("APP_DS_USE_FLASH_ATTN", "true").lower() == "true"
    ds_dtype: str = os.getenv("APP_DS_DTYPE", "bfloat16")  # bfloat16|float16|float32
    ds_base_size: int = int(os.getenv("APP_DS_BASE_SIZE", "1024"))
    ds_image_size: int = int(os.getenv("APP_DS_IMAGE_SIZE", "640"))
    ds_crop_mode: bool = os.getenv("APP_DS_CROP_MODE", "true").lower() == "true"
    ds_prompt_override: Optional[str] = os.getenv("APP_DS_PROMPT_OVERRIDE")

    # DeepSeek-OCR options (vLLM backend)
    ds_vllm_temperature: float = float(os.getenv("APP_DS_VLLM_TEMPERATURE", "0.0"))
    ds_vllm_max_tokens: int = int(os.getenv("APP_DS_VLLM_MAX_TOKENS", "8192"))
    ds_vllm_enable_prefix_caching: bool = os.getenv("APP_DS_VLLM_ENABLE_PREFIX_CACHING", "false").lower() == "true"
    ds_vllm_mm_processor_cache_gb: int = int(os.getenv("APP_DS_VLLM_MM_PROCESSOR_CACHE_GB", "0"))
    ds_vllm_ngram_size: int = int(os.getenv("APP_DS_VLLM_NGRAM_SIZE", "30"))
    ds_vllm_window_size: int = int(os.getenv("APP_DS_VLLM_WINDOW_SIZE", "90"))
    ds_vllm_whitelist_token_ids: Optional[str] = os.getenv("APP_DS_VLLM_WHITELIST_TOKEN_IDS", "128821,128822")

    # Metrics
    metrics_enabled: bool = os.getenv("APP_METRICS_ENABLED", "true").lower() == "true"

    # Server
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "8000"))
    log_level: str = os.getenv("APP_LOG_LEVEL", "info")
    cors_allow_origins: List[str] = Field(default_factory=lambda: os.getenv("APP_CORS_ALLOW_ORIGINS", "*").split(","))
    cors_allow_credentials: bool = os.getenv("APP_CORS_ALLOW_CREDENTIALS", "true").lower() == "true"
    cors_allow_origin_regex: Optional[str] = os.getenv("APP_CORS_ALLOW_ORIGIN_REGEX")

    # Security
    require_key_prefix: str = os.getenv("APP_REQUIRE_KEY_PREFIX", "sk_")
    require_auth: bool = os.getenv("APP_REQUIRE_AUTH", "true").lower() == "true"
    # Console auth
    console_enabled: bool = os.getenv("APP_CONSOLE_ENABLED", "true").lower() == "true"
    console_password: Optional[str] = os.getenv("APP_CONSOLE_PASSWORD")
    console_session_max_age: int = int(os.getenv("APP_CONSOLE_SESSION_MAX_AGE", "86400"))
    session_secret: Optional[str] = os.getenv("APP_SESSION_SECRET")
    cookie_secure: bool = os.getenv("APP_COOKIE_SECURE", "false").lower() == "true"

    # Rate limit
    rate_limit_enabled: bool = os.getenv("APP_RATE_LIMIT_ENABLED", "true").lower() == "true"
    rate_limit_rps: float = float(os.getenv("APP_RATE_LIMIT_RPS", "10"))
    rate_limit_burst: int = int(os.getenv("APP_RATE_LIMIT_BURST", "20"))
    rate_limit_exempt_paths: List[str] = Field(
        default_factory=lambda: [p.strip() for p in os.getenv("APP_RATE_LIMIT_EXEMPT", "/healthz,/metrics").split(",") if p.strip()]
    )
    login_rate_per_min: float = float(os.getenv("APP_LOGIN_RATE_PER_MIN", "10"))
    login_rate_burst: int = int(os.getenv("APP_LOGIN_RATE_BURST", "10"))

    # Result controls
    default_bbox: bool = os.getenv("APP_DEFAULT_BBOX", "true").lower() == "true"
    default_pack_zip: bool = os.getenv("APP_DEFAULT_PACK_ZIP", "true").lower() == "true"

    @field_validator("api_keys", mode="before")
    @classmethod
    def _parse_api_keys(cls, v):
        # Accept comma-separated string, JSON list string, list/tuple, or empty
        if v is None or v == "":
            return []
        if isinstance(v, str):
            s = v.strip()
            # Try JSON list first
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = json.loads(s)
                    if isinstance(parsed, list):
                        return [str(x).strip() for x in parsed if str(x).strip()]
                except Exception:
                    pass
            return [x.strip() for x in s.split(",") if x.strip()]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]
        return v

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _parse_cors(cls, v):
        if v is None or v == "":
            return ["*"]
        if isinstance(v, str):
            return [x.strip() for x in v.split(",") if x.strip()]
        if isinstance(v, (list, tuple)):
            return [str(x).strip() for x in v if str(x).strip()]
        return v


class RuntimeInfo(BaseModel):
    pid: int
    started_at: float
    version: str = "0.1.0"


def load_settings() -> Settings:
    s = Settings()
    # Normalize API keys combining both env styles
    keys: List[str] = []
    if s.api_keys:
        keys.extend([k.strip() for k in s.api_keys if isinstance(k, str) and k.strip()])
    env_list = os.getenv("APP_API_KEYS")
    if env_list:
        keys.extend([k.strip() for k in env_list.split(",") if k.strip()])
    if s.api_key:
        keys.append(s.api_key.strip())
    s.api_keys = list(dict.fromkeys(keys))
    return s
