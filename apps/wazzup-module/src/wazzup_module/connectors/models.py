from __future__ import annotations

from pydantic import SecretStr, model_validator

from common.transport.base_config import BaseConnectorConfig


class WazzupConnectorConfig(BaseConnectorConfig):
    wazzup_api_key: SecretStr
    channel_id: str

    @model_validator(mode="after")
    def _normalize_wazzup_fields(self) -> WazzupConnectorConfig:
        self.channel_id = self.channel_id.strip()
        if not self.channel_id:
            raise ValueError("channel_id must be provided")
        return self
