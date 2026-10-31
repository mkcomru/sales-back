from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, Field

from src.backend.modules.billing.models import BillingStatus
from src.backend.modules.stages.schemas import StageInfo

if TYPE_CHECKING:
    from src.backend.modules.orders.models import Order


class LastMessagePreview(BaseModel):
    content: str
    created_at: datetime


def chat_message_preview_text(*, content: str | None, transcription: str | None) -> str:
    t = (transcription or "").strip()
    if t:
        return t
    return (content or "").strip()


class ChatMessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"
    MANAGER = "manager"
    SYSTEM = "system"


class ChatMessageStatus(str, Enum):
    PENDING = "pending"
    SENT = "sent"
    DELIVERED = "delivered"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ChatMessageType(str, Enum):
    TEXT = "text"
    INTERNAL_NOTE = "internal_note"
    SYSTEM_EVENT = "system_event"


class ThreadState(str, Enum):
    ACTIVE = "active"
    WAITING_MANAGER = "waiting_manager"
    HANDOFF = "handoff"
    CLOSED = "closed"


class AssistantMode(str, Enum):
    ACTIVE = "active"
    SHADOWING = "shadowing"
    INACTIVE = "inactive"


class ThreadControlAction(str, Enum):
    STOP_ASSISTANT = "stop_assistant"
    RESUME_ASSISTANT = "resume_assistant"
    HANDOFF_TO_OPERATOR = "handoff_to_operator"
    RETURN_TO_ASSISTANT = "return_to_assistant"


class ThreadFilter(str, Enum):
    """Filter options for thread listing."""

    ALL = "all"
    MINE = "mine"
    AI = "ai"
    HUMAN = "human"


class RealtimeEventType(str, Enum):
    MESSAGE = "message"
    CONTROL = "control"
    NOTE = "note"
    TYPING = "typing"
    ACK = "ack"
    THREAD_UPDATED = "thread_updated"
    THREAD_LIST_UPDATE = "thread_list_update"
    THREAD_CREATED = "thread_created"


class ChatParticipant(BaseModel):
    participant_id: str = Field(min_length=1, description="Unique participant identifier")
    display_name: str = Field(min_length=1, description="Friendly name for UI rendering")
    role: ChatMessageRole = Field(description="Role of the participant inside the thread")
    avatar_url: str | None = Field(default=None, description="Optional avatar reference")


class ChatMessageBase(BaseModel):
    role: ChatMessageRole = Field(description="Author role of the message")
    content: str = Field(
        default="",
        description=(
            "Plain text body (typed messages, captions). Not used for STT output — "
            "see `transcription` on responses for voice/audio transcripts."
        ),
    )
    metadata: dict[str, Any] = Field(default_factory=dict, description="Transport-specific metadata")
    attachments: list[dict[str, Any]] = Field(default_factory=list, description="Attachment descriptors")
    reply_to: str | None = Field(default=None, description="Message id being referenced")


class AuthorInfo(BaseModel):
    """Full author information for message responses."""

    id: int = Field(description="CompanyUser ID")
    user_id: int = Field(description="User ID")
    first_name: str = Field(description="First name")
    last_name: str = Field(description="Last name")
    email: str = Field(description="User email")
    role: str = Field(description="Role in the company")


