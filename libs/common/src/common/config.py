from __future__ import annotations

import json
import os
from collections.abc import Mapping
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import AnyHttpUrl, BaseModel, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = next(
    (parent for parent in Path(__file__).resolve().parents if (parent / "apps").exists()),
    Path(__file__).resolve().parents[4],
)


def _resolve_environment() -> tuple[str, bool]:
    """Resolve active environment and whether it was explicitly set.

    Returns:
        Tuple of (environment_name, was_explicitly_set)
    """
    for key in ("APP__ENVIRONMENT", "APP_ENV", "ENV"):
        candidate = os.environ.get(key)
        if candidate:
            value = candidate.strip()
            if value:
                return value.lower(), True
    return "dev", False


def _collect_env_files(base_path: Path, environment: str, explicit: bool = False) -> tuple[str, ...]:
    """Collect environment files in priority order.

    Pydantic-settings loads files in order, with later files overriding earlier ones.

    If environment is explicitly set:
        - Load only .env.<env> (env-specific file, ignoring base)
    Otherwise (default behavior):
        - Load base .env first, then .env.<env> if it exists (overrides base)

    Args:
        base_path: Base path for env file (e.g., .env.shared or apps/module/.env)
        environment: Environment name (e.g., "dev", "test")
        explicit: Whether environment was explicitly set via ENV/APP__ENVIRONMENT
    """
    candidates = []
    env_specific = base_path.with_name(f"{base_path.name}.{environment}")

    if explicit and environment:
        # If environment is explicitly set, use only env-specific file
        # No fallback - explicit env means strict env-specific configs only
        if env_specific.exists():
            candidates.append(env_specific)
    else:
        # Default behavior: load base file, then environment-specific override
        if base_path.exists():
            candidates.append(base_path)
        if environment and env_specific.exists():
            candidates.append(env_specific)
    return tuple(str(path) for path in candidates)


ACTIVE_ENVIRONMENT, ENV_EXPLICIT = _resolve_environment()
SHARED_ENV_FILES: tuple[str, ...] = _collect_env_files(PROJECT_ROOT / ".env.shared", ACTIVE_ENVIRONMENT, ENV_EXPLICIT)


class AppSettings(BaseModel):
    debug: bool = False
    version: str = "0.1.0"
    environment: str = "dev"


class BotSettings(BaseModel):
    token: str | None = None


class BackendSettings(BaseModel):
    url: str | None = None


class SalesAgentServiceSettings(BaseModel):
    url: AnyHttpUrl | None = None


class ServiceAuthSettings(BaseModel):
    api_key: SecretStr | None = Field(
        default=None,
        description="Shared API key for service-to-service authentication.",
    )
    header: str = Field(
        default="X-Service-Key",
        description="HTTP header name carrying the shared service API key.",
    )

    def resolved_header(self) -> str:
        header = (self.header or "").strip()
        return header or "X-Service-Key"


class CorsSettings(BaseModel):
    allow_origins: list[str] = Field(
        default_factory=list,
        description="Allowed origins. Leave empty to disable CORS.",
    )
    allow_methods: list[str] = Field(default_factory=lambda: ["*"], description="Allowed HTTP methods.")
    allow_headers: list[str] = Field(default_factory=lambda: ["*"], description="Allowed request headers.")
    expose_headers: list[str] = Field(
        default_factory=list,
        description="Response headers exposed to browsers.",
    )
    allow_credentials: bool = Field(
        default=False,
        description="Allow browsers to include credentials. Ignored when allow_origins contains '*'.",
    )
    max_age: int = Field(
        default=600,
        ge=0,
        description="How long (seconds) preflight responses can be cached.",
    )

    @field_validator(
        "allow_origins",
        "allow_methods",
        "allow_headers",
        "expose_headers",
        mode="before",
    )
    @classmethod
    def _ensure_list(cls, value: object) -> list[str] | object:
        if value is None:
            return []
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            if text.startswith("[") and text.endswith("]"):
                try:
                    parsed = json.loads(text)
                except json.JSONDecodeError:
                    parsed = None
                if isinstance(parsed, list):
                    return [str(item).strip() for item in parsed if str(item).strip()]
            return [item for item in (part.strip() for part in text.split(",")) if item]
        return value

    def is_enabled(self) -> bool:
        return bool(self.allow_origins)


