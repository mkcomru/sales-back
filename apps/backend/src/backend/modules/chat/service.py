"""Service layer for managing customers, threads, and messages."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import structlog

from common.correlation import make_correlation_id

from src.backend.modules.chat.models import (
    AssistantMode,
    ChatMessage,
    ChatMessageRole,
    ChatMessageStatus,
    ChatMessageType,
    Customer,
    Thread,
    ThreadState,
)
from src.backend.modules.chat.repository import (
    ChatMessagesRepository,
    CustomersRepository,
    ThreadsRepository,
)
from src.backend.modules.chat.schemas import (
    AssigneeInfo,
    CustomerFieldSchema,
    CustomerProfileResponse,
    LangfuseSessionResponse,
    LastMessagePreview,
    RejectedField,
    ThreadFilter,
    UpdateFieldsUnifiedResponse,
    chat_message_preview_text,
)
from src.backend.modules.chat.threads_service import ThreadsService
from src.backend.modules.chat.websocket import get_websocket_manager
from src.backend.modules.companies.models import Company
from src.backend.modules.fields.models import AnswerType, Field, FieldLevel
from src.backend.modules.messages.outbound_service import OutboundService
from src.backend.modules.messages.sales_agent_client import SalesAgentClient, SalesAgentClientError
from src.backend.modules.orders.models import Order
from src.backend.modules.orders.service import OrderService
from src.backend.modules.transport.models import Connector
from src.backend.modules.transport.repository import ConnectorsRepository
from src.backend.modules.transport.service import ConnectorsService

log = structlog.get_logger(__name__)


class ChatService:
    """Service for managing customers, threads, and messages."""

    def __init__(
        self,
        order_service: OrderService,
        *,
        threads_service: ThreadsService | None = None,
        sales_agent_client: SalesAgentClient | None = None,
    ):
        self.customers_repo = CustomersRepository()
        self.threads_repo = ThreadsRepository()
        self.messages_repo = ChatMessagesRepository()
        self.order_service = order_service
        self._threads_service = threads_service or ThreadsService()
        self._sales_agent_client = sales_agent_client

    async def get_or_create_customer(
        self, user_id: str, company_id: int, meta: dict[str, Any] | None = None
    ) -> tuple[Customer, bool]:
        """Get existing customer or create new one.

        Args:
            user_id: External user identifier (from CRM, messenger, etc.)
            company_id: Company identifier
            meta: Optional metadata (e.g., username) to store

        Returns:
            Tuple of (customer, created_flag)
        """
        customer, created = await self.customers_repo.get_or_create(
            user_id=user_id, company_id=company_id, meta=meta or {}
        )
        if created:
            log.info(
                "chat.customer_created",
                user_id=user_id,
                company_id=company_id,
                customer_id=customer.id,
            )
        return customer, created

    async def get_customer_profile(self, user_id: str, company_id: int) -> CustomerProfileResponse:
        """Get customer profile data.

        Args:
            user_id: External user identifier
            company_id: Company identifier

        Returns:
            CustomerProfileResponse with customer_fields, rejected, rejection_reason
        """
        customer, _ = await self.get_or_create_customer(user_id, company_id)
        return CustomerProfileResponse(
            customer_fields=customer.customer_fields or {},
            rejected=customer.rejected,
            rejection_reason=customer.rejection_reason,
            name=customer.name,
        )

    async def update_customer_fields(self, user_id: str, company_id: int, updates: dict[str, Any]) -> None:
        """Update customer fields and recalculate stages for all active orders.

        Args:
            user_id: External user identifier
            company_id: Company identifier
            updates: Dictionary of fields to update in customer_fields
        """
        customer, _ = await self.get_or_create_customer(user_id, company_id)
        await self.customers_repo.update_customer_fields(customer, updates)
        log.debug(
            "chat.customer_fields_updated",
            user_id=user_id,
            company_id=company_id,
            fields=list(updates.keys()),
        )

        active_orders = await Order.filter(
            customer_id=customer.id,
            closed_at__isnull=True,
        ).all()

        for order in active_orders:
            if not order.frozen:
                try:
                    await self.order_service.recalculate_stage(order.id)
                except Exception as e:
                    log.warning(
                        "order.stage_recalculation_failed_after_customer_update",
                        order_id=order.id,
                        customer_id=customer.id,
                        error=str(e),
                    )

    async def update_fields_unified(
        self,
        user_id: str,
        company_id: int,
        updates: dict[str, Any],
        order_id: int | None = None,
    ) -> UpdateFieldsUnifiedResponse:
        """Route field updates to customer_fields, order_fields, or extra_fields based on schema."""
        if not updates:
            return UpdateFieldsUnifiedResponse()

        all_fields = await Field.filter(company_id=company_id).prefetch_related("options").all()
        field_defs = {f.name: f for f in all_fields}
        customer_keys = {f.name for f in all_fields if f.level == FieldLevel.CUSTOMER}
        order_keys = {f.name for f in all_fields if f.level == FieldLevel.ORDER}

        validated: dict[str, Any] = {}
        rejected: list[RejectedField] = []

        for key, value in updates.items():
            field_def = field_defs.get(key)
            if field_def and field_def.answer_type == AnswerType.ENUM:
                allowed_values = [opt.value for opt in field_def.options]
                if str(value) not in allowed_values:
                    rejected.append(
                        RejectedField(
                            key=key,
                            value=value,
                            reason=f"Invalid enum value. Allowed: {allowed_values}",
                            allowed=allowed_values,
                        )
                    )
                    continue
            validated[key] = value

        customer_updates: dict[str, Any] = {}
        order_updates: dict[str, Any] = {}
        extra_updates: dict[str, Any] = {}

        for key, value in validated.items():
            if key in customer_keys:
                customer_updates[key] = value
            elif key in order_keys:
                if order_id is None:
                    rejected.append(RejectedField(key=key, value=value, reason="No active order for order-level field"))
                else:
                    order_updates[key] = value
            else:
                if order_id is None:
                    rejected.append(RejectedField(key=key, value=value, reason="No active order for extra field"))
                else:
                    extra_updates[key] = value

        response = UpdateFieldsUnifiedResponse(rejected=rejected)

        if customer_updates:
            customer, _ = await self.get_or_create_customer(user_id, company_id)
            await self.customers_repo.update_customer_fields(customer, customer_updates)
            response.updated_customer = list(customer_updates.keys())

        orders_repo = self.order_service.orders_repo

        if order_id and (order_updates or extra_updates):
            order = await orders_repo.get_by_id(order_id)
            if not order:
                for key, value in {**order_updates, **extra_updates}.items():
                    rejected.append(RejectedField(key=key, value=value, reason=f"Order {order_id} not found"))
                response.rejected = rejected
            else:
                if order_updates:
                    await orders_repo.update_fields(order, order_updates)
                    response.updated_order = list(order_updates.keys())
                if extra_updates:
                    await orders_repo.update_extra_fields(order, extra_updates)
                    response.updated_extra = list(extra_updates.keys())

                if not order.frozen:
                    try:
                        await self.order_service.recalculate_stage(order.id)
                    except Exception as e:
                        log.warning("order.stage_recalculation_failed", order_id=order.id, error=str(e))

        if customer_updates and not order_updates and not extra_updates:
            customer, _ = await self.get_or_create_customer(user_id, company_id)
            active_orders = await Order.filter(customer_id=customer.id, closed_at__isnull=True).all()
            for order in active_orders:
                if not order.frozen:
                    try:
                        await self.order_service.recalculate_stage(order.id)
                    except Exception as e:
                        log.warning(
                            "order.stage_recalculation_failed_after_customer_update",
                            order_id=order.id,
                            error=str(e),
                        )

        log.debug(
            "chat.fields_unified_updated",
            user_id=user_id,
            company_id=company_id,
            customer_keys=response.updated_customer,
            order_keys=response.updated_order,
            extra_keys=response.updated_extra,
            rejected_count=len(response.rejected),
        )

        return response

    async def mark_customer_rejected(self, user_id: str, company_id: int, reason: str = "") -> None:
        """Mark customer as rejected.

        Args:
            user_id: External user identifier
            company_id: Company identifier
            reason: Rejection reason
        """
        customer, _ = await self.get_or_create_customer(user_id, company_id)
        await self.customers_repo.mark_rejected(customer, reason)
        log.info(
            "chat.customer_rejected",
            user_id=user_id,
            company_id=company_id,
            reason=reason,
        )

    async def reset_customer_profile(self, user_id: str, company_id: int) -> None:
        """Reset customer quiz answers and delete messages.

        Args:
            user_id: External user identifier
            company_id: Company identifier
        """
        customer, _ = await self.get_or_create_customer(user_id, company_id)
        await self.customers_repo.reset_profile(customer)

        # AICODE-NOTE: Get threads for customer and batch delete messages
        from src.backend.modules.chat.models import Thread

        customer_threads = await Thread.filter(customer_id=customer.id).all()
        for thread in customer_threads:
            await self.messages_repo.delete_by_thread(thread)

        log.info("chat.customer_profile_reset", user_id=user_id, company_id=company_id)

    async def get_qualification_config(self, thread: Thread) -> tuple[str, str]:
        """Get qualification workflow and examples from prompt_addon or company fallback.

        Args:
            thread: Thread instance with connector_id and company relation

        Returns:
            Tuple of (workflow, examples)
        """
        await thread.fetch_related("company")
        company = thread.company

        if thread.connector_id:
            connector = await Connector.get_or_none(connector_id=thread.connector_id)
            if connector:
                await connector.fetch_related("prompt_addon")
                if connector.prompt_addon:
                    return connector.prompt_addon.qualification_workflow, connector.prompt_addon.qualification_examples

        return company.qualification_workflow, company.qualification_examples

    async def get_or_create_thread(
        self,
        user_id: str,
        company_id: int,
        channel_type: str,
        connector_id: str | None = None,
        conversation_id: str | None = None,
        thread_id: str | None = None,
        meta: dict[str, Any] | None = None,
        is_historical: bool = False,
    ) -> tuple[Thread, bool]:
        """Get existing thread or create new one.

        Args:
            user_id: External user identifier
            company_id: Company identifier
            channel_type: Channel type (telegram, wappi, etc.)
            connector_id: Connector identifier (optional, for new threads)
            conversation_id: External conversation identifier
            thread_id: Optional thread identifier (will be generated if not provided)
            meta: Optional metadata (e.g., username) to store in customer
            is_historical: Whether this is a historical message (from sync)

        Returns:
            Tuple of (thread, created_flag)
        """
        customer, _ = await self.get_or_create_customer(user_id, company_id, meta=meta or {})
        company = await Company.get(id=company_id)

        thread, created = await self.threads_repo.get_or_create(
            customer=customer,
            company=company,
            channel_type=channel_type,
            connector_id=connector_id,
            conversation_id=conversation_id,
            thread_id=thread_id,
        )

        if created:
            if is_historical:
                thread = await self._threads_service.set_assistant_mode(
                    thread=thread,
                    mode=AssistantMode.INACTIVE,
                    reason="Thread created from historical message",
                )
                metadata = dict(thread.metadata or {})
                metadata["has_history"] = True
                metadata["history_synced_at"] = datetime.now(UTC).isoformat()
                thread.metadata = metadata
                await thread.save(update_fields=["metadata"])

                log.info(
                    "chat.thread_created_with_history",
                    thread_id=thread.thread_id,
                    user_id=user_id,
                    company_id=company_id,
                    channel_type=channel_type,
                )
            else:
                log.info(
                    "chat.thread_created",
                    thread_id=thread.thread_id,
                    user_id=user_id,
                    company_id=company_id,
                    channel_type=channel_type,
                )

            # Blank order for management; historical threads keep assistant disabled above
            order = await self.order_service.ensure_active_order(thread)
            log.info(
                "chat.order_created_for_thread",
                thread_id=thread.thread_id,
                order_id=order.id,
                order_number=order.order_number,
                customer_id=customer.id,
            )
        return thread, created

    async def get_thread_by_id(self, thread_id: str) -> Thread | None:
        """Get thread by thread_id.

        Args:
            thread_id: Thread identifier

        Returns:
            Thread instance or None if not found
        """
        return await self.threads_repo.get_by_thread_id(thread_id)

    async def can_process_with_ai(self, thread_id: str, connector_id: str | None = None) -> bool:
        """Check if thread can be processed with AI.

        Args:
            thread_id: Thread identifier
            connector_id: Optional connector identifier to check sync status

        Returns:
            True if assistant_mode allows AI processing and connector sync allows it
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            return False

        if thread.assistant_mode == AssistantMode.INACTIVE:
            return False

        # If connector_id provided, check connector sync status
        if connector_id:
            connectors_repo = ConnectorsRepository()
            connector = await connectors_repo.get_by_connector_id(connector_id)
            if connector:
                # AI paused during sync
                if connector.is_syncing:
                    return False

        return True

    async def list_threads(
        self,
        company_id: int,
        channel_type: str | None = None,
        state: ThreadState | None = None,
        assignee_filter: ThreadFilter | None = None,
        current_user_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Thread], int]:
        """List threads for a company with optional filters.

        Args:
            company_id: Company identifier
            channel_type: Optional channel type filter
            state: Optional state filter
            assignee_filter: Filter type (all/mine/ai/human)
            current_user_id: Current user ID for 'mine' filter
            limit: Maximum results to return
            offset: Offset for pagination

        Returns:
            Tuple of (threads, total_count)
        """
        return await self.threads_repo.list_by_company(
            company_id=company_id,
            channel_type=channel_type,
            state=state,
            assignee_filter=assignee_filter,
            current_user_id=current_user_id,
            limit=limit,
            offset=offset,
        )

    async def update_thread_state(
        self,
        thread_id: str,
        state: ThreadState,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> Thread:
        """Update thread state.

        Args:
            thread_id: Thread identifier
            state: New thread state
            reason: Reason for state change
            metadata: Additional metadata to merge

        Returns:
            Updated thread instance

        Raises:
            ValueError: If thread not found
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        previous_state = thread.state
        thread = await self.threads_repo.update_state(
            thread=thread,
            state=state,
            reason=reason,
            metadata=metadata,
        )

        log.info(
            "chat.thread_state_updated",
            thread_id=thread_id,
            previous_state=previous_state.value,
            new_state=state.value,
            reason=reason,
        )
        return thread

    async def control_thread_mode(self, thread_id: str, mode: AssistantMode, reason: str) -> Thread:
        """Control assistant mode for a thread.

        Args:
            thread_id: Thread identifier
            mode: New assistant mode
            reason: Reason for control change

        Returns:
            Updated thread instance

        Raises:
            ValueError: If thread not found
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        thread = await self._threads_service.set_assistant_mode(thread=thread, mode=mode, reason=reason)

        log.info(
            "chat.thread_mode_controlled",
            thread_id=thread_id,
            mode=mode.value,
            reason=reason,
        )
        return thread

    async def find_outgoing_duplicate(
        self,
        thread_id: str,
        content: str,
        timestamp: datetime,
    ) -> ChatMessage | None:
        """Find an existing outgoing message that matches content within a time window.

        Used by sync to avoid creating a duplicate row when the same message was
        already persisted via the outbound path (assistant) or inbound path (manager).
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            return None
        return await self.messages_repo.find_outgoing_near_duplicate(thread, content, timestamp)

    async def create_message(
        self,
        thread_id: str,
        role: ChatMessageRole,
        content: str,
        message_id: str | None = None,
        status: ChatMessageStatus = ChatMessageStatus.PENDING,
        message_type: ChatMessageType | None = None,
        metadata: dict[str, Any] | None = None,
        attachments: list[dict[str, Any]] | None = None,
        reply_to: str | None = None,
        delivered_at: datetime | None = None,
        author: Any | None = None,
        provider_message_id: str | None = None,
        is_historical: bool = False,
        artifact_ids: list[str] | None = None,
        created_at: datetime | None = None,
    ) -> ChatMessage:
        """Create a new message in a thread.

        Args:
            thread_id: Thread identifier
            role: Message author role
            content: Message content
            message_id: Optional message identifier (will be generated if not provided)
            status: Message status
            message_type: Message type (TEXT or INTERNAL_NOTE)
            metadata: Additional metadata
            attachments: List of attachment descriptors
            reply_to: Message ID being replied to
            author: Optional CompanyUser instance for manager messages
            provider_message_id: Optional provider message ID for idempotency
            is_historical: Whether this is a historical message (from sync)
            artifact_ids: Optional list of S3 artifact IDs for media attachments

        Returns:
            Created message instance (or existing if provider_message_id matches)

        Raises:
            ValueError: If thread not found
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        message = await self.messages_repo.create_message(
            thread=thread,
            role=role,
            content=content,
            message_id=message_id,
            status=status,
            message_type=message_type,
            metadata=metadata,
            attachments=attachments,
            reply_to=reply_to,
            delivered_at=delivered_at,
            author=author,
            provider_message_id=provider_message_id,
            artifact_ids=artifact_ids,
            created_at=created_at,
        )

        # AICODE-NOTE: Update thread's updated_at timestamp
        await self.threads_repo.touch(thread)

        log.debug(
            "chat.message_created",
            thread_id=thread_id,
            message_id=message.message_id,
            role=role.value,
            is_historical=is_historical,
        )
        return message

    async def create_messages_batch(self, thread_id: str, messages: list[dict[str, Any]]) -> list[ChatMessage]:
        """Create multiple messages in a thread.

        Args:
            thread_id: Thread identifier
            messages: List of message dicts with keys: role, content, and optionally
                      message_id, status, metadata, attachments, reply_to

        Returns:
            List of created message instances

        Raises:
            ValueError: If thread not found
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        created_messages = []
        for msg_data in messages:
            message = await self.messages_repo.create_message(
                thread=thread,
                role=msg_data["role"],
                content=msg_data["content"],
                message_id=msg_data.get("message_id"),
                status=msg_data.get("status", ChatMessageStatus.PENDING),
                metadata=msg_data.get("metadata"),
                attachments=msg_data.get("attachments"),
                reply_to=msg_data.get("reply_to"),
                delivered_at=msg_data.get("delivered_at"),
                author=msg_data.get("author"),
                provider_message_id=msg_data.get("provider_message_id"),
            )
            created_messages.append(message)

        # AICODE-NOTE: Update thread's updated_at timestamp
        await self.threads_repo.touch(thread)

        log.debug(
            "chat.messages_batch_created",
            thread_id=thread_id,
            count=len(created_messages),
        )
        return created_messages

    async def deliver_manager_message(
        self,
        thread: Thread,
        message_id: str,
        content: str,
        outbound_service: OutboundService,
        connectors_service: ConnectorsService,
        attachments: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str | None]:
        """Route manager message to transport via OutboundService.

        Returns tuple(success, delivered_at_iso_or_error).
        """
        from datetime import UTC, datetime

        from src.backend.modules.messages.transport_client import TransportClientError
        from src.backend.modules.transport.exceptions import ConnectorNotFoundError

        if not thread.connector_id:
            return False, "connector_id not found in thread"

        try:
            connector = await connectors_service.get_by_connector_id(thread.connector_id)
            if not connector:
                return False, f"Connector '{thread.connector_id}' not found"

            await outbound_service.deliver_to_thread(
                connector=connector,
                thread=thread,
                replies=[content] if content.strip() else [],
                correlation_id=make_correlation_id("mgr", message_id),
                metadata={
                    "message_id": message_id,
                    "thread_id": thread.thread_id,
                    "source": "manager",
                    "company_id": thread.company_id,
                },
                attachments=attachments,
            )

            delivered_at = datetime.now(UTC).isoformat()
            log.info(
                "manager_message.delivered",
                message_id=message_id,
                thread_id=thread.thread_id,
                connector_id=thread.connector_id,
                delivered_at=delivered_at,
            )
            return True, delivered_at

        except ConnectorNotFoundError as exc:
            log.error("manager_message.connector_not_found", connector_id=thread.connector_id, error=str(exc))
            return False, f"Connector not found: {str(exc)}"
        except TransportClientError as exc:
            log.error("manager_message.delivery_failed", message_id=message_id, error=str(exc))
            return False, f"Transport delivery failed: {str(exc)}"
        except Exception as exc:
            log.error("manager_message.error", message_id=message_id, error=str(exc), exc_info=True)
            return False, f"Unexpected error: {str(exc)}"

    async def get_thread_messages(
        self, thread_id: str, limit: int = 50, offset: int = 0
    ) -> tuple[list[ChatMessage], int]:
        """Get messages for a thread.

        Args:
            thread_id: Thread identifier
            limit: Maximum results to return
            offset: Offset for pagination

        Returns:
            Tuple of (messages, total_count)

        Raises:
            ValueError: If thread not found
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        return await self.messages_repo.list_by_thread(
            thread=thread,
            limit=limit,
            offset=offset,
        )

    async def get_last_message(self, thread_id: str) -> ChatMessage | None:
        """Get the most recent message in a thread.

        Args:
            thread_id: Thread identifier

        Returns:
            Last message or None if thread has no messages
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            return None

        return await self.messages_repo.get_last_message(thread)

    async def get_last_messages_batch(self, thread_ids: list[str]) -> dict[str, LastMessagePreview]:
        """Get last message preview (content + timestamp) for multiple threads."""
        raw = await self.messages_repo.get_last_messages_batch(thread_ids)
        return {
            tid: LastMessagePreview(
                content=chat_message_preview_text(
                    content=data.get("content"),
                    transcription=data.get("transcription"),
                ),
                created_at=data["created_at"],
            )
            for tid, data in raw.items()
        }

    async def get_recent_history(
        self,
        thread_id: str,
        limit: int | None = None,
        *,
        exclude_internal_notes: bool = False,
    ) -> list[dict[str, Any]]:
        """Get recent message history for a thread.

        Args:
            thread_id: Thread identifier
            limit: Maximum messages to return (None returns all)
            exclude_internal_notes: When True, omit INTERNAL_NOTE rows before applying limit

        Returns:
            List of message dicts with role, content, transcription, metadata, created_at
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            return []

        return await self.messages_repo.get_recent_history(
            thread=thread,
            limit=limit,
            exclude_internal_notes=exclude_internal_notes,
        )

    async def transcribe_voice_message(self, message_id: str, attachments: list[dict[str, Any]]) -> None:
        if self._sales_agent_client is None:
            log.warning("voice_transcription.sales_agent_client_missing", message_id=message_id)
            return

        artifact_id: str | None = None
        mime: str | None = None
        for att in attachments:
            if att.get("type") in ("audio", "voice") and att.get("artifact_id"):
                artifact_id = str(att["artifact_id"])
                mime_val = att.get("mime")
                mime = str(mime_val) if mime_val is not None else None
                break

        if not artifact_id:
            return

        try:
            text = await self._sales_agent_client.request_transcription(artifact_id, mime)
        except SalesAgentClientError:
            log.exception(
                "voice_transcription.request_failed",
                message_id=message_id,
                artifact_id=artifact_id,
            )
            return

        try:
            message = await self.get_message_by_id(message_id)
        except ValueError:
            log.warning("voice_transcription.message_not_found", message_id=message_id)
            return

        message.transcription = text
        await message.save(update_fields=["transcription", "updated_at"])
        log.info(
            "voice_transcription.saved",
            message_id=message_id,
            artifact_id=artifact_id,
            text_length=len(text),
        )

        await message.fetch_related("thread")
        await get_websocket_manager().notify_thread_updated(
            message.thread.thread_id,
            {
                "update_type": "message_transcription",
                "message_id": message.message_id,
                "transcription": text,
            },
        )

    async def get_message_by_id(self, message_id: str) -> ChatMessage:
        """Get message by message_id.

        Args:
            message_id: Message identifier

        Returns:
            Message instance

        Raises:
            ValueError: If message not found
        """
        message = await self.messages_repo.get_by_message_id(message_id)
        if not message:
            raise ValueError(f"Message {message_id} not found")
        return message

    async def update_message_status(
        self,
        message_id: str,
        status: ChatMessageStatus,
        delivered_at: datetime | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ChatMessage:
        """Update message delivery status.

        Args:
            message_id: Message identifier
            status: New status
            delivered_at: Optional delivery timestamp
            metadata: Additional metadata to merge

        Returns:
            Updated message instance

        Raises:
            ValueError: If message not found
        """
        message = await self.get_message_by_id(message_id)

        message = await self.messages_repo.update_status(
            message=message,
            status=status,
            delivered_at=delivered_at,
            metadata=metadata,
        )

        log.debug(
            "chat.message_status_updated",
            message_id=message_id,
            status=status.value,
        )
        return message

    async def get_langfuse_session_id(
        self, user_id: str, company_id: int, conversation_id: str | None
    ) -> LangfuseSessionResponse:
        """Get LangFuse session_id for given conversation_id.

        Args:
            user_id: External user identifier
            company_id: Company identifier
            conversation_id: Conversation identifier

        Returns:
            LangfuseSessionResponse with session_id if exists, None otherwise
        """
        if not conversation_id:
            return LangfuseSessionResponse(session_id=None)
        customer, _ = await self.get_or_create_customer(user_id, company_id)
        session_id = await self.customers_repo.get_langfuse_session(customer, conversation_id)
        return LangfuseSessionResponse(session_id=session_id)

    async def create_langfuse_session(self, user_id: str, company_id: int, conversation_id: str) -> str:
        """Create or update LangFuse session_id for conversation_id.

        Args:
            user_id: External user identifier
            company_id: Company identifier
            conversation_id: Conversation identifier

        Returns:
            Generated session ID

        Raises:
            ValueError: If conversation_id is not provided
        """
        if not conversation_id:
            raise ValueError("conversation_id is required")

        customer, _ = await self.get_or_create_customer(user_id, company_id)
        session_id = str(uuid4())
        await self.customers_repo.create_langfuse_session(customer, conversation_id, session_id)

        log.debug(
            "chat.langfuse_session_created",
            user_id=user_id,
            company_id=company_id,
            conversation_id=conversation_id,
            session_id=session_id,
        )
        return session_id

    async def get_customer_detail(self, customer_id: int) -> Customer:
        """Get full customer details by ID.

        Args:
            customer_id: Customer ID

        Returns:
            Customer instance with all fields

        Raises:
            ValueError: If customer not found
        """
        customer = await self.customers_repo.get_by_id(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        log.debug("chat.customer_detail_fetched", customer_id=customer_id)
        return customer

    async def update_customer_profile_fields(
        self, customer_id: int, answers: dict[str, Any]
    ) -> tuple[Customer, dict[str, Any]]:
        """Update customer profile fields (merge with existing).

        Args:
            customer_id: Customer ID
            answers: Customer fields to merge

        Returns:
            Tuple of (updated_customer, changed_fields)

        Raises:
            ValueError: If customer not found
        """
        customer = await self.customers_repo.get_by_id(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        customer, changed_fields = await self.customers_repo.update_customer_fields(customer, answers)

        log.info(
            "chat.customer_fields_updated",
            customer_id=customer_id,
            changed_fields=changed_fields,
        )

        if changed_fields:
            active_orders = await Order.filter(
                customer_id=customer.id,
                closed_at__isnull=True,
            ).all()
            for order in active_orders:
                if not order.frozen:
                    try:
                        await self.order_service.recalculate_stage(order.id)
                    except Exception as e:
                        log.warning(
                            "order.stage_recalculation_failed_after_customer_update",
                            order_id=order.id,
                            customer_id=customer.id,
                            error=str(e),
                        )

        return customer, changed_fields

    async def update_customer_basic_fields(
        self, customer_id: int, name: str | None = None, phone: str | None = None
    ) -> Customer:
        """Update customer basic fields (name, phone).

        Args:
            customer_id: Customer ID
            name: New customer name (optional)
            phone: New customer phone (optional)

        Returns:
            Updated customer instance

        Raises:
            ValueError: If customer not found
        """
        customer = await self.customers_repo.get_by_id(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        old_name = customer.name
        old_phone = (customer.meta or {}).get("phone")

        customer = await self.customers_repo.update_basic_fields(customer, name=name, phone=phone)

        log.info(
            "chat.customer_updated",
            customer_id=customer_id,
            changes={
                "name": {"old": old_name, "new": customer.name},
                "phone": {"old": old_phone, "new": (customer.meta or {}).get("phone")},
            },
        )

        return customer

    async def get_customer_fields_schema(self, company_id: int) -> list[CustomerFieldSchema]:
        """Get fields schema for customer quiz answers.

        Args:
            company_id: Company identifier

        Returns:
            List of field schemas with types and options for UI rendering
        """
        fields = await Field.filter(company_id=company_id).prefetch_related("options", "category", "product").all()
        fields_schema = [
            CustomerFieldSchema(
                id=field.id,
                name=field.name,
                question=field.question,
                type=field.answer_type.value,
                required=field.required,
                display_name=field.display_name,
                category_id=field.category.id if field.category else None,
                product_id=field.product.id if field.product else None,
                options=[{"id": opt.id, "value": opt.value, "order": opt.order} for opt in field.options],
            )
            for field in fields
        ]

        log.debug("chat.customer_fields_schema_loaded", company_id=company_id, fields_count=len(fields_schema))
        return fields_schema

    async def update_customer_notes(self, customer_id: int, notes: str | None) -> Customer:
        """Update customer notes.

        Args:
            customer_id: Customer database ID
            notes: New notes text (null to clear)

        Returns:
            Updated customer instance

        Raises:
            ValueError: If customer not found
        """
        customer = await self.customers_repo.get_by_id(customer_id)
        if not customer:
            raise ValueError(f"Customer {customer_id} not found")

        customer = await self.customers_repo.update_notes(customer, notes)

        log.info(
            "chat.customer_notes_updated",
            customer_id=customer_id,
            user_id=customer.user_id,
            notes_length=len(notes) if notes else 0,
        )

        return customer

    async def update_thread_custom_fields(
        self, thread_id: str, fields: dict[str, Any], log_to_chat: bool = True, updated_by: str | None = None
    ) -> tuple[Thread, dict[str, Any], ChatMessage | None]:
        """Update thread custom fields with optional chat logging.

        Args:
            thread_id: Thread identifier
            fields: Dictionary of field_name -> new_value
            log_to_chat: If True, log significant changes (intent, goal)
                to chat as system message
            updated_by: Name of the user who made the change

        Returns:
            Tuple of (updated_thread, changed_fields_dict, system_message | None)

        Raises:
            ValueError: If thread not found
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        thread, changed_fields = await self.threads_repo.update_custom_fields(thread, fields)

        log.info(
            "chat.thread_custom_fields_updated",
            thread_id=thread_id,
            changed_fields=changed_fields,
        )

        system_message: ChatMessage | None = None
        if log_to_chat and changed_fields:
            changes_text = "\n".join([f"• {key}: {cf['new']}" for key, cf in changed_fields.items()])
            system_message_content = f"Обновлены поля диалога\n\nИзменения:\n{changes_text}"
            if updated_by:
                system_message_content += f"\n\nКто: {updated_by}"

            system_message = await self.create_message(
                thread_id=thread_id,
                role=ChatMessageRole.SYSTEM,
                content=system_message_content,
                status=ChatMessageStatus.SENT,
                message_type=ChatMessageType.SYSTEM_EVENT,
                metadata={
                    "event_type": "custom_fields_update",
                    "changed_fields": {key: cf["new"] for key, cf in changed_fields.items()},
                    "updated_by": updated_by,
                },
            )

        return thread, changed_fields, system_message

    async def build_assignee_info_from_order(self, thread: Thread) -> AssigneeInfo | None:
        """Build AssigneeInfo from thread's active order assignee if present."""
        if not thread.active_order_id:
            return None

        try:
            await thread.fetch_related("active_order__assignee__user")
            order = thread.active_order
            if not order or not order.assignee:
                return None
            assignee = order.assignee
            user = assignee.user
            return AssigneeInfo(
                id=assignee.id,
                user_id=user.id,
                first_name=user.first_name,
                last_name=user.last_name,
                role=assignee.role.value,
            )
        except Exception:
            return None

    async def active_order_assignee_ws_payload(self, thread: Thread) -> dict[str, Any] | None:
        info = await self.build_assignee_info_from_order(thread)
        if info is None:
            return None
        return info.model_dump(mode="json")

    async def handle_handoff(
        self,
        thread_id: str,
        summary: str,
        reason: str,
        *,
        escalate: bool = False,
        cancel_debounce_on_deactivate: bool = True,
    ) -> tuple[Thread, ChatMessage]:
        """Handle AI agent handoff to manager.

        Args:
            thread_id: Thread identifier
            summary: Brief conversation summary
            reason: Reason for handoff
            escalate: If True (hard handoff), set mode to INACTIVE immediately.
                      If False (soft handoff), set mode to SHADOWING — AI continues until manager writes.
            cancel_debounce_on_deactivate: Whether to cancel debounce bucket when assistant is deactivated

        Returns:
            Tuple of (updated_thread, system_message)

        Raises:
            ValueError: If thread not found
        """
        thread = await self.threads_repo.get_by_thread_id(thread_id)
        if not thread:
            raise ValueError(f"Thread {thread_id} not found")

        target_mode = AssistantMode.INACTIVE if escalate else AssistantMode.SHADOWING

        thread = await self.threads_repo.update_state(
            thread=thread,
            state=ThreadState.HANDOFF,
            reason=f"AI handoff: {reason}",
        )
        thread = await self._threads_service.set_assistant_mode(
            thread=thread,
            mode=target_mode,
            reason="Handoff to manager",
            cancel_debounce_on_deactivate=cancel_debounce_on_deactivate,
        )

        handoff_message = f"Диалог передан менеджеру\n\nПричина: {reason}\n\nСодержание разговора: {summary}"

        system_message = await self.create_message(
            thread_id=thread_id,
            role=ChatMessageRole.SYSTEM,
            content=handoff_message,
            status=ChatMessageStatus.SENT,
            message_type=ChatMessageType.TEXT,
            metadata={
                "event_type": "handoff",
                "summary": summary,
                "reason": reason,
                "escalate": escalate,
                "source": "ai_agent",
            },
        )

        log.info(
            "chat.handoff_processed",
            thread_id=thread_id,
            reason=reason,
            escalate=escalate,
            assistant_mode=target_mode.value,
            message_id=system_message.message_id,
        )

        return thread, system_message