class ChatMessageResponse(ChatMessageBase):
    """API shape for a persisted thread message, including delivery fields and STT."""

    message_id: str = Field(min_length=1, description="Unique message id")
    thread_id: str = Field(min_length=1, description="Thread identifier that owns the message")
    type: ChatMessageType = Field(default=ChatMessageType.TEXT, description="Message type (text or internal note)")
    status: ChatMessageStatus = Field(description="Delivery status inside backend domain")
    author: AuthorInfo | None = Field(default=None, description="Full author information")
    transcription: str | None = Field(
        default=None,
        description=(
            "Speech-to-text for voice/audio attachments (canonical STT field). "
            "Clients should prefer this for transcript display; `content` may still hold legacy "
            "pre-migration transcripts for old rows. Not sent as outbound text to transports."
        ),
    )
    artifact_ids: list[str] = Field(default_factory=list, description="List of S3 artifact IDs")
    created_at: datetime = Field(description="Creation timestamp (UTC)")
    updated_at: datetime | None = Field(default=None, description="Last update timestamp (UTC)")
    delivered_at: datetime | None = Field(default=None, description="Delivery timestamp (UTC)")

    @classmethod
    def from_model(cls, message: Any, thread_id: str | None = None) -> "ChatMessageResponse":
        """Convert ChatMessage model to ChatMessageResponse schema.

        Args:
            message: ChatMessage instance with author__user relation prefetched
            thread_id: Optional thread_id (if not provided, will use message.thread.thread_id)

        Returns:
            ChatMessageResponse instance including `transcription` when set on the model

        Raises:
            AttributeError: If thread_id not provided and message.thread not loaded
        """
        from src.backend.modules.chat.utils import get_author_info

        resolved_thread_id: str
        if thread_id is None:
            try:
                resolved_thread_id = message.thread.thread_id
            except AttributeError:
                raise AttributeError(
                    f"Message {message.message_id} thread relation not loaded. "
                    "Either pass thread_id parameter or call fetch_related('thread') first"
                ) from None
        else:
            resolved_thread_id = thread_id

        return cls(
            message_id=message.message_id,
            thread_id=resolved_thread_id,
            role=ChatMessageRole(message.role.value),
            content=message.content,
            transcription=message.transcription,
            type=ChatMessageType(message.type.value),
            metadata=message.metadata,
            attachments=message.attachments,
            reply_to=message.reply_to,
            status=ChatMessageStatus(message.status.value),
            author=get_author_info(message),
            artifact_ids=message.artifact_ids or [],
            created_at=message.created_at,
            updated_at=message.updated_at,
            delivered_at=message.delivered_at,
        )


class ChatMessageCreateRequest(ChatMessageBase):
    """Payload used by managers/front to inject manual messages."""

    is_note: bool = Field(
        default=False,
        description="If true, message is internal note (not sent to client)",
    )
    pause_assistant: bool = Field(
        default=True,
        description=("If true, pause AI assistant when manager sends a message"),
    )


class InternalMessageEnvelope(ChatMessageBase):
    message_id: str | None = Field(
        default=None,
        description="Optional upstream message id, backend will generate if absent",
    )
    status: ChatMessageStatus = Field(
        default=ChatMessageStatus.PENDING,
        description="Status reported by Sales Agent",
    )
    created_at: datetime | None = Field(default=None, description="Original creation time inside Sales Agent")
    delivered_at: datetime | None = Field(default=None, description="Delivery timestamp (UTC)")


class AssigneeInfo(BaseModel):
    """Compact assignee information for thread responses."""

    id: int = Field(description="CompanyUser ID")
    user_id: int = Field(description="User ID")
    first_name: str = Field(description="First name")
    last_name: str = Field(description="Last name")
    role: str = Field(description="Role in the company")


class OrderSummary(BaseModel):
    """Minimal order info for thread summary."""

    id: int = Field(description="Order ID")
    order_number: int = Field(description="Order number")
    stage: StageInfo | None = Field(None, description="Order stage")
    assignee: AssigneeInfo | None = Field(default=None, description="Order assignee")

    @classmethod
    def from_model(cls, order: "Order") -> "OrderSummary":
        """Convert Order model to OrderSummary schema."""
        assignee_info = None
        if order.assignee:
            assignee_info = AssigneeInfo(
                id=order.assignee.id,
                user_id=order.assignee.user.id,
                first_name=order.assignee.user.first_name,
                last_name=order.assignee.user.last_name,
                role=order.assignee.role.value,
            )
        return cls(
            id=order.id,
            order_number=order.order_number,
            stage=StageInfo.from_model(order.stage),
            assignee=assignee_info,
        )


class ThreadCustomerDetails(BaseModel):
    """Customer details for thread list (chat sidebar display)."""

    email: str = Field(default="-", description="Customer email from meta")
    phone: str = Field(default="-", description="Customer phone from meta")
    location: str = Field(default="-", description="Customer location from meta")
    username: str = Field(default="", description="Customer username from meta")
    customer_fields: dict[str, str | int | bool | None] = Field(
        default_factory=dict, description="Qualification/custom fields"
    )


