from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from tortoise import Tortoise
from tortoise.exceptions import DoesNotExist
from tortoise.expressions import Q

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
from src.backend.modules.chat.schemas import ThreadFilter
from src.backend.modules.companies.models import Company
from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.core.settings import get_settings
from src.backend.modules.fields.models import Field, FieldLevel


class CustomersRepository(BaseRepository[Customer]):
    def __init__(self):
        super().__init__(Customer)

    async def _ensure_all_fields_present(self, customer: Customer) -> bool:
        """Ensure customer has all customer-level fields in customer_fields.

        Args:
            customer: Customer instance to check and update

        Returns:
            True if any fields were added, False otherwise
        """
        fields = await Field.filter(company_id=customer.company_id, level=FieldLevel.CUSTOMER).all()
        customer_fields = customer.customer_fields or {}
        updated = False

        for field in fields:
            if field.name not in customer_fields:
                customer_fields[field.name] = None
                updated = True

        if updated:
            customer.customer_fields = customer_fields

        return updated

    async def backfill_fields_for_company(self, company_id: int) -> tuple[int, int]:
        """Backfill customer_fields for all customers of a company.

        Args:
            company_id: Company identifier

        Returns:
            Tuple of (total_customers, updated_customers)
        """
        # AICODE-NOTE: Get fields once for the entire company
        fields = await Field.filter(company_id=company_id).all()
        field_names = {field.name for field in fields}

        # AICODE-NOTE: Get all customers
        customers = await Customer.filter(company_id=company_id).all()

        customers_to_update = []

        for customer in customers:
            customer_fields = customer.customer_fields or {}
            updated = False

            for field_name in field_names:
                if field_name not in customer_fields:
                    customer_fields[field_name] = None
                    updated = True

            if updated:
                customer.customer_fields = customer_fields
                customers_to_update.append(customer)

        # AICODE-NOTE: Bulk update - one request instead of N
        if customers_to_update:
            await Customer.bulk_update(customers_to_update, fields=["customer_fields"])

        return len(customers), len(customers_to_update)

    async def get_or_create(
        self, user_id: str, company_id: int, meta: dict[str, Any] | None = None
    ) -> tuple[Customer, bool]:
        """Get existing customer or create new one with initialized customer_fields."""
        try:
            customer = await Customer.get(user_id=user_id, company_id=company_id)
            created = False
            updated = await self._ensure_all_fields_present(customer)
            if updated:
                await customer.save()

        except DoesNotExist:
            company = await Company.get(id=company_id)

            # AICODE-NOTE: Initialize customer_fields with all customer-level fields
            fields = await Field.filter(company_id=company_id, level=FieldLevel.CUSTOMER).all()
            customer_fields = {field.name: None for field in fields}

            name_from_meta = None
            if meta:
                name_from_meta = meta.get("name")
                if isinstance(name_from_meta, str):
                    name_from_meta = name_from_meta.strip() or None

            customer = await Customer.create(
                user_id=user_id,
                company=company,
                name=name_from_meta,
                customer_fields=customer_fields,
                langfuse_sessions={},
                meta=meta or {},
            )
            created = True

        # AICODE-NOTE: Update meta and name if customer exists and new data provided
        if not created and meta:
            needs_save = False

            existing_meta = customer.meta or {}
            existing_meta.update(meta)
            customer.meta = existing_meta
            needs_save = True

            name_from_meta = meta.get("name")
            if isinstance(name_from_meta, str) and name_from_meta.strip():
                if not customer.name or customer.name != name_from_meta:
                    customer.name = name_from_meta
                    needs_save = True

            if needs_save:
                await customer.save()
        return customer, created

    async def get_by_user_id(self, user_id: str, company_id: int) -> Customer | None:
        """Get customer by user_id and company_id."""
        try:
            return await Customer.get(user_id=user_id, company_id=company_id)
        except DoesNotExist:
            return None

    async def update_notes(self, customer: Customer, notes: str | None) -> Customer:
        """Update customer notes.

        Args:
            customer: Customer instance to update
            notes: New notes text (null to clear)

        Returns:
            Updated customer instance
        """
        customer.notes = notes
        await customer.save(update_fields=["notes", "updated_at"])
        return customer

    async def mark_rejected(self, customer: Customer, reason: str = "") -> Customer:
        """Mark customer as rejected."""
        customer.rejected = True
        if reason:
            customer.rejection_reason = reason
        await customer.save()
        return customer

    async def reset_profile(self, customer: Customer) -> Customer:
        """Reset customer profile."""
        customer.customer_fields = {}
        customer.rejected = False
        customer.rejection_reason = None
        await customer.save()
        return customer

    async def get_langfuse_session(self, customer: Customer, conversation_id: str) -> str | None:
        """Get Langfuse session ID for conversation."""
        sessions = customer.langfuse_sessions or {}
        return sessions.get(conversation_id)

    async def create_langfuse_session(self, customer: Customer, conversation_id: str, session_id: str) -> Customer:
        """Create or update Langfuse session ID."""
        sessions = customer.langfuse_sessions or {}
        sessions[conversation_id] = session_id
        customer.langfuse_sessions = sessions
        await customer.save()
        return customer

    async def update_basic_fields(
        self, customer: Customer, name: str | None = None, phone: str | None = None
    ) -> Customer:
        """Update customer name and phone."""
        if name is not None:
            customer.name = name
        if phone is not None:
            meta = customer.meta or {}
            meta["phone"] = phone
            customer.meta = meta
        await customer.save()
        return customer

    async def get_by_id(self, customer_id: int) -> Customer | None:
        """Get customer by ID."""
        try:
            return await Customer.get(id=customer_id)
        except DoesNotExist:
            return None

    async def update_customer_fields(
        self, customer: Customer, answers: dict[str, Any]
    ) -> tuple[Customer, dict[str, Any]]:
        """Update customer fields (merge with existing).

        Returns:
            Tuple of (updated_customer, changed_fields)
        """
        customer_fields = customer.customer_fields or {}
        changed_fields = {}

        for key, value in answers.items():
            old_value = customer_fields.get(key)
            if old_value != value:
                changed_fields[key] = {"old": old_value, "new": value}
                if value is None:
                    customer_fields.pop(key, None)
                else:
                    customer_fields[key] = value

        customer.customer_fields = customer_fields
        await customer.save()
        return customer, changed_fields