class BackendTransportTelegramSettings(BaseModel):
    url: AnyHttpUrl | None = Field(
        default=None,
        description="Base URL for Telegram transport module (e.g., http://telegram-module:8001).",
    )
    reload_url: AnyHttpUrl | None = Field(
        default=None,
        description="Optional webhook endpoint for forcing telegram-module reload.",
    )


class BackendTransportWappiSettings(BaseModel):
    url: AnyHttpUrl | None = Field(
        default=None,
        description="Base URL for Wappi transport module (e.g., http://wappi-module:8002).",
    )


class BackendTransportWazzupSettings(BaseModel):
    url: AnyHttpUrl | None = Field(
        default=None,
        description="Base URL for Wazzup transport module (e.g., http://wazzup-module:8004).",
    )


class BackendTransportSettings(BaseModel):
    telegram: BackendTransportTelegramSettings = Field(
        default_factory=BackendTransportTelegramSettings,
        description="Transport integration settings scoped per connector type.",
    )
    wappi: BackendTransportWappiSettings = Field(
        default_factory=BackendTransportWappiSettings,
        description="Wappi transport integration settings.",
    )
    wazzup: BackendTransportWazzupSettings = Field(
        default_factory=BackendTransportWazzupSettings,
        description="Wazzup transport integration settings.",
    )


class SalesAgentTransportTelegramSettings(BaseModel):
    endpoint: AnyHttpUrl | None = Field(
        default=None,
        description="Base URL for Telegram transport module (e.g., http://localhost:8081).",
    )


class SalesAgentTransportSettings(BaseModel):
    telegram: SalesAgentTransportTelegramSettings = Field(
        default_factory=SalesAgentTransportTelegramSettings,
        description="Transport integration settings for Sales Agent.",
    )


class DatabaseSettings(BaseModel):
    url: str | None = None


class LangfuseSettings(BaseModel):
    enabled: bool = False
    public_key: SecretStr | None = None
    secret_key: SecretStr | None = None
    host: str | None = None
    sample_rate: float = 1.0
    enable_generation_callback_only: bool = True


class YandexSettings(BaseModel):
    token: str | None = None


class LLMSettings(BaseModel):
    base_url: str = "https://api.openai.com/v1"
    api_key: SecretStr | None = None
    light_model: str = "gpt-4o-mini"
    large_model: str = "gpt-4o"


class RedisSettings(BaseModel):
    url: str | None = None


class EventBrokerType(StrEnum):
    """Supported event broker types."""

    REDIS_STREAMS = "redis_streams"


def _default_consumer_name() -> str:
    """Generate default consumer name from hostname."""
    import socket

    return socket.gethostname()


class EventStreamSettings(BaseModel):
    """Configuration for the single event stream."""

    name: str = Field(
        default="backend.events",
        description="Broker stream name (e.g., backend.events)",
    )
    group: str = Field(
        default="",
        description="Consumer group name (e.g., sales-agent)",
    )
    consumer_name: str = Field(
        default_factory=_default_consumer_name,
        description="Consumer instance name (defaults to hostname)",
    )
    block_ms: int = Field(default=5000, ge=100, le=60000)
    count: int = Field(default=10, ge=1, le=100)


class EventingSettings(BaseModel):
    """
    Event bus configuration (single-stream design).

    When enabled=True, stream.group and stream.consumer_name must be set (fail-fast).
    """

    enabled: bool = Field(
        default=False,
        description="Enable event bus. App will fail to start if misconfigured.",
    )
    broker: EventBrokerType = Field(
        default=EventBrokerType.REDIS_STREAMS,
        description="Event broker type.",
    )
    stream: EventStreamSettings = Field(
        default_factory=EventStreamSettings,
        description="Single stream configuration.",
    )

    def validate_if_enabled(self, redis_url: str | None) -> None:
        """
        Validate configuration if eventing is enabled.

        Raises:
            ValueError: If configuration is invalid
        """
        if not self.enabled:
            return

        if self.broker == EventBrokerType.REDIS_STREAMS and not redis_url:
            raise ValueError("Eventing enabled with redis_streams broker but REDIS__URL is not set")

        if not self.stream.group:
            raise ValueError("Eventing enabled but EVENTING__STREAM__GROUP is not set")

        if not self.stream.consumer_name:
            raise ValueError("Eventing enabled but EVENTING__STREAM__CONSUMER_NAME is not set")