class ChatThreadSummary(BaseModel):
    thread_id: str = Field(min_length=1, description="Thread identifier")
    company_id: int = Field(ge=1, description="Owning company")
    channel_type: str = Field(min_length=1, description="Channel identifier (telegram, wappi, ...)")
    connector_transport_type: str | None = Field(
        default=None,
        description="Connector.type when thread has connector_id (telegram, wappi, wazzup, custom); null otherwise",
    )
    conversation_id: str | None = Field(default=None, description="External conversation reference (CRM, messenger)")
    customer_id: int = Field(ge=1, description="Customer database ID")
    state: ThreadState = Field(description="Current lifecycle state")
    customer_name: str | None = Field(default=None, description="Readable customer name if present")
    last_message_preview: str = Field(description="Short preview for lists")
    last_message_at: datetime = Field(description="Timestamp of the latest message")
    unread_count: int = Field(default=0, ge=0, description="Unread messages for manager")
    assistant_mode: AssistantMode = Field(default=AssistantMode.ACTIVE, description="AI assistant mode")
    billing_status: BillingStatus = Field(default=BillingStatus.ACTIVE, description="Billing status of the thread")
    active_order: OrderSummary | None = Field(default=None, description="Active order for this thread")
    details: ThreadCustomerDetails = Field(
        default_factory=ThreadCustomerDetails,
        description="Customer details for chat sidebar (email, phone, customer_fields)",
    )


class ChatThreadResponse(ChatThreadSummary):
    participants: list[ChatParticipant] = Field(
        default_factory=list, description="Participants involved in this thread"
    )
    messages: list[ChatMessageResponse] = Field(default_factory=list, description="Ordered message history")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Arbitrary backend metadata (CRM ids, pipeline info)",
    )

    def to_summary(self) -> ChatThreadSummary:
        return ChatThreadSummary(
            thread_id=self.thread_id,
            company_id=self.company_id,
            channel_type=self.channel_type,
            connector_transport_type=self.connector_transport_type,
            conversation_id=self.conversation_id,
            customer_id=self.customer_id,
            state=self.state,
            customer_name=self.customer_name,
            last_message_preview=self.last_message_preview,
            last_message_at=self.last_message_at,
            unread_count=self.unread_count,
            assistant_mode=self.assistant_mode,
            billing_status=self.billing_status,
            active_order=self.active_order,
            details=self.details,
        )


class ThreadControlResponse(BaseModel):
    thread_id: str = Field(min_length=1)
    action: ThreadControlAction
    state: ThreadState
    assistant_mode: AssistantMode = Field(description="AI assistant mode after the control action")
    issued_by: str = Field(description="Identifier of user/system that triggered the control command")
    effective_at: datetime = Field(description="UTC timestamp when action became effective")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Supplementary details")


class InternalMessageIngestRequest(BaseModel):
    source: str = Field(min_length=1, description="Origin of the payload (sales_agent, etc.)")
    trace_id: str | None = Field(default=None, description="Trace for cross-service correlation")
    messages: list[InternalMessageEnvelope] = Field(default_factory=list, description="Batch of messages to ingest")


class InternalMessageIngestResponse(BaseModel):
    thread_id: str
    accepted: int = Field(ge=0, description="Amount of messages accepted for processing")
    state: ThreadState
    trace_id: str


class ChatMessagePatchRequest(BaseModel):
    status: ChatMessageStatus = Field(description="Updated status reported by Sales Agent")
    delivered_at: datetime | None = Field(default=None, description="Optional delivery confirmation timestamp")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional status context")


class ThreadStateUpdateRequest(BaseModel):
    state: ThreadState
    reason: str = Field(min_length=1, description="Why state changed (handoff, manual stop, etc.)")
    metadata: dict[str, Any] = Field(default_factory=dict)


class CustomerUpdateRequest(BaseModel):
    """Request to update customer basic fields."""

    name: str | None = Field(default=None, min_length=1, description="Customer name")
    phone: str | None = Field(default=None, min_length=1, description="Customer phone")


class CustomerQuizAnswersUpdateRequest(BaseModel):
    """Request to update customer quiz answers."""

    answers: dict[str, Any] = Field(description="Quiz answers to update (merge with existing)")


