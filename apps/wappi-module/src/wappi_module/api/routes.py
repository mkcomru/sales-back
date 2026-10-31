from __future__ import annotations

import asyncio
import json
from http import HTTPStatus
from uuid import uuid4

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status

from common.contracts.sync import SyncCancelCommand, SyncMessage, SyncStartCommand
from common.sync.client import BackendSyncClient
from wappi_module.api.dependencies import (
    get_backend_client,
    get_connector_manager,
    get_sales_agent_client,
    get_settings_dep,
    get_sync_controller,
    get_transport_service,
    get_wappi_client,
    require_service_api_key,
)
from wappi_module.config import Settings
from wappi_module.connectors.manager import ConnectorManager
from wappi_module.connectors.models import WappiConnectorConfig
from wappi_module.services.backend import WappiBackendClient
from wappi_module.services.sales_agent import BackendInboundClient
from wappi_module.services.wappi_api import WappiApiClient
from wappi_module.sync.controller import SyncController
from wappi_module.sync.provider import WappiSyncProvider
from wappi_module.transport.models import TransportDeliveryPayload
from wappi_module.transport.service import TransportDeliveryService

log = structlog.get_logger(__name__)

transport_router = APIRouter(tags=["transport"])
admin_router = APIRouter(prefix="/admin", tags=["admin"])
health_router = APIRouter(tags=["health"])
wappi_router = APIRouter(prefix="/wappi", tags=["wappi"])
internal_router = APIRouter(prefix="/internal", tags=["internal"])


@transport_router.post(
    "/transport/delivery",
    status_code=status.HTTP_202_ACCEPTED,
)
async def transport_delivery(
    request: Request,
    service: TransportDeliveryService = Depends(get_transport_service),
) -> dict[str, str]:
    raw_body = await request.body()
    try:
        data = json.loads(raw_body.decode("utf-8") or "{}")
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid JSON body") from exc

    try:
        payload = TransportDeliveryPayload.model_validate(data)
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return await service.handle(payload=payload, headers=dict(request.headers))


@admin_router.post("/reload", status_code=status.HTTP_202_ACCEPTED)
async def reload_connectors(
    manager: ConnectorManager = Depends(get_connector_manager),
) -> dict[str, str]:
    await manager.reload()
    return {"status": "reloaded"}