class DebounceSettings(BaseModel):
    window_seconds: int = Field(
        default=45,
        description="Global debounce silence window, sec",
        ge=1,
        le=300,
    )
    per_channel: dict[str, int] = Field(default_factory=dict, description="Per-channel overrides")


class ConnectorDebounceSettings(BaseModel):
    window_seconds: int | None = Field(
        default=None,
        description="Override silent window for this connector",
        ge=1,
        le=300,
    )
    max_batch_messages: int | None = Field(
        default=None,
        description="Optional hard limit for batch size",
        ge=1,
    )
    storage_key_template: str | None = Field(
        default=None,
        description=(
            "Format string for debounce bucket key. "
            "Supports placeholders like {connector_id}, {conversation_id}, "
            "{user_id}, {channel_type}, and metadata keys."
        ),
    )

    def resolve_window(self, fallback: int) -> int:
        return self.window_seconds or fallback

    def render_storage_key(
        self,
        *,
        connector_id: str,
        conversation_id: str,
        user_id: str,
        channel_type: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> str:
        if self.storage_key_template:
            context: dict[str, Any] = {
                "connector_id": connector_id,
                "conversation_id": conversation_id,
                "user_id": user_id,
                "channel_type": channel_type or "",
            }
            if metadata:
                for key, value in metadata.items():
                    if isinstance(value, (str, int, float)):
                        context.setdefault(key, value)
            try:
                rendered = str(self.storage_key_template.format(**context)).strip()
                if rendered:
                    return rendered
            except Exception:
                pass
        return f"{connector_id}:{conversation_id}"


class ConnectorSecretSettings(BaseModel):
    token: SecretStr | None = None
    extra: dict[str, SecretStr] = Field(default_factory=dict)

    def get_secret(self, key: str) -> SecretStr | None:
        if key == "token":
            return self.token
        return self.extra.get(key)


class ConnectorCallbackSettings(BaseModel):
    delivery_url: str | None = None
    poll_url: str | None = None
    proxy_url: str | None = None
    handoff_url: str | None = None

    def public(self) -> dict[str, str]:
        data = {
            "delivery_url": self.delivery_url,
            "poll_url": self.poll_url,
            "proxy_url": self.proxy_url,
            "handoff_url": self.handoff_url,
        }
        return {key: value for key, value in data.items() if value}


class ConnectorTransportRetrySettings(BaseModel):
    max_attempts: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of delivery attempts including the first call.",
    )
    backoff_schedule_ms: list[int] = Field(
        default_factory=lambda: [1000, 5000, 15000],
        min_length=1,
        description="Explicit backoff delays in milliseconds between retries.",
    )
    connect_timeout_s: float = Field(
        default=2.0,
        gt=0.0,
        description="Connection timeout per attempt in seconds.",
    )
    read_timeout_s: float = Field(
        default=6.0,
        gt=0.0,
        description="Read timeout per attempt in seconds.",
    )
    total_timeout_s: float = Field(
        default=8.0,
        gt=0.0,
        description="Overall timeout per attempt in seconds.",
    )


class ConnectorTransportSettings(BaseModel):
    model_config = {"extra": "ignore"}

    enabled: bool = Field(
        default=False,
        description="Whether transport push delivery is enabled for the connector.",
    )
    endpoint: AnyHttpUrl | None = Field(
        default=None,
        description="Base URL for transport delivery endpoint.",
    )
    retries: ConnectorTransportRetrySettings = Field(default_factory=ConnectorTransportRetrySettings)

    def is_configured(self) -> bool:
        return bool(self.endpoint) and self.enabled

    def public(self) -> dict[str, Any]:
        data: dict[str, Any] = {"enabled": bool(self.enabled)}
        if not self.is_configured():
            return data

        data["endpoint"] = str(self.endpoint)
        data["retries"] = self.retries.model_dump()
        return data