class CustomerQuizAnswersUpdateResponse(BaseModel):
    """Response after quiz answers update."""

    customer_id: int = Field(ge=1, description="Customer ID")
    updated_answers: dict[str, Any] = Field(description="Updated quiz answers fields")
    updated_at: datetime = Field(description="Update timestamp")


class CustomerUpdateResponse(BaseModel):
    """Response after customer update."""

    customer_id: int = Field(ge=1, description="Customer ID")
    user_id: str = Field(min_length=1, description="External user identifier")
    name: str | None = Field(default=None, description="Customer name")
    phone: str | None = Field(default=None, description="Customer phone from meta")
    updated_at: datetime = Field(description="Update timestamp")


class ThreadCustomFieldsUpdateRequest(BaseModel):
    """Request to update thread custom fields (quiz answers, etc)."""

    fields: dict[str, Any] = Field(description="Custom fields to update (e.g., intent, goal, preferences)")


class ThreadCustomFieldsUpdateResponse(BaseModel):
    """Response after thread custom fields update."""

    thread_id: str = Field(min_length=1, description="Thread identifier")
    updated_fields: dict[str, Any] = Field(description="Fields that were updated with new values")
    updated_at: datetime = Field(description="Update timestamp")


class ThreadAssigneeUpdateRequest(BaseModel):
    """Request to update thread assignee."""

    assignee_id: int | None = Field(description="CompanyUser ID of the new assignee, null to unassign")


class ThreadAssigneeUpdateResponse(BaseModel):
    """Response after thread assignee update."""

    thread_id: str = Field(min_length=1, description="Thread identifier")
    previous_assignee_id: int | None = Field(default=None, description="Previous assignee ID")
    assignee: AssigneeInfo | None = Field(default=None, description="New assignee info, null if unassigned")
    updated_at: datetime = Field(description="Update timestamp")


class ThreadStateUpdateResponse(BaseModel):
    thread_id: str
    previous_state: ThreadState
    state: ThreadState
    updated_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class RealtimeEvent(BaseModel):
    event_id: str = Field(min_length=1)
    event_type: RealtimeEventType
    thread_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    emitted_at: datetime = Field(description="UTC timestamp emitted by backend")


class WebSocketContractEventSchema(BaseModel):
    event_type: RealtimeEventType
    direction: str = Field(description="outbound|inbound relative to the browser")
    description: str
    payload_fields: dict[str, str] = Field(default_factory=dict, description="Key-value description of payload fields")
    example: dict[str, Any] = Field(default_factory=dict)


class WebSocketContractResponse(BaseModel):
    thread_id: str
    endpoint: str = Field(description="Absolute WS endpoint url template")
    auth_header: str = Field(description="Header that must be forwarded during handshake (e.g. Bearer token)")
    reconnect_strategy: str = Field(description="Recommendation for client retry behaviour upon disconnect")
    outbound_events: list[WebSocketContractEventSchema] = Field(
        default_factory=list, description="Events sent by backend to the browser"
    )
    inbound_events: list[WebSocketContractEventSchema] = Field(
        default_factory=list, description="Events browser can send to backend"
    )


class CustomerGetOrCreateRequest(BaseModel):
    user_id: str = Field(min_length=1)
    company_id: int = Field(ge=1)
    meta: dict[str, Any] = Field(default_factory=dict)


class CustomerGetOrCreateResponse(BaseModel):
    customer_id: int
    user_id: str
    company_id: int
    created: bool


class CustomerProfileResponse(BaseModel):
    customer_fields: dict[str, Any] = Field(default_factory=dict)
    rejected: bool
    rejection_reason: str | None
    name: str | None = None


class CustomerFieldSchema(BaseModel):
    """Field schema for customer fields."""

    id: int = Field(description="Field ID")
    name: str = Field(description="Field name (key in customer_fields)")
    question: str = Field(description="Field question text")
    type: str = Field(description="Field type: string, number, boolean, enum")
    required: bool = Field(default=False, description="Is field required")
    display_name: str | None = Field(default=None, description="Display name for UI")
    category_id: int | None = Field(default=None, description="Category ID if category-specific")
    product_id: int | None = Field(default=None, description="Product ID if product-specific")
    options: list[dict[str, Any]] = Field(default_factory=list, description="Options for enum fields")


