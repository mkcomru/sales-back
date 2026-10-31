"""YClients credential and configuration schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.backend.modules.integrations.schemas import ConfigFieldSchema, CredentialFieldSchema

YCLIENTS_BASE_URL = "https://api.yclients.com"
YCLIENTS_RATE_LIMIT_RPS = 5.0

CREDENTIAL_FIELDS = [
    CredentialFieldSchema(
        key="partner_token",
        label="Partner Token",
        field_type="password",
        required=True,
        placeholder="Bearer-токен из маркетплейса YClients",
    ),
]

CONFIG_FIELDS = [
    ConfigFieldSchema(
        key="yclients_company_id",
        label="ID филиала в YClients",
        field_type="number",
        required=True,
        placeholder="123456",
    ),
    ConfigFieldSchema(
        key="form_id",
        label="ID формы бронирования",
        field_type="string",
        required=False,
        placeholder="w12345 (опционально)",
    ),
]


class YClientsCredentials(BaseModel):
    partner_token: str = Field(min_length=1)


class YClientsConfig(BaseModel):
    yclients_company_id: int
    form_id: str | None = None