@health_router.get("/healthz")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@wappi_router.post("/{connector_id}/webhook", status_code=HTTPStatus.ACCEPTED)
async def wappi_webhook(
    connector_id: str,
    request: Request,
    manager: ConnectorManager = Depends(get_connector_manager),
    sales_agent: BackendInboundClient = Depends(get_sales_agent_client),
    wappi_client: WappiApiClient = Depends(get_wappi_client),
    backend_client: WappiBackendClient = Depends(get_backend_client),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, str]:
    try:
        payload = await request.json()
    except Exception as exc:
        log.warning(
            "wappi.webhook.invalid_json",
            connector_id=connector_id,
            error=str(exc),
            content_type=request.headers.get("content-type"),
        )
        raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

    log.info(
        "wappi.webhook.received",
        connector_id=connector_id,
        payload_keys=list(payload.keys()) if isinstance(payload, dict) else [],
        payload_type=type(payload).__name__,
    )

    connector = manager.get(connector_id)
    if connector is None:
        log.warning(
            "wappi.webhook.connector_not_found",
            connector_id=connector_id,
            available_connectors=list(manager._connectors.keys()),
        )
        raise HTTPException(
            status_code=404,
            detail=f"Unknown connector '{connector_id}'. Available: {list(manager._connectors.keys())}",
        )

    # AICODE-NOTE: Обработка исходящих сообщений от менеджера
    # Webhook приходит на ВСЕ исходящие сообщения (от assistant и от manager)
    # Логика:
    # - from_where="api" → assistant (уже в БД, пропускаем)
    # - from_where!="api" → manager (помечаем флагом для sales-agent)
    messages = payload.get("messages", [])
    if isinstance(messages, list):
        for msg in messages:
            if not isinstance(msg, dict):
                continue

            wh_type = msg.get("wh_type", "")
            from_where = msg.get("from_where", "").lower()
            is_me = msg.get("is_me", False)

            # Проверяем: это исходящее сообщение?
            is_outgoing = "outgoing" in wh_type.lower() or is_me

            if is_outgoing:
                # Проверяем: это НЕ через API (значит manager)?
                if from_where and from_where != "api":
                    # Это менеджер пишет из веб/устройства
                    msg["_manager_outgoing"] = True
                    log.debug(
                        "wappi.webhook.manager_outgoing_detected",
                        connector_id=connector_id,
                        from_where=from_where,
                        msg_id=msg.get("id"),
                    )
                elif not from_where:
                    # Поле from_where пустое, но это исходящее → скорее всего manager
                    # Пометим и sales-agent проверит по БД
                    msg["_manager_outgoing"] = True
                    log.debug(
                        "wappi.webhook.outgoing_no_from_where",
                        connector_id=connector_id,
                        msg_id=msg.get("id"),
                    )

    log.debug(
        "wappi.webhook.forwarding",
        connector_id=connector_id,
        company_id=connector.company_id,
        channel_type=connector.channel_type,
    )

    try:
        await sales_agent.forward_update(connector_id, connector, payload)
    except Exception as exc:
        log.error(
            "wappi.webhook.forward_failed",
            connector_id=connector_id,
            company_id=connector.company_id,
            error=str(exc),
            exc_type=type(exc).__name__,
        )
        raise HTTPException(status_code=502, detail=f"Failed to forward to sales agent: {exc}") from exc

    log.info(
        "wappi.webhook.forwarded",
        connector_id=connector_id,
        company_id=connector.company_id,
    )

    # AICODE-NOTE: Trigger background sync for conversation history
    # Extract unique conversation_ids from incoming messages and sync their full history
    # Uses existing sync infrastructure with idempotency via provider_message_id
    if isinstance(messages, list):
        conversation_ids = set()
        for msg in messages:
            if isinstance(msg, dict):
                chat_id = msg.get("chatId")
                if chat_id:
                    conversation_ids.add(str(chat_id))

        # Trigger sync for each unique conversation
        for conversation_id in conversation_ids:
            asyncio.create_task(
                _sync_conversation_history(
                    connector_id=connector_id,
                    conversation_id=conversation_id,
                    connector=connector,
                    wappi_client=wappi_client,
                    backend_client=backend_client,
                    settings=settings,
                )
            )

    return {"status": "forwarded"}