class ThreadsRepository(BaseRepository[Thread]):
    def __init__(self):
        super().__init__(Thread)

    async def get_by_thread_id(self, thread_id: str) -> Thread | None:
        """Get thread by thread_id with related data."""
        thread = await Thread.filter(thread_id=thread_id).first()
        if thread:
            await thread.fetch_related("customer", "company")
        return thread

    async def get_or_create(
        self,
        customer: Customer,
        company: Company,
        channel_type: str,
        connector_id: str | None = None,
        conversation_id: str | None = None,
        thread_id: str | None = None,
    ) -> tuple[Thread, bool]:
        """Get existing thread or create new one."""
        # AICODE-NOTE: If thread_id is provided, try to fetch existing thread
        if thread_id:
            thread = await self.get_by_thread_id(thread_id)
            if thread:
                return thread, False

        # AICODE-NOTE: Try to find existing thread by customer+channel+conversation
        if conversation_id:
            try:
                thread = await Thread.get(
                    customer=customer,
                    channel_type=channel_type,
                    conversation_id=conversation_id,
                ).prefetch_related("customer", "company")
                return thread, False
            except DoesNotExist:
                pass

        # AICODE-NOTE: Create new thread
        generated_thread_id = thread_id or f"{channel_type}_{customer.user_id}_{uuid4().hex[:8]}"
        thread = await Thread.create(
            thread_id=generated_thread_id,
            customer=customer,
            company=company,
            channel_type=channel_type,
            connector_id=connector_id,
            conversation_id=conversation_id,
            state=ThreadState.ACTIVE,
            assistant_mode=AssistantMode.ACTIVE,
            metadata={},
        )
        # AICODE-NOTE: Load relations for API response
        await thread.fetch_related("customer", "company")
        return thread, True

    async def list_by_company(
        self,
        company_id: int,
        channel_type: str | None = None,
        state: ThreadState | None = None,
        assignee_filter: ThreadFilter | None = None,
        current_user_id: int | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Thread], int]:
        """List threads for a company with filters.

        Args:
            company_id: Filter by company
            channel_type: Optional channel filter
            state: Optional state filter
            assignee_filter: Filter type (all/mine/ai/human)
            current_user_id: Current user ID for 'mine' filter
            limit: Max results
            offset: Pagination offset

        Returns:
            Tuple of (threads, total_count)
        """
        query = Thread.filter(company_id=company_id)

        if channel_type:
            query = query.filter(channel_type=channel_type)
        if state:
            query = query.filter(state=state)

        if assignee_filter == ThreadFilter.MINE and current_user_id:
            query = query.filter(active_order__assignee_id=current_user_id)
        elif assignee_filter == ThreadFilter.AI:
            query = query.filter(assistant_mode__in=[AssistantMode.ACTIVE, AssistantMode.SHADOWING])
        elif assignee_filter == ThreadFilter.HUMAN:
            query = query.filter(Q(assistant_mode=AssistantMode.INACTIVE) | Q(active_order__assignee_id__isnull=False))
        # ThreadFilter.ALL or None - no additional filter

        total = await query.count()
        threads = (
            await query.prefetch_related("customer", "active_order")
            .order_by("-updated_at")
            .limit(limit)
            .offset(offset)
            .all()
        )

        return threads, total

    async def update_state(
        self,
        thread: Thread,
        state: ThreadState,
        reason: str,
        metadata: dict | None = None,
    ) -> Thread:
        """Update thread state."""
        previous_state = thread.state
        thread.state = state

        if metadata:
            thread.metadata.update(metadata)

        thread.metadata["last_state_change"] = {
            "from": previous_state.value,
            "to": state.value,
            "reason": reason,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }

        await thread.save()
        return thread

    async def set_assistant_mode(self, thread: Thread, mode: AssistantMode, reason: str) -> Thread:
        """Set assistant mode for thread."""
        thread.assistant_mode = mode
        thread.metadata["last_assistant_control"] = {
            "mode": mode.value,
            "reason": reason,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        }
        await thread.save()
        return thread

    async def touch(self, thread: Thread) -> Thread:
        """Update thread's updated_at timestamp."""
        thread.updated_at = datetime.now(tz=UTC)
        await thread.save()
        return thread

    async def update_custom_fields(self, thread: Thread, fields: dict[str, Any]) -> tuple[Thread, dict[str, Any]]:
        """Update thread custom fields (stored in metadata).

        Returns:
            Tuple of (updated_thread, changed_fields_dict)
        """
        metadata = thread.metadata or {}
        custom_fields = metadata.get("custom_fields", {})

        changed_fields = {}
        for key, value in fields.items():
            old_value = custom_fields.get(key)
            if old_value != value:
                changed_fields[key] = {"old": old_value, "new": value}
                custom_fields[key] = value

        metadata["custom_fields"] = custom_fields
        thread.metadata = metadata
        await thread.save()
        return thread, changed_fields