class CustomerDetailResponse(BaseModel):
    """Full customer information for UI display."""

    customer_id: int = Field(ge=1, description="Customer database ID")
    user_id: str = Field(min_length=1, description="External user identifier")
    name: str | None = Field(default=None, description="Customer name")
    username: str | None = Field(default=None, description="Username from metadata (e.g., Telegram @username)")
    phone: str | None = Field(default=None, description="Customer phone number")
    email: str | None = Field(default=None, description="Customer email")
    avatar_url: str | None = Field(default=None, description="Customer avatar URL")
    customer_fields: dict[str, Any] = Field(default_factory=dict, description="Customer profile fields")
    fields_schema: list[CustomerFieldSchema] = Field(
        default_factory=list, description="Schema of all fields for typed UI rendering"
    )
    rejected: bool = Field(default=False, description="Is customer rejected")
    rejection_reason: str | None = Field(default=None, description="Reason for rejection if applicable")
    notes: str | None = Field(default=None, description="Manager notes about the customer")
    meta: dict[str, Any] = Field(default_factory=dict, description="Additional metadata (channel-specific)")
    created_at: datetime = Field(description="Customer creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class RejectedField(BaseModel):
    key: str
    value: Any
    reason: str
    allowed: list[str] | None = None


class UpdateFieldsUnifiedRequest(BaseModel):
    company_id: int = Field(ge=1)
    order_id: int | None = Field(default=None)
    updates: dict[str, Any] = Field(default_factory=dict)


class UpdateFieldsUnifiedResponse(BaseModel):
    updated_customer: list[str] = Field(default_factory=list)
    updated_order: list[str] = Field(default_factory=list)
    updated_extra: list[str] = Field(default_factory=list)
    rejected: list[RejectedField] = Field(default_factory=list)


class CustomerRejectRequest(BaseModel):
    company_id: int = Field(ge=1)
    reason: str = Field(default="")


class CustomerNotesUpdateRequest(BaseModel):
    """Request to update customer notes."""

    notes: str | None = Field(description="Manager notes about the customer (null to clear)")


class CustomerNotesUpdateResponse(BaseModel):
    """Response after customer notes update."""

    customer_id: int = Field(ge=1, description="Customer database ID")
    user_id: str = Field(min_length=1, description="External user identifier")
    notes: str | None = Field(default=None, description="Updated notes")
    updated_at: datetime = Field(description="Update timestamp")


class LangfuseSessionRequest(BaseModel):
    company_id: int = Field(ge=1)
    conversation_id: str = Field(min_length=1)


class LangfuseSessionResponse(BaseModel):
    session_id: str | None


class ThreadHistoryRequest(BaseModel):
    limit: int | None = Field(default=None, ge=1)


class ThreadGetOrCreateRequest(BaseModel):
    user_id: str = Field(min_length=1)
    company_id: int = Field(ge=1)
    channel_type: str = Field(min_length=1)
    connector_id: str | None = Field(default=None)
    conversation_id: str | None = None
    thread_id: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)


class ThreadGetOrCreateResponse(BaseModel):
    thread_id: str
    user_id: str
    company_id: int
    channel_type: str
    connector_id: str
    conversation_id: str | None
    stage: str | None
    assistant_mode: str
    history_synced: bool
    created: bool


class ThreadByConversationResponse(BaseModel):
    """Response for getting thread by conversation ID."""

    thread_id: str = Field(min_length=1, description="Thread identifier")
    history_synced: bool = Field(description="Whether full conversation history has been synced")


class HandoffNotificationRequest(BaseModel):
    """Request from Sales Agent to notify backend about handoff."""

    summary: str = Field(min_length=1, description="Brief conversation summary for manager")
    reason: str = Field(min_length=1, description="Reason for handoff (e.g., 'complex_question', 'user_request')")


class HandoffNotificationResponse(BaseModel):
    """Response after handoff notification processed."""

    thread_id: str = Field(min_length=1, description="Thread identifier")
    state: ThreadState = Field(description="New thread state")
    assistant_mode: AssistantMode = Field(description="AI assistant mode after handoff")
    message_id: str = Field(min_length=1, description="ID of created system message")
    processed_at: datetime = Field(description="When handoff was processed")


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int