class ConnectorSettings(BaseModel):
    connector_id: str | None = None
    type: str = Field(
        default="messaging",
        description="High-level connector type (e.g., crm, messaging)",
    )
    channel_type: str | None = Field(
        default=None,
        description="Legacy single-channel identifier used in payload metadata",
    )
    channel_types: list[str] = Field(
        default_factory=list,
        description="List of channel identifiers served by this connector",
    )
    debounce: ConnectorDebounceSettings = Field(default_factory=ConnectorDebounceSettings)
    secrets: ConnectorSecretSettings = Field(default_factory=ConnectorSecretSettings)
    callbacks: ConnectorCallbackSettings = Field(default_factory=ConnectorCallbackSettings)
    transport: ConnectorTransportSettings = Field(default_factory=ConnectorTransportSettings)
    metadata: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True

    def assign_defaults(self, key: str) -> None:
        if not self.connector_id:
            self.connector_id = key
        if self.channel_type and self.channel_type not in self.channel_types:
            self.channel_types.insert(0, self.channel_type)
        deduped: dict[str, bool] = {}
        ordered: list[str] = []
        for item in self.channel_types:
            if item and item not in deduped:
                deduped[item] = True
                ordered.append(item)
        self.channel_types = ordered

    def matches_channel(self, channel_type: str | None) -> bool:
        if not channel_type:
            return False
        return channel_type in self.channel_types

    def sanitized(self) -> dict[str, Any]:
        transport = self.transport.public()
        return {
            "connector_id": self.connector_id,
            "type": self.type,
            "channel_types": list(self.channel_types),
            "callbacks": self.callbacks.public(),
            "enabled": self.enabled,
            "metadata": dict(self.metadata or {}),
            "transport": transport,
        }


class EmbeddingAPISettings(BaseModel):
    base_url: str | None = None
    api_key: SecretStr | None = None
    model: str = "BAAI/bge-m3"
    dimension: int = 1024
    timeout_s: float = 30.0


class QdrantSettings(BaseModel):
    url: str | None = None
    api_key: SecretStr | None = None
    collection_prefix: str = "kb"
    prefer_sparse: bool = False


class RerankerAPISettings(BaseModel):
    enabled: bool = False
    api_key: SecretStr | None = None
    model: str = ""
    timeout_s: float = 30.0


class RagSettings(BaseModel):
    enabled: bool = True
    default_kb: str = "default"
    embedding: EmbeddingAPISettings = EmbeddingAPISettings()
    qdrant: QdrantSettings = QdrantSettings()
    reranker: RerankerAPISettings = RerankerAPISettings()

    # Chunking defaults
    chunk_max_tokens: int = 800
    chunk_overlap_tokens: int = 120


class HumanizerSettings(BaseModel):
    enabled: bool = True


class FaqSettings(BaseModel):
    enabled: bool = True
    threshold: float = Field(default=0.82, ge=0.0, le=1.0)
    path: str | None = None
    use_qdrant: bool = False
    kb_name: str = "faq"


class AudioTranscribeSettings(BaseModel):
    model: str = Field(default="gpt-4o-mini-transcribe", description="OpenAI model for transcription")
    base_url: str | None = Field(default=None, description="Override API endpoint (defaults to OpenAI)")
    api_key: SecretStr | None = Field(default=None, description="API key for transcription service")
    max_audio_bytes: int = Field(default=15_000_000, description="Maximum audio file size in bytes")
    supported_mimes: list[str] = Field(
        default_factory=lambda: ["audio/ogg", "audio/opus", "audio/mpeg"],
        description="Supported MIME types for audio",
    )
    timeout_s: float = Field(default=60.0, description="Request timeout in seconds")
    transcode_enabled: bool = Field(
        default=True,
        description=("Transcode inputs (e.g., OGG/OPUS) to WAV 16k mono before transcription"),
    )
    ffmpeg_path: str = Field(
        default="ffmpeg",
        description="Path to ffmpeg executable for audio transcoding",
    )