class ChatMessagesRepository(BaseRepository[ChatMessage]):
    def __init__(self):
        super().__init__(ChatMessage)

    async def get_by_message_id(self, message_id: str) -> ChatMessage | None:
        """Get message by message_id."""
        try:
            return await ChatMessage.get(message_id=message_id).prefetch_related("thread", "author__user")
        except DoesNotExist:
            return None

    async def get_last_message(self, thread: Thread) -> ChatMessage | None:
        """Get the most recent message in a thread."""
        return await ChatMessage.filter(thread=thread).order_by("-created_at").first()

    async def get_last_messages_batch(self, thread_ids: list[str]) -> dict[str, dict[str, Any]]:
        """Get last message data for multiple threads in a single query.

        Uses ROW_NUMBER() window function (SQLite 3.25+, PostgreSQL) to fetch
        exactly one (most recent) message per thread. Single round-trip.

        Returns:
            Mapping of thread_id -> {"content", "transcription", "created_at"}
        """
        if not thread_ids:
            return {}

        db_url = get_settings().resolved_database_url
        is_postgres = "postgres" in db_url

        if is_postgres:
            cm_t, t_t = '"backend"."chat_messages"', '"backend"."threads"'
            sql = f"""
                SELECT content, transcription, created_at, thread_tid FROM (
                    SELECT cm.content, cm.transcription, cm.created_at, t.thread_id AS thread_tid,
                           ROW_NUMBER() OVER (PARTITION BY t.thread_id ORDER BY cm.created_at DESC) AS rn
                    FROM {cm_t} cm
                    INNER JOIN {t_t} t ON t.id = cm.thread_id
                    WHERE t.thread_id = ANY($1::text[])
                ) sub WHERE rn = 1
            """
            params = [thread_ids]
        else:
            cm_t, t_t = '"chat_messages"', '"threads"'
            placeholders = ",".join("?" for _ in thread_ids)
            sql = f"""
                SELECT content, transcription, created_at, thread_tid FROM (
                    SELECT cm.content, cm.transcription, cm.created_at, t.thread_id AS thread_tid,
                           ROW_NUMBER() OVER (PARTITION BY t.thread_id ORDER BY cm.created_at DESC) AS rn
                    FROM {cm_t} cm
                    INNER JOIN {t_t} t ON t.id = cm.thread_id
                    WHERE t.thread_id IN ({placeholders})
                ) sub WHERE rn = 1
            """
            params = list(thread_ids)

        conn = Tortoise.get_connection("default")
        rows = await conn.execute_query_dict(sql, params)
        return {
            r["thread_tid"]: {
                "content": r["content"],
                "transcription": r.get("transcription"),
                "created_at": r["created_at"],
            }
            for r in rows
        }

    async def get_by_provider_message_id(self, thread: Thread, provider_message_id: str) -> ChatMessage | None:
        """Get message by provider_message_id within a thread (for idempotency)."""
        try:
            return await ChatMessage.get(thread=thread, provider_message_id=provider_message_id)
        except DoesNotExist:
            return None

    async def find_outgoing_near_duplicate(
        self,
        thread: Thread,
        content: str,
        timestamp: datetime,
        window_seconds: int = 120,
    ) -> ChatMessage | None:
        """Find an existing outgoing message with matching content within a time window.

        Used to prevent duplicates when assistant messages (saved via outbound without
        provider_message_id) are re-encountered during history sync.
        """
        if not content:
            return None
        window = timedelta(seconds=window_seconds)
        return (
            await ChatMessage.filter(
                thread=thread,
                content=content,
                created_at__gte=timestamp - window,
                created_at__lte=timestamp + window,
            )
            .exclude(role=ChatMessageRole.USER)
            .first()
        )

    async def create_message(
        self,
        thread: Thread,
        role: ChatMessageRole,
        content: str,
        message_id: str | None = None,
        status: ChatMessageStatus = ChatMessageStatus.PENDING,
        message_type: ChatMessageType | None = None,
        metadata: dict | None = None,
        attachments: list | None = None,
        reply_to: str | None = None,
        delivered_at: datetime | None = None,
        author: Any | None = None,
        provider_message_id: str | None = None,
        artifact_ids: list | None = None,
        created_at: datetime | None = None,
    ) -> ChatMessage:
        """Create a new message in a thread.

        Args:
            provider_message_id: Optional provider message ID for idempotency.
                                If provided and message already exists, returns existing message.
            artifact_ids: Optional list of S3 artifact IDs for media attachments.
            created_at: Optional creation timestamp override (used for historical sync messages).
        """
        # AICODE-NOTE: Check for existing message by provider_message_id for idempotency
        if provider_message_id:
            existing = await self.get_by_provider_message_id(thread, provider_message_id)
            if existing:
                return existing

        generated_message_id = message_id or f"msg_{uuid4().hex[:16]}"

        create_kwargs: dict = dict(
            message_id=generated_message_id,
            thread=thread,
            role=role,
            content=content,
            status=status,
            type=message_type or ChatMessageType.TEXT,
            metadata=metadata or {},
            attachments=attachments or [],
            reply_to=reply_to,
            delivered_at=delivered_at,
            author=author,
            provider_message_id=provider_message_id,
            artifact_ids=artifact_ids or [],
        )
        if created_at is not None:
            create_kwargs["created_at"] = created_at

        message = await ChatMessage.create(**create_kwargs)

        await (
            Thread.filter(id=thread.id)
            .filter(Q(updated_at__lt=message.created_at) | Q(updated_at__isnull=True))
            .update(updated_at=message.created_at)
        )

        return message

    async def list_by_thread(self, thread: Thread, limit: int = 50, offset: int = 0) -> tuple[list[ChatMessage], int]:
        """Get messages for a thread with pagination.

        Returns the most recent messages first (offset=0 = newest page).
        Results are in chronological order (oldest first) for display.
        """
        query = ChatMessage.filter(thread=thread)

        total = await query.count()
        rows = await (
            query.prefetch_related("author__user").order_by("-created_at", "-id").limit(limit).offset(offset).all()
        )
        messages = list(reversed(rows))

        return messages, total

    async def get_recent_history(
        self,
        thread: Thread,
        limit: int | None = None,
        *,
        exclude_internal_notes: bool = False,
    ) -> list[dict]:
        """Get recent message history for a thread."""
        query = ChatMessage.filter(thread=thread)
        if exclude_internal_notes:
            query = query.exclude(type=ChatMessageType.INTERNAL_NOTE)
        query = query.order_by("-created_at", "-id")

        if limit is not None:
            query = query.limit(limit)

        messages = await query.values("role", "content", "transcription", "metadata", "created_at")
        return list(reversed(messages))

    async def update_status(
        self,
        message: ChatMessage,
        status: ChatMessageStatus,
        delivered_at: datetime | None = None,
        metadata: dict | None = None,
    ) -> ChatMessage:
        """Update message delivery status."""
        message.status = status

        if delivered_at:
            message.delivered_at = delivered_at

        if metadata:
            message.metadata.update(metadata)

        message.updated_at = datetime.now(tz=UTC)
        await message.save()
        return message

    async def delete_by_thread(self, thread: Thread) -> int:
        """Delete all messages in a thread."""
        return await ChatMessage.filter(thread=thread).delete()
