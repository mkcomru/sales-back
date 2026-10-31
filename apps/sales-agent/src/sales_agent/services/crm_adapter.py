from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from common import SalesAgentSettings as Settings
from common.config import ConnectorSettings
from common.models.io import SimpleMessage

from src.sales_agent.agents.stage import to_crm_stage
from src.sales_agent.services.domain_config import load_domain_config

log = structlog.get_logger(__name__)


def _normalize_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


@dataclass(slots=True)
class CRMAdapter:
    settings: Settings

    def resolve_stage_id(self, stage_name: str | None) -> str | None:
        """Map internal stage identifier to CRM-specific stage_id."""
        normalized = _normalize_str(stage_name)
        if not normalized:
            return None
        mapped = to_crm_stage(normalized)
        if mapped:
            return mapped
        return normalized

    def default_stage_id(self) -> str:
        cfg = load_domain_config()
        stage_id = self.resolve_stage_id(cfg.crm_default_stage_id)
        return stage_id or cfg.crm_default_stage_id

    def manager_attention_stage_id(self) -> str:
        cfg = load_domain_config()
        stage_id = self.resolve_stage_id(cfg.crm_manager_attention_stage_id)
        return stage_id or cfg.crm_manager_attention_stage_id

    def initial_stage_id(self) -> str:
        """Stage applied when dialog starts without explicit CRM stage."""
        return self.resolve_stage_id("IN_PROCESS") or "IN_PROCESS"

    def finalize_stage_id(self, stage_id: str | None) -> str:
        resolved = self.resolve_stage_id(stage_id)
        return resolved or self.initial_stage_id()

    def filter_forward_metadata(self, metadata: Mapping[str, Any] | None) -> dict[str, Any]:
        cfg = load_domain_config()
        allowlist = tuple(cfg.crm_forward_metadata_keys or ())
        if not allowlist or not metadata:
            return {}

        filtered: dict[str, Any] = {}
        for key in allowlist:
            if key not in metadata:
                continue
            value = metadata[key]
            if isinstance(value, (str, int, float, bool)):
                filtered[key] = value
            elif value is not None:
                filtered[key] = str(value)
        return filtered

    def _resolve_connector(
        self,
        metadata: Mapping[str, Any] | None,
    ) -> ConnectorSettings | None:
        connector_id = _normalize_str(metadata.get("connector_id")) if metadata else None
        if connector_id:
            connector = self.settings.get_connector(connector_id)
            if connector is not None:
                return connector

        channel_type = _normalize_str(metadata.get("channel_type")) if metadata else None
        if channel_type:
            connector = self.settings.get_connector_by_channel(channel_type)
            if connector is not None:
                return connector

        return self.settings.get_default_connector()

    def _resolve_conversation_id(self, metadata: Mapping[str, Any] | None, message: SimpleMessage) -> str:
        if metadata and metadata.get("conversation_id"):
            return str(metadata["conversation_id"])
        if message.chat and message.chat.id is not None:
            return str(message.chat.id)
        return "unknown"

    async def notify_handoff(
        self,
        message: SimpleMessage,
        summary: Mapping[str, Any],
        stage: str | None = None,
        *,
        operator: bool | None = None,
    ) -> None:
        """Forward handoff notification to CRM proxy."""
        metadata = message.metadata if isinstance(message.metadata, Mapping) else {}
        connector = self._resolve_connector(metadata)
        if connector is None:
            log.debug("crm_adapter.handoff.connector_missing")
            return

        proxy_url = _normalize_str(connector.callbacks.proxy_url)
        if not proxy_url:
            log.debug(
                "crm_adapter.handoff.proxy_url_missing",
                connector_id=connector.connector_id,
            )
            return

        token_secret = connector.secrets.token
        if token_secret is None:
            log.warning(
                "crm_adapter.handoff.token_missing",
                connector_id=connector.connector_id,
            )
            return

        summary_text = _normalize_str(summary.get("text")) if summary else None
        if not summary_text:
            log.debug(
                "crm_adapter.handoff.summary_empty",
                connector_id=connector.connector_id,
            )
            return

        stage_candidates = (
            stage,
            summary.get("stage") if summary else None,
            summary.get("stage_id") if summary else None,
        )
        resolved_stage_id: str | None = None
        for candidate in stage_candidates:
            resolved_stage_id = self.resolve_stage_id(candidate)
            if resolved_stage_id:
                break
        if not resolved_stage_id:
            resolved_stage_id = self.default_stage_id()

        payload: dict[str, Any] = {
            "token": token_secret.get_secret_value(),
            "conversation_id": self._resolve_conversation_id(metadata, message),
            "summary": summary_text,
            "reason": (_normalize_str(summary.get("reason")) if summary else None),
            "stage_id": resolved_stage_id,
        }

        forwarded = self.filter_forward_metadata(metadata)
        if forwarded:
            payload.update(forwarded)

        if operator is not None:
            payload["operator"] = bool(operator)

        url = proxy_url.rstrip("/") + "/handoff"
        timeout = httpx.Timeout(5.0, connect=3.0)

        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                log.info(
                    "crm_adapter.handoff.sent",
                    connector_id=connector.connector_id,
                    status=response.status_code,
                )
            except httpx.HTTPError as exc:  # pragma: no cover - network path
                response = getattr(exc, "response", None)
                status_code = getattr(response, "status_code", None) if response else None
                log.warning(
                    "crm_adapter.handoff.failed",
                    connector_id=connector.connector_id,
                    error=str(exc),
                    status=status_code,
                )