@wappi_router.post(
    "/sync/{connector_id}/conversation/{conversation_id}",
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_conversation_history_manual(
    connector_id: str,
    conversation_id: str,
    manager: ConnectorManager = Depends(get_connector_manager),
    wappi_client: WappiApiClient = Depends(get_wappi_client),
    backend_client: WappiBackendClient = Depends(get_backend_client),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, str]:
    """Manually trigger full history sync for a specific conversation.

    Called by backend when user requests full history sync via API.
    Reuses existing _sync_conversation_history logic.

    Args:
        connector_id: Connector identifier
        conversation_id: Conversation/chat ID to sync

    Returns:
        Status message
    """
    connector = manager.get(connector_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    log.info(
        "wappi.conversation_sync.manual_trigger",
        connector_id=connector_id,
        conversation_id=conversation_id,
        channel_type=connector.channel_type,
    )

    # Trigger background sync (reuses existing logic)
    asyncio.create_task(
        _sync_conversation_history(
            connector_id=connector_id,
            conversation_id=conversation_id,
            connector=connector,
            wappi_client=wappi_client,
            backend_client=backend_client,
            settings=settings,
        )
    )

    return {"status": "sync_triggered", "conversation_id": conversation_id}


@wappi_router.post(
    "/sync/{connector_id}/more-chats",
    status_code=status.HTTP_202_ACCEPTED,
)
async def sync_more_chats(
    connector_id: str,
    manager: ConnectorManager = Depends(get_connector_manager),
    wappi_client: WappiApiClient = Depends(get_wappi_client),
    backend_client: WappiBackendClient = Depends(get_backend_client),
    settings: Settings = Depends(get_settings_dep),
) -> dict[str, str]:
    """Load more chats for a connector.

    Continues loading chats that weren't included in initial sync.
    Gets existing conversation_ids from backend and fetches only new chats from Wappi.

    For each new chat:
    - Parses initial_sync_messages_limit messages
    - Uploads media to S3 with artifact_ids
    - Creates Thread and ChatMessage records

    Args:
        connector_id: Connector identifier

    Returns:
        Status message
    """
    connector = manager.get(connector_id)
    if not connector:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Connector {connector_id} not found",
        )

    log.info(
        "wappi.sync_more_chats.started",
        connector_id=connector_id,
        channel_type=connector.channel_type,
    )

    # Trigger background sync
    asyncio.create_task(
        _sync_more_chats_background(
            connector_id=connector_id,
            connector=connector,
            wappi_client=wappi_client,
            backend_client=backend_client,
            settings=settings,
        )
    )

    return {"status": "sync_triggered", "message": "Loading more chats"}


@wappi_router.post("/sync/{connector_id}", status_code=status.HTTP_202_ACCEPTED)
async def sync_connector_history(
    connector_id: str,
    manager: ConnectorManager = Depends(get_connector_manager),
    sales_agent: BackendInboundClient = Depends(get_sales_agent_client),
    wappi_client: WappiApiClient = Depends(get_wappi_client),
) -> dict:
    """
    Синхронизация истории сообщений из Wappi API.

    Получает все чаты и сообщения из подключенного Telegram аккаунта,
    отправляет их на sales-agent для сохранения в БД с правильными ролями.

    Решение:
    1. Получаем connector (содержит wappi_token, wappi_profile_id)
    2. Запрашиваем список чатов через GET /tapi/sync/chats/get
    3. Для каждого чата запрашиваем сообщения через GET /tapi/sync/messages/get
    4. Формируем webhook payload (как обычное сообщение) с флагом _sync_mode=true
    5. Отправляем на sales-agent через forward_update

    sales-agent при получении _sync_mode=true:
    - fromMe: false → role=user
    - fromMe: true → проверяет в БД, если уже есть (assistant отправил) → skip,
                    если нет → role=manager (оператор написал)
    """
    log.info("wappi.sync.started", connector_id=connector_id)

    connector = manager.get(connector_id)
    if connector is None:
        raise HTTPException(
            status_code=404,
            detail=f"Connector '{connector_id}' not found",
        )

    if not connector.wappi_token or not connector.wappi_profile_id:
        raise HTTPException(
            status_code=400,
            detail=f"Connector '{connector_id}' missing Wappi credentials",
        )

    # 1. Получить список чатов
    # AICODE-NOTE: Wappi API иногда возвращает 500 с параметрами
    # Пробуем минимальный набор параметров
    try:
        log.debug(
            "wappi.sync.fetching_chats",
            profile_id=connector.wappi_profile_id,
        )
        chats_data = await wappi_client.get_chats_list(
            wappi_token=connector.wappi_token.get_secret_value(),
            profile_id=connector.wappi_profile_id,
        )
    except Exception as exc:
        log.error(
            "wappi.sync.chats_failed",
            error=str(exc),
            profile_id=connector.wappi_profile_id,
        )
        # Если не удалось получить список чатов, возвращаем ошибку с деталями
        raise HTTPException(
            status_code=502,
            detail=(
                f"Failed to fetch chats from Wappi API: {exc}\n\n"
                "Возможные причины:\n"
                "1. Проблема с Wappi API (попробуйте позже)\n"
                "2. Неверный profile_id или токен\n"
                "3. Аккаунт не поддерживает синхронизацию\n\n"
                "Используйте эндпоинт GET /wappi/{connector_id}/chat/{chat_id}/history "
                "для синхронизации конкретного чата"
            ),
        ) from exc

    dialogs = chats_data.get("dialogs", [])
    log.info("wappi.sync.chats_found", count=len(dialogs))

    total_messages = 0
    total_chats = len(dialogs)

    # 2. Для каждого чата получить сообщения
    for idx, dialog in enumerate(dialogs):
        chat_id = dialog.get("id")
        if not chat_id:
            log.warning("wappi.sync.chat_no_id", dialog=dialog)
            continue

        log.debug(
            "wappi.sync.chat_processing",
            chat_id=chat_id,
            progress=f"{idx + 1}/{total_chats}",
        )

        # 3. Получить сообщения чата (макс 100 за раз)
        try:
            messages_data = await wappi_client.get_chat_messages(
                wappi_token=connector.wappi_token.get_secret_value(),
                profile_id=connector.wappi_profile_id,
                chat_id=chat_id,
                limit=100,
                order="asc",  # От старых к новым
            )
        except Exception as exc:
            log.error("wappi.sync.messages_failed", chat_id=chat_id, error=str(exc))
            continue

        messages = messages_data.get("messages", [])
        if not messages:
            log.debug("wappi.sync.chat_empty", chat_id=chat_id)
            continue

        log.debug("wappi.sync.chat_messages", chat_id=chat_id, count=len(messages))
        total_messages += len(messages)

        # 4. Отправить сообщения на sales-agent
        # Формируем payload как обычный webhook, но с флагом _sync_mode
        for msg in messages:
            # Добавляем флаг синхронизации в каждое сообщение
            msg["_sync_mode"] = True

        # Формируем webhook payload (как обычное входящее сообщение)
        webhook_payload = {"messages": messages}

        # 5. Отправляем на sales-agent
        try:
            await sales_agent.forward_update(connector_id, connector, webhook_payload)
        except Exception as exc:
            log.error(
                "wappi.sync.forward_failed",
                chat_id=chat_id,
                error=str(exc),
            )
            continue

    log.info(
        "wappi.sync.completed",
        connector_id=connector_id,
        chats=total_chats,
        messages=total_messages,
    )

    return {
        "status": "completed",
        "chats_processed": total_chats,
        "messages_sent": total_messages,
    }


@wappi_router.get("/{connector_id}/chat/{chat_id}/history", status_code=status.HTTP_200_OK)
async def get_chat_history(
    connector_id: str,
    chat_id: str,
    limit: int = 100,
    offset: int = 0,
    order: str = "desc",
    sync: bool = True,
    manager: ConnectorManager = Depends(get_connector_manager),
    sales_agent: BackendInboundClient = Depends(get_sales_agent_client),
    wappi_client: WappiApiClient = Depends(get_wappi_client),
) -> dict:
    """
    Получить историю чата с конкретным пользователем.

    Args:
        connector_id: ID коннектора
        chat_id: ID чата (может быть числовой ID или номер телефона)
        limit: Количество сообщений (макс 100)
        offset: Сдвиг для пагинации (0 = самое новое)
        order: Сортировка ("desc" = новые→старые, "asc" = старые→новые)
        sync: Синхронизировать сообщения в БД (default True)

    Returns:
        {
            "status": "ok",
            "messages": [...],
            "total_count": 2,
            "synced": true/false
        }

    Решение:
    1. Получаем историю из Wappi API через GET /tapi/sync/messages/get
    2. Если sync=true → отправляем на sales-agent с флагом _sync_mode
    3. sales-agent сохраняет с правильными ролями (user/assistant/manager)
    4. Возвращаем историю клиенту

    Удобство:
    - chat_id может быть числовым ID или номером телефона
    - Автоматическая синхронизация в БД при чтении
    - Можно отключить sync=false если нужна только выгрузка
    """
    log.info(
        "wappi.chat_history.request",
        connector_id=connector_id,
        chat_id=chat_id,
        sync=sync,
    )

    connector = manager.get(connector_id)
    if connector is None:
        raise HTTPException(
            status_code=404,
            detail=f"Connector '{connector_id}' not found",
        )

    if not connector.wappi_token or not connector.wappi_profile_id:
        raise HTTPException(
            status_code=400,
            detail=f"Connector '{connector_id}' missing Wappi credentials",
        )

    # 1. Получить сообщения из Wappi API
    try:
        messages_data = await wappi_client.get_chat_messages(
            wappi_token=connector.wappi_token.get_secret_value(),
            profile_id=connector.wappi_profile_id,
            chat_id=chat_id,
            limit=limit,
            offset=offset,
            order=order,
        )
    except Exception as exc:
        log.error(
            "wappi.chat_history.fetch_failed",
            connector_id=connector_id,
            chat_id=chat_id,
            error=str(exc),
        )
        raise HTTPException(
            status_code=502,
            detail=f"Failed to fetch chat history from Wappi: {exc}",
        ) from exc

    messages = messages_data.get("messages", [])
    total_count = messages_data.get("total_count", len(messages))

    log.debug(
        "wappi.chat_history.fetched",
        connector_id=connector_id,
        chat_id=chat_id,
        count=len(messages),
    )

    # 2. Синхронизировать в БД если sync=True
    synced = False
    if sync and messages:
        # Добавляем флаг _sync_mode к каждому сообщению
        for msg in messages:
            msg["_sync_mode"] = True

        # Формируем webhook payload
        webhook_payload = {"messages": messages}

        # Отправляем на sales-agent
        try:
            await sales_agent.forward_update(connector_id, connector, webhook_payload)
            synced = True
            log.info(
                "wappi.chat_history.synced",
                connector_id=connector_id,
                chat_id=chat_id,
                count=len(messages),
            )
        except Exception as exc:
            log.error(
                "wappi.chat_history.sync_failed",
                connector_id=connector_id,
                chat_id=chat_id,
                error=str(exc),
            )
            # Продолжаем - история всё равно возвращается

    return {
        "status": "ok",
        "total_count": total_count,
        "synced": synced,
        "chat_id": chat_id,
        "limit": limit,
        "offset": offset,
        "order": order,
    }


@internal_router.post(
    "/sync/start",
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_service_api_key)],
    summary="Start history synchronization",
    description="Start initial, backfill, or catchup sync for a connector",
)
async def start_sync(
    command: SyncStartCommand,
    controller: SyncController = Depends(get_sync_controller),
) -> dict[str, str]:
    """Start sync job for a connector.

    Args:
        command: Sync start command from backend
        controller: Sync controller instance

    Returns:
        Success response

    Raises:
        HTTPException: If connector not found or sync already running
    """
    try:
        await controller.start_sync(command)
        return {
            "status": "accepted",
            "message": f"Sync started with correlation_id: {command.correlation_id}",
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@internal_router.post(
    "/sync/cancel",
    status_code=status.HTTP_200_OK,
    dependencies=[Depends(require_service_api_key)],
    summary="Cancel history synchronization",
    description="Cancel active sync job for a connector",
)
async def cancel_sync(
    command: SyncCancelCommand,
    controller: SyncController = Depends(get_sync_controller),
) -> dict[str, str]:
    """Cancel sync job for a connector.

    Args:
        command: Sync cancel command from backend
        controller: Sync controller instance

    Returns:
        Success response

    Raises:
        HTTPException: If sync not found
    """
    try:
        await controller.cancel_sync(command)
        return {
            "status": "cancelled",
            "message": f"Sync cancelled for correlation_id: {command.correlation_id}",
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


async def _sync_conversation_history(
    connector_id: str,
    conversation_id: str,
    connector: WappiConnectorConfig,
    wappi_client: WappiApiClient,
    backend_client: WappiBackendClient,
    settings: Settings,
) -> None:
    """Background task to sync full history for a conversation.

    Triggered when incoming webhook arrives for a conversation.
    Uses existing sync infrastructure:
    - WappiSyncProvider.fetch_messages() to get all messages from Wappi API
    - WappiSyncProvider.transform_message() to normalize and process media (uploads to S3)
    - BackendSyncClient.send_batch() to send historical messages to backend
    - Backend handles idempotency via provider_message_id (duplicates are skipped)

    Works for both WhatsApp and Telegram:
    - WappiApiClient automatically uses correct endpoint based on connector.channel_type
    - Telegram: /tapi/sync/messages/get
    - WhatsApp: /api/sync/messages/get

    Args:
        connector_id: Connector identifier
        conversation_id: Chat/conversation ID to sync
        connector: Wappi connector configuration (contains channel_type, tokens, etc)
        wappi_client: Wappi API client for fetching messages
        backend_client: Backend client for uploading media to S3
        settings: Application settings (backend URL, service key)
    """
    correlation_id = f"backfill-{conversation_id}-{uuid4().hex[:8]}"

    log.info(
        "wappi.conversation_sync.started",
        connector_id=connector_id,
        conversation_id=conversation_id,
        correlation_id=correlation_id,
        channel_type=connector.channel_type,
    )

    try:
        # Check if history is already synced for this conversation
        thread_info = await backend_client.get_thread_by_conversation(
            connector_id=connector_id,
            conversation_id=conversation_id,
        )

        if thread_info is not None:
            thread_id, history_synced = thread_info
            if history_synced:
                log.info(
                    "wappi.conversation_sync.already_synced",
                    connector_id=connector_id,
                    conversation_id=conversation_id,
                    thread_id=thread_id,
                    correlation_id=correlation_id,
                )
                return

        log.debug(
            "wappi.conversation_sync.history_not_synced",
            connector_id=connector_id,
            conversation_id=conversation_id,
            thread_exists=thread_info is not None,
        )

        # Create provider (reuses existing sync infrastructure!)
        provider = WappiSyncProvider(
            connector_config=connector,
            wappi_client=wappi_client,
            backend_client=backend_client,
        )

        # Create sync client for sending batches to backend
        sync_client = BackendSyncClient(
            base_url=settings.backend.url,
            service_key=settings.service.api_key.get_secret_value(),
        )

        batch: list[SyncMessage] = []
        total_messages = 0

        # Fetch ALL messages from conversation
        # provider.fetch_messages() handles pagination automatically
        # and uses correct Wappi API endpoint based on channel_type
        async for raw_message in provider.fetch_messages(
            dialog_id=conversation_id,
            cursor=None,  # Start from beginning
            since=None,  # No date filter - get all messages
        ):
            # Transform message (includes media processing and S3 upload!)
            # - Extracts provider_message_id from Wappi message ID
            # - Processes voice/image/video/document media
            # - Uploads media to S3 via backend_client.upload_artifact()
            # - Returns SyncMessage with artifact_ids
            sync_msg = await provider.transform_message(raw_message)
            batch.append(sync_msg)
            total_messages += 1

            # Send batch when full
            if len(batch) >= 50:
                await sync_client.send_batch(
                    connector_id=connector_id,
                    correlation_id=correlation_id,
                    messages=batch,
                )
                batch.clear()

                # Rate limiting to avoid overwhelming Wappi API or backend
                await asyncio.sleep(0.5)

        # Send remaining messages
        if batch:
            await sync_client.send_batch(
                connector_id=connector_id,
                correlation_id=correlation_id,
                messages=batch,
            )

        log.info(
            "wappi.conversation_sync.completed",
            connector_id=connector_id,
            conversation_id=conversation_id,
            total_messages=total_messages,
            correlation_id=correlation_id,
            channel_type=connector.channel_type,
        )

        # Mark thread history as synced
        # Thread might be created asynchronously when first message arrives via sales-agent
        thread_id_to_mark: str | None = None
        if thread_info is not None:
            thread_id_to_mark, _ = thread_info

        # If thread doesn't exist yet, wait for it to be created (with retry)
        if thread_id_to_mark is None:
            for attempt in range(3):
                await asyncio.sleep(1.0 * (attempt + 1))  # 1s, 2s, 3s delays

                thread_info = await backend_client.get_thread_by_conversation(
                    connector_id=connector_id,
                    conversation_id=conversation_id,
                )

                if thread_info is not None:
                    thread_id_to_mark, _ = thread_info
                    break

        if thread_id_to_mark:
            success = await backend_client.mark_thread_history_synced(thread_id_to_mark)
            if success:
                log.info(
                    "wappi.conversation_sync.history_marked_synced",
                    connector_id=connector_id,
                    conversation_id=conversation_id,
                    thread_id=thread_id_to_mark,
                )
            else:
                log.warning(
                    "wappi.conversation_sync.failed_to_mark_synced",
                    connector_id=connector_id,
                    conversation_id=conversation_id,
                    thread_id=thread_id_to_mark,
                )
        else:
            log.warning(
                "wappi.conversation_sync.thread_not_found",
                connector_id=connector_id,
                conversation_id=conversation_id,
            )

    except Exception as exc:
        log.exception(
            "wappi.conversation_sync.failed",
            connector_id=connector_id,
            conversation_id=conversation_id,
            correlation_id=correlation_id,
            channel_type=connector.channel_type,
            error=str(exc),
        )


async def _sync_more_chats_background(
    connector_id: str,
    connector: WappiConnectorConfig,
    wappi_client: WappiApiClient,
    backend_client: WappiBackendClient,
    settings: Settings,
) -> None:
    """Background task to sync more chats for a connector.

    Continues loading chats that weren't included in initial sync (limited by initial_sync_dialogs_limit).
    For each new chat, parses initial_sync_messages_limit messages.

    Args:
        connector_id: Connector identifier
        connector: Connector configuration
        wappi_client: Wappi API client
        backend_client: Backend client
        settings: Application settings
    """
    correlation_id = f"more-chats-{connector_id}-{int(asyncio.get_event_loop().time())}"

    log.info(
        "wappi.sync_more_chats.started",
        connector_id=connector_id,
        correlation_id=correlation_id,
        channel_type=connector.channel_type,
    )

    try:
        # Create provider
        provider = WappiSyncProvider(
            connector_config=connector,
            wappi_client=wappi_client,
            backend_client=backend_client,
        )

        # Create sync client for sending batches to backend
        sync_client = BackendSyncClient(
            base_url=settings.backend.url,
            service_key=settings.service.api_key.get_secret_value(),
        )

        total_new_chats = 0
        total_messages = 0
        max_messages_per_dialog = provider.get_initial_sync_limit()

        # Fetch dialogs from Wappi API
        # Note: This will continue from where initial sync stopped (via cursor pagination)
        async for dialog in provider.fetch_dialogs(cursor=None, max_dialogs=None):
            conversation_id = dialog.id

            # Check if thread already exists for this conversation
            thread_info = await backend_client.get_thread_by_conversation(
                connector_id=connector_id,
                conversation_id=conversation_id,
            )

            if thread_info is not None:
                # Thread already exists, skip this dialog
                log.debug(
                    "wappi.sync_more_chats.dialog_exists",
                    connector_id=connector_id,
                    conversation_id=conversation_id,
                )
                continue

            # Thread doesn't exist - this is a new chat, sync it
            log.debug(
                "wappi.sync_more_chats.new_dialog",
                connector_id=connector_id,
                conversation_id=conversation_id,
            )

            batch: list[SyncMessage] = []
            dialog_messages = 0

            # Fetch messages for this dialog (limited by initial_sync_messages_limit)
            async for raw_message in provider.fetch_messages(
                dialog_id=conversation_id,
                cursor=None,
                since=None,
                max_messages=max_messages_per_dialog,
            ):
                # Transform message (includes media processing and S3 upload)
                sync_msg = await provider.transform_message(raw_message)
                batch.append(sync_msg)
                dialog_messages += 1

                # Send batch when full
                if len(batch) >= 50:
                    await sync_client.send_batch(
                        connector_id=connector_id,
                        correlation_id=correlation_id,
                        messages=batch,
                    )
                    batch.clear()

                    # Rate limiting
                    await asyncio.sleep(0.5)

            # Send remaining messages for this dialog
            if batch:
                await sync_client.send_batch(
                    connector_id=connector_id,
                    correlation_id=correlation_id,
                    messages=batch,
                )

            total_new_chats += 1
            total_messages += dialog_messages

            log.debug(
                "wappi.sync_more_chats.dialog_synced",
                connector_id=connector_id,
                conversation_id=conversation_id,
                messages=dialog_messages,
            )

        log.info(
            "wappi.sync_more_chats.completed",
            connector_id=connector_id,
            correlation_id=correlation_id,
            new_chats=total_new_chats,
            total_messages=total_messages,
            channel_type=connector.channel_type,
        )

    except Exception as exc:
        log.exception(
            "wappi.sync_more_chats.failed",
            connector_id=connector_id,
            correlation_id=correlation_id,
            channel_type=connector.channel_type,
            error=str(exc),
        )