class S3Settings(BaseModel):
    endpoint_url: str = Field(
        ...,
        description="S3-compatible endpoint URL (e.g., http://minio:9000 for MinIO)",
    )
    access_key_id: SecretStr = Field(
        ...,
        description="S3 access key ID",
    )
    secret_access_key: SecretStr = Field(
        ...,
        description="S3 secret access key",
    )
    bucket_name: str = Field(
        ...,
        description="S3 bucket name for storing media files",
    )
    region_name: str | None = Field(
        default=None,
        description="S3 region name (optional, defaults to us-east-1 for MinIO)",
    )
    use_ssl: bool = Field(
        default=False,
        description="Use SSL/TLS for S3 connections (usually False for local MinIO)",
    )


class ArtifactUploadSettings(BaseModel):
    """Settings for artifact upload retry logic."""

    max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum number of retry attempts for artifact upload",
    )
    retry_delay_s: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Base delay in seconds for exponential backoff retry",
    )


class EncryptionSettings(BaseModel):
    master_key: SecretStr | None = Field(
        default=None,
        description="Master encryption key for envelope encryption (Fernet-compatible, 32+ bytes base64).",
    )


class CommonSettingsBase(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=SHARED_ENV_FILES,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
    )

    app: AppSettings = AppSettings()
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    sales_agent: SalesAgentServiceSettings = SalesAgentServiceSettings()
    service: ServiceAuthSettings = ServiceAuthSettings()
    cors: CorsSettings = CorsSettings()
    eventing: EventingSettings = Field(default_factory=EventingSettings)
    s3: S3Settings = Field(default_factory=S3Settings)
    artifact_upload: ArtifactUploadSettings = Field(default_factory=ArtifactUploadSettings)
    encryption: EncryptionSettings = Field(default_factory=EncryptionSettings)

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)
        header = (self.service.header or "").strip()
        if not header:
            self.service.header = "X-Service-Key"

        self.eventing.validate_if_enabled(self.redis.url)

    @property
    def resolved_database_url(self) -> str:
        """Get database URL from settings with validation.

        Raises:
            ValueError: If DATABASE__URL is not configured.
        """
        if not self.database.url:
            raise ValueError("DATABASE__URL is not configured")

        return self.database.url


class SalesAgentSettings(CommonSettingsBase):
    _env_files: tuple[str, ...] = (
        *SHARED_ENV_FILES,
        *_collect_env_files(
            PROJECT_ROOT / "apps" / "sales-agent" / ".env",
            ACTIVE_ENVIRONMENT,
            ENV_EXPLICIT,
        ),
    )
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    bot: BotSettings = BotSettings()
    llm: LLMSettings = LLMSettings()
    langfuse: LangfuseSettings = LangfuseSettings()
    yandex: YandexSettings = YandexSettings()
    debounce: DebounceSettings = Field(default_factory=DebounceSettings)
    connectors: dict[str, ConnectorSettings] = Field(default_factory=dict)
    rag: RagSettings = RagSettings()
    humanizer: HumanizerSettings = HumanizerSettings()
    faq: FaqSettings = FaqSettings()
    backend: BackendSettings = BackendSettings()
    audio: AudioTranscribeSettings = AudioTranscribeSettings()
    transport: SalesAgentTransportSettings = Field(default_factory=SalesAgentTransportSettings)
    connectors_refresh_interval_s: float = Field(
        default=1800.0,
        ge=0.0,
        le=3600.0,
        description=(
            "Background refresh interval for connector configuration "
            "fetched from backend. Set to 0 to disable periodic refresh."
        ),
    )

    def model_post_init(self, __context: Any) -> None:
        super().model_post_init(__context)

        connectors: dict[str, ConnectorSettings] = dict(self.connectors or {})

        for key, cfg in connectors.items():
            cfg.assign_defaults(key)

        self.connectors = connectors

    def get_connector(self, connector_id: str | None) -> ConnectorSettings | None:
        if not connector_id:
            return None
        return self.connectors.get(connector_id)

    def get_connector_by_channel(self, channel_type: str | None) -> ConnectorSettings | None:
        if not channel_type:
            return None
        for cfg in self.connectors.values():
            if cfg.matches_channel(channel_type):
                return cfg
        return None

    def get_default_connector(self) -> ConnectorSettings | None:
        for cfg in self.connectors.values():
            if cfg.enabled:
                return cfg
        return None


