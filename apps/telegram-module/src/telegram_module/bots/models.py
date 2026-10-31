from __future__ import annotations

from enum import Enum

from pydantic import SecretStr

from common.transport.base_config import BaseConnectorConfig


class BotMode(str, Enum):
    AUTO = "auto"
    WEBHOOK = "webhook"
    POLLING = "polling"


class BotConfig(BaseConnectorConfig):
    bot_token: SecretStr
    mode: BotMode = BotMode.AUTO
    webhook_secret: SecretStr | None = None
    webhook_path: str | None = None

    # AICODE-NOTE: connector_id, company_id, channel_type, metadata and their
    # normalization are inherited from BaseConnectorConfig.

    def resolved_mode(self, default_mode: BotMode) -> BotMode:
        if self.mode == BotMode.AUTO:
            return default_mode
        return self.mode
