from __future__ import annotations

from pydantic import SecretStr, model_validator

from common.transport.base_config import BaseConnectorConfig


class WappiConnectorConfig(BaseConnectorConfig):
    wappi_token: SecretStr
    wappi_profile_id: str

    # AICODE-NOTE: connector_id, company_id, channel_type, metadata and their
    # normalization are inherited from BaseConnectorConfig.

    @model_validator(mode="after")
    def _normalize_wappi_fields(self) -> WappiConnectorConfig:
        self.wappi_profile_id = self.wappi_profile_id.strip()
        if not self.wappi_profile_id:
            raise ValueError("wappi_profile_id must be provided")
        return self