class TelegramModuleSettings(CommonSettingsBase):
    _env_files: tuple[str, ...] = (
        *SHARED_ENV_FILES,
        *_collect_env_files(
            PROJECT_ROOT / "apps" / "telegram-module" / ".env",
            ACTIVE_ENVIRONMENT,
            ENV_EXPLICIT,
        ),
    )
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    backend: BackendSettings = BackendSettings()
    public_url: AnyHttpUrl | None = Field(default=None, alias="TELEGRAM_MODULE_PUBLIC_URL")
    default_mode: Literal["polling"] = "polling"
    backend_bots_path: str = "/transport/telegram/bots"
    request_timeout_s: float = Field(
        default=100.0,
        alias="TELEGRAM_MODULE_REQUEST_TIMEOUT_S",
        description="Default HTTP timeout for backend and Sales Agent requests.",
    )
    config_refresh_interval_s: float = Field(
        default=120.0,
        alias="TELEGRAM_MODULE_CONFIG_REFRESH_INTERVAL_S",
        description="Background refresh interval for bot configuration.",
    )
    signature_tolerance_s: int = Field(
        default=300,
        alias="TELEGRAM_MODULE_SIGNATURE_TOLERANCE_S",
        description="Fallback timestamp tolerance when connector-specific value is absent.",
    )
    max_delivery_attempts: int = Field(
        default=3,
        alias="TELEGRAM_MODULE_MAX_DELIVERY_ATTEMPTS",
        ge=1,
        le=10,
        description="Maximum retries when delivering messages to Telegram API.",
    )
    alert_after_failures: int = Field(
        default=2,
        alias="TELEGRAM_MODULE_ALERT_AFTER_FAILURES",
        ge=1,
        description="Number of consecutive failures before raising alert events.",
    )
    drop_pending_on_webhook_reset: bool = Field(
        default=True,
        alias="TELEGRAM_MODULE_DROP_PENDING_ON_WEBHOOK_RESET",
        description="Drop pending updates when reconfiguring webhooks.",
    )
    polling_timeout_s: float = Field(
        default=25.0,
        alias="TELEGRAM_MODULE_POLLING_TIMEOUT_S",
        gt=0,
        description="Long polling timeout passed to the Telegram Bot API.",
    )

    @property
    def sales_agent_url(self) -> AnyHttpUrl:
        if not self.sales_agent.url:
            raise ValueError("SALES_AGENT__URL is not configured")
        return self.sales_agent.url


class WappiModuleSettings(CommonSettingsBase):
    _env_files: tuple[str, ...] = (
        *SHARED_ENV_FILES,
        *_collect_env_files(
            PROJECT_ROOT / "apps" / "wappi-module" / ".env",
            ACTIVE_ENVIRONMENT,
            ENV_EXPLICIT,
        ),
    )
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    backend: BackendSettings = BackendSettings()
    request_timeout_s: float = Field(
        default=10.0,
        alias="WAPPI_MODULE_REQUEST_TIMEOUT_S",
        description="Default HTTP timeout for backend and Sales Agent requests.",
    )
    config_refresh_interval_s: float = Field(
        default=60.0,
        alias="WAPPI_MODULE_CONFIG_REFRESH_INTERVAL_S",
        description="Background refresh interval for connector configuration.",
    )
    max_delivery_attempts: int = Field(
        default=3,
        alias="WAPPI_MODULE_MAX_DELIVERY_ATTEMPTS",
        ge=1,
        le=10,
        description="Maximum retries when delivering messages to Wappi API.",
    )
    initial_sync_messages_limit: int = Field(
        default=50,
        alias="WAPPI_MODULE_INITIAL_SYNC_MESSAGES_LIMIT",
        ge=1,
        le=1000,
        description=(
            "Maximum number of messages to sync per "
            "dialog during initial sync. "
            "Full history is synced when user sends a message."
        ),
    )
    initial_sync_dialogs_limit: int = Field(
        default=50,
        alias="WAPPI_MODULE_INITIAL_SYNC_DIALOGS_LIMIT",
        ge=1,
        le=200,
        description=(
            "Maximum number of dialogs to sync during initial sync. "
            "Full dialog history is synced when user sends a message from that dialog."
        ),
    )
    audio: AudioTranscribeSettings = AudioTranscribeSettings()

    @property
    def sales_agent_url(self) -> AnyHttpUrl:
        if not self.sales_agent.url:
            raise ValueError("SALES_AGENT__URL is not configured")
        return self.sales_agent.url


class WazzupModuleSettings(CommonSettingsBase):
    _env_files: tuple[str, ...] = (
        *SHARED_ENV_FILES,
        *_collect_env_files(
            PROJECT_ROOT / "apps" / "wazzup-module" / ".env",
            ACTIVE_ENVIRONMENT,
            ENV_EXPLICIT,
        ),
    )
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )

    backend: BackendSettings = BackendSettings()
    request_timeout_s: float = Field(
        default=10.0,
        alias="WAZZUP_MODULE_REQUEST_TIMEOUT_S",
        description="Default HTTP timeout for backend requests.",
    )
    config_refresh_interval_s: float = Field(
        default=60.0,
        alias="WAZZUP_MODULE_CONFIG_REFRESH_INTERVAL_S",
        description="Background refresh interval for connector configuration.",
    )
    max_delivery_attempts: int = Field(
        default=3,
        alias="WAZZUP_MODULE_MAX_DELIVERY_ATTEMPTS",
        ge=1,
        le=10,
        description="Maximum retries when delivering messages to Wazzup API.",
    )
    webhook_url: AnyHttpUrl | None = Field(
        default=None,
        alias="WAZZUP_MODULE_WEBHOOK_URL",
        description="Public URL where Wazzup24 sends webhooks (e.g. https://our-domain.com/wazzup/webhook).",
    )


class SentrySettings(BaseModel):
    dsn: str | None = Field(default=None, description="Sentry DSN for error tracking")
    send_default_pii: bool = Field(default=True, description="Send PII like request headers and IP")
    traces_sample_rate: float = Field(default=0.5, ge=0.0, le=1.0, description="Sample rate for tracing")
    environment: str | None = Field(default=None, description="Environment name for Sentry")

    def is_enabled(self) -> bool:
        return bool(self.dsn)


class AuthSettings(BaseModel):
    jwt_secret_key: SecretStr = Field(
        description=("Secret key for JWT token signing. Must be set via AUTH__JWT_SECRET_KEY environment variable.")
    )
    jwt_algorithm: str = Field(
        default="HS256",
        description="JWT signing algorithm.",
    )
    access_token_expire_minutes: int = Field(
        default=15,
        ge=1,
        le=1440,
        description="Access token expiration time in minutes.",
    )
    refresh_token_expire_days: int = Field(
        default=30,
        ge=1,
        le=365,
        description="Refresh token expiration time in days.",
    )


class BackendModuleSettings(CommonSettingsBase):
    _env_files: tuple[str, ...] = (
        *SHARED_ENV_FILES,
        *_collect_env_files(
            PROJECT_ROOT / "apps" / "backend" / ".env",
            ACTIVE_ENVIRONMENT,
            ENV_EXPLICIT,
        ),
    )
    transport: BackendTransportSettings = BackendTransportSettings()
    auth: AuthSettings = Field(default_factory=AuthSettings)
    sentry: SentrySettings = Field(default_factory=SentrySettings)
    model_config = SettingsConfigDict(
        env_file=_env_files,
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        populate_by_name=True,
    )


Settings = SalesAgentSettings
