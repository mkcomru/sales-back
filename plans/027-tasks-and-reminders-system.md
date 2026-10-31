# 027 — Tasks & Reminders System

> Implementation plan for unified Tasks & Reminders system around orders.

---

## Зачем это делаем

Сегодня менеджеры и AI-агенты не могут надежно планировать, отслеживать и выполнять follow-ups в едином структурированном месте: напоминания разбросаны по промптам, чатам, заметкам и легко теряются.

После внедрения Tasks & Reminders:
- **Follow-ups становятся явными** — каждое "напомни позвонить в пятницу" превращается в Task с конкретной датой и ответственным.
- **AI и люди работают в одном цикле** — менеджер и агент видят единый список задач по заказу и могут их выполнять.
- **Мы перестаем терять сделки** — автоматические напоминания обеспечивают систематический, а не случайный follow-up.

---

## Scope

**In scope (backend only):**
- Task data model with polymorphic subject
- REST API endpoints for CRUD operations
- Scheduler worker for executing due tasks
- Sales Agent integration (internal endpoint + AI tool)
- `docker-compose.yml` modification to include scheduler worker

**Out of scope:**
- Frontend implementation (separate plan)
- Manager/company-scoped task endpoints (future)
- Notification system for human tasks (future)

---

## Phase 1: Data Model & Repository

### 1.1 Create Task Model

**File:** `apps/backend/src/backend/modules/tasks/models.py`

```python
"""
Task model with polymorphic subject binding.

Design principles:
- Data structure is unified and flexible (subject_type + subject_id pattern)
- External interfaces are strict and descriptive (typed helpers, explicit accessors)
- Fail-fast validation: required fields must be present and valid at creation
"""

class TaskSubjectType(str, Enum):
    ORDER = "order"
    # Reserved for future phases:
    # MANAGER = "manager"
    # COMPANY = "company"
    # CUSTOMER = "customer"

class TaskType(str, Enum):
    MANUAL = "manual"              # Human-created, human-executed
    AI_SCHEDULED = "ai_scheduled"  # Created for AI to execute later
    # REMINDER = "reminder"        # Placeholder for future

class TaskAutoAction(str, Enum):
    """Defined in libs/common for cross-service usage. Import from common.models."""
    SEND_FOLLOWUP_MESSAGE = "send_followup_message"
    # FORWARD_TO_CONNECTOR = "forward_to_connector"  # Reserved: no implementation yet

class CompletedByType(str, Enum):
    USER = "user"      # Completed by human (assignee or admin)
    SYSTEM = "system"  # Completed by scheduler after AI execution

class Task(Model):
    """
    Unified task entity with polymorphic subject binding.
    
    Subject binding uses subject_type + subject_id internally, but external
    APIs expose typed helpers (create_order_task) and accessors (get_order_id).
    Higher-level services are responsible for resolving IDs to model instances.
    
    Lifecycle: Tasks are deleted when their subject is deleted (CASCADE).
    For order tasks: if order is deleted, its tasks are deleted too.
    """
    id: int (PK)
    company_id: int (FK -> Company, ON DELETE CASCADE)
    
    # Polymorphic subject (internal representation)
    # Note: No FK constraint on subject_id — validated at service level
    # Tasks are deleted via application logic when subject is deleted
    subject_type: TaskSubjectType
    subject_id: int
    
    # Core fields
    title: str (required, max 255)
    description: str | None
    type: TaskType
    due_date: datetime (UTC)
    
    # Assignee (optional - if None and AI_SCHEDULED, system executes)
    assignee_id: int | None (FK -> CompanyUser)
    
    # Auto-action (required for AI_SCHEDULED)
    auto_action: TaskAutoAction | None
    
    # Lifecycle
    completed: bool = False
    completed_at: datetime | None
    completed_by_type: CompletedByType | None  # Who completed: user or system (if user, assume assignee)
    cancelled_at: datetime | None
    
    # Execution tracking (for AI_SCHEDULED tasks)
    attempt_count: int = 0
    last_attempt_at: datetime | None
    failure_reason: str | None  # Last failure reason, cleared on success
    
    # Audit
    created_at: datetime
    created_by_id: int | None (FK -> CompanyUser)
    updated_at: datetime
    
    # Typed accessor — returns ID, service layer resolves to model
    def get_order_id(self) -> int:
        """Returns order_id. Raises ValueError if subject_type != ORDER."""
        if self.subject_type != TaskSubjectType.ORDER:
            raise ValueError(f"Task {self.id} subject is {self.subject_type}, not ORDER")
        return self.subject_id
    
    @property
    def is_overdue(self) -> bool:
        return not self.completed and self.cancelled_at is None and datetime.utcnow() > self.due_date
```

**Validation rules:**
- `subject_id > 0` always
- If `type == AI_SCHEDULED`, `auto_action` must be set
- If `type == MANUAL`, `auto_action` must be None
- `due_date` must be in future on creation (configurable tolerance)

### 1.2 Migration

After Aerich generates the migration file, manually add the `"backend"` schema prefix to all table and index references. Example pattern to follow:

```sql
-- Aerich generates: CREATE TABLE "tasks" (...)
-- Change to: CREATE TABLE "backend"."tasks" (...)

-- Same for indexes:
-- Aerich generates: CREATE INDEX "idx_tasks_subject" ON "tasks" (...)
-- Change to: CREATE INDEX "idx_tasks_subject" ON "backend"."tasks" (...)
```

**Indexes to add:**

```sql
-- Subject-based listing (for "show tasks for order X")
CREATE INDEX "idx_tasks_subject" ON "backend"."tasks" 
    ("company_id", "subject_type", "subject_id");

-- Scheduler query: pending tasks due before timestamp
CREATE INDEX "idx_tasks_due_pending" ON "backend"."tasks" ("due_date")
    WHERE "completed" = FALSE AND "cancelled_at" IS NULL;

-- "My tasks" for assignee
CREATE INDEX "idx_tasks_assignee" ON "backend"."tasks" 
    ("company_id", "assignee_id") 
    WHERE "assignee_id" IS NOT NULL;
```

### 1.3 Create Repository

**File:** `apps/backend/src/backend/modules/tasks/repository.py`

```python
"""
Task repository with typed creation helpers.

Design: Internal storage uses subject_type + subject_id, but the repository
exposes typed methods (create_order_task) that hide this wiring from callers.
"""

class TaskRepository:
    async def get_by_id(self, task_id: int) -> Task:
        """Get task by ID. Raises DoesNotExist if not found."""
        return await Task.get(id=task_id)
    
    async def create_order_task(
        self,
        company_id: int,
        order_id: int,
        title: str,
        due_date: datetime,
        type: TaskType,
        *,
        description: str | None = None,
        assignee_id: int | None = None,
        auto_action: TaskAutoAction | None = None,
        created_by_id: int | None = None,
    ) -> Task:
        """Create a task bound to an order. Maps order_id to subject internally."""
        return await Task.create(
            company_id=company_id,
            subject_type=TaskSubjectType.ORDER,
            subject_id=order_id,
            title=title,
            due_date=due_date,
            type=type,
            description=description,
            assignee_id=assignee_id,
            auto_action=auto_action,
            created_by_id=created_by_id,
        )
    
    async def get_tasks_for_order(
        self,
        company_id: int,
        order_id: int,
        *,
        include_completed: bool = False,
    ) -> list[Task]:
        query = Task.filter(
            company_id=company_id,
            subject_type=TaskSubjectType.ORDER,
            subject_id=order_id,
        )
        if not include_completed:
            query = query.filter(completed=False, cancelled_at__isnull=True)
        return await query.order_by("due_date")
    
    async def get_due_tasks(
        self,
        before: datetime,
        *,
        limit: int = 100,
    ) -> list[Task]:
        """Get pending tasks due before given timestamp. Used by scheduler."""
        return await Task.filter(
            completed=False,
            cancelled_at__isnull=True,
            due_date__lte=before,
        ).limit(limit)
    
    async def get_tasks_for_assignee(
        self,
        company_id: int,
        assignee_id: int,
        *,
        include_completed: bool = False,
    ) -> list[Task]:
        query = Task.filter(company_id=company_id, assignee_id=assignee_id)
        if not include_completed:
            query = query.filter(completed=False, cancelled_at__isnull=True)
        return await query.order_by("due_date")
    
    async def complete_task(
        self,
        task_id: int,
        completed_by_type: CompletedByType,
    ) -> Task:
        task = await Task.get(id=task_id)
        task.completed = True
        task.completed_at = datetime.utcnow()
        task.completed_by_type = completed_by_type
        task.failure_reason = None  # Clear on success
        await task.save()
        return task
    
    async def cancel_task(self, task_id: int) -> Task:
        task = await Task.get(id=task_id)
        task.cancelled_at = datetime.utcnow()
        await task.save()
        return task
    
    async def update_task(self, task_id: int, **updates) -> Task:
        task = await Task.get(id=task_id)
        for key, value in updates.items():
            setattr(task, key, value)
        task.updated_at = datetime.utcnow()
        await task.save()
        return task
    
    async def record_attempt(self, task_id: int) -> Task:
        """Increment attempt count and update last_attempt_at."""
        task = await Task.get(id=task_id)
        task.attempt_count += 1
        task.last_attempt_at = datetime.utcnow()
        await task.save()
        return task
    
    async def record_failure(self, task_id: int, failure_reason: str) -> Task:
        """Record failure reason (called after record_attempt on failure)."""
        task = await Task.get(id=task_id)
        task.failure_reason = failure_reason
        await task.save()
        return task
```

---

## Phase 2: Service Layer & Validation

### 2.1 Create Task Service

**File:** `apps/backend/src/backend/modules/tasks/service.py`

```python
"""
Task service orchestrating validation, business logic, and cross-module interactions.

Design principles:
- Service methods accept explicit IDs and resolve to model instances when needed
- Validation is fail-fast: invalid input raises immediately
- Order events are logged for traceability
"""

class TaskService:
    def __init__(self, repo: TaskRepository, order_service: OrderService):
        self.repo = repo
        self.order_service = order_service
    
    async def create_order_task(
        self,
        company_id: int,
        order_id: int,
        data: CreateOrderTaskRequest,
        created_by_id: int | None = None,
    ) -> Task:
        # Resolve order_id to Order instance for validation
        order = await self.order_service.get_order(company_id, order_id)
        if not order:
            raise OrderNotFoundError(order_id)
        
        # Validate type/auto_action consistency
        if data.type == TaskType.AI_SCHEDULED and not data.auto_action:
            raise ValidationError("AI_SCHEDULED tasks require auto_action")
        if data.type == TaskType.MANUAL and data.auto_action:
            raise ValidationError("MANUAL tasks cannot have auto_action")
        
        # Validate due_date is in future
        if data.due_date <= datetime.utcnow():
            raise ValidationError("due_date must be in the future")
        
        # Create task
        task = await self.repo.create_order_task(
            company_id=company_id,
            order_id=order_id,
            **data.model_dump(),
            created_by_id=created_by_id,
        )
        
        # Log to order history
        await self.order_service.log_event(
            order_id=order_id,
            event_type="task_created",
            data={"task_id": task.id, "title": task.title},
        )
        
        return task
    
    async def complete_task(
        self,
        company_id: int,
        task_id: int,
    ) -> Task:
        """Complete task by user. For system completion, use repository directly."""
        task = await self.repo.get_by_id(task_id)
        
        if task.company_id != company_id:
            raise TaskNotFoundError(task_id)
        
        # Idempotent
        if task.completed:
            return task
        
        task = await self.repo.complete_task(task_id, completed_by_type=CompletedByType.USER)
        
        # Log to order if subject is order
        if task.subject_type == TaskSubjectType.ORDER:
            await self.order_service.log_event(
                order_id=task.get_order_id(),
                event_type="task_completed",
                data={"task_id": task.id, "completed_by_type": "user"},
            )
        
        return task
    
    async def get_order_with_tasks(
        self,
        company_id: int,
        order_id: int,
    ) -> tuple[Order, list[Task]]:
        """Higher-level method returning resolved Order + its tasks."""
        order = await self.order_service.get_order(company_id, order_id)
        if not order:
            raise OrderNotFoundError(order_id)
        tasks = await self.repo.get_tasks_for_order(company_id, order_id)
        return order, tasks
```

### 2.2 Schemas

**File:** `apps/backend/src/backend/modules/tasks/schemas.py`

```python
class CreateOrderTaskRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=255)
    description: str | None = None
    type: TaskType
    due_date: datetime
    assignee_id: int | None = None
    auto_action: TaskAutoAction | None = None
    
    @model_validator(mode="after")
    def validate_type_action_consistency(self) -> Self:
        if self.type == TaskType.AI_SCHEDULED and not self.auto_action:
            raise ValueError("AI_SCHEDULED tasks require auto_action")
        if self.type == TaskType.MANUAL and self.auto_action:
            raise ValueError("MANUAL tasks cannot have auto_action")
        return self

class UpdateTaskRequest(BaseModel):
    title: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = None
    due_date: datetime | None = None
    assignee_id: int | None = None

class TaskResponse(BaseModel):
    id: int
    company_id: int
    order_id: int  # Derived from subject for order tasks
    title: str
    description: str | None
    type: TaskType
    due_date: datetime
    assignee_id: int | None
    auto_action: TaskAutoAction | None
    completed: bool
    completed_at: datetime | None
    completed_by_type: CompletedByType | None  # If USER, assume assignee completed
    is_overdue: bool  # Computed
    created_at: datetime
    created_by_id: int | None
    # Execution tracking
    attempt_count: int
    last_attempt_at: datetime | None
    failure_reason: str | None

# Use PaginatedResponse[TaskResponse] from common.models.pagination
# Do not create custom TaskListResponse
```

---

## Phase 3: REST API Endpoints

### 3.1 Order-Scoped Endpoints

**File:** `apps/backend/src/backend/modules/tasks/routes.py`

```python
router = APIRouter(prefix="/companies/{company_id}/orders/{order_id}/tasks", tags=["tasks"])

@router.get("", response_model=PaginatedResponse[TaskResponse])
async def list_order_tasks(
    company_id: int,
    order_id: int,
    include_completed: bool = False,
    pagination: PaginationParams = Depends(),
    service: TaskService = Depends(),
    user: CompanyUser = Depends(get_current_company_user),
) -> PaginatedResponse[TaskResponse]: ...

@router.post("", response_model=TaskResponse, status_code=201)
async def create_order_task(
    company_id: int,
    order_id: int,
    data: CreateOrderTaskRequest,
    service: TaskService = Depends(),
    user: CompanyUser = Depends(get_current_company_user),
) -> TaskResponse: ...

@router.patch("/{task_id}", response_model=TaskResponse)
async def update_task(
    company_id: int,
    order_id: int,
    task_id: int,
    data: UpdateTaskRequest,
    service: TaskService = Depends(),
    user: CompanyUser = Depends(get_current_company_user),
) -> TaskResponse:
    """Update task fields (title, description, due_date, assignee)."""
    ...

@router.post("/{task_id}/complete", response_model=TaskResponse)
async def complete_task(
    company_id: int,
    order_id: int,
    task_id: int,
    service: TaskService = Depends(),
    user: CompanyUser = Depends(get_current_company_user),
) -> TaskResponse: ...

@router.post("/{task_id}/cancel", response_model=TaskResponse)
async def cancel_task(
    company_id: int,
    order_id: int,
    task_id: int,
    service: TaskService = Depends(),
    user: CompanyUser = Depends(get_current_company_user),
) -> TaskResponse: ...
```

### 3.2 Manager-Scoped Endpoint (My Tasks)

```python
@router.get("/companies/{company_id}/my-tasks", response_model=PaginatedResponse[TaskResponse])
async def list_my_tasks(
    company_id: int,
    include_completed: bool = False,
    pagination: PaginationParams = Depends(),
    service: TaskService = Depends(),
    user: CompanyUser = Depends(get_current_company_user),
) -> PaginatedResponse[TaskResponse]:
    """List tasks assigned to the current user."""
    ...
```

---

## Phase 4: Task Scheduler & Executor

### 4.1 Architectural Decision

**Worker is a backend execution mode, not a separate service.**

See [`apps/backend/src/backend/workers/README.md`](../apps/backend/src/backend/workers/README.md) for architectural constraints.

Key points:
- Worker lives in `backend/workers/`, uses backend's service layer
- External apps (sales-agent, telegram-module, etc.) MUST talk to backend via HTTP API only — no shortcuts
- Worker is thin orchestration: poll → delegate to service → done

Entrypoint: `python -m backend.workers.task_scheduler`

### 4.2 Scheduler Worker

**File:** `apps/backend/src/backend/workers/task_scheduler.py`

```python
"""
Task scheduler worker — polls for due tasks and dispatches execution.

Deployment: Runs as separate container, same codebase as backend.
Guarantee: At-least-once delivery — tasks must be idempotent.
"""

class TaskScheduler:
    def __init__(
        self,
        task_repo: TaskRepository,
        executor: TaskExecutor,
        poll_interval_seconds: int = 10,
    ):
        self.task_repo = task_repo
        self.executor = executor
        self.poll_interval = poll_interval_seconds
    
    async def run(self) -> NoReturn:
        logger.info("Task scheduler started")
        while True:
            try:
                await self._process_due_tasks()
            except Exception:
                logger.exception("Error processing due tasks")
            await asyncio.sleep(self.poll_interval)
    
    async def _process_due_tasks(self) -> None:
        now = datetime.utcnow()
        tasks = await self.task_repo.get_due_tasks(before=now, limit=100)
        
        for task in tasks:
            # Re-fetch to ensure still pending (at-least-once guard)
            fresh_task = await self.task_repo.get_by_id(task.id)
            if fresh_task.completed or fresh_task.cancelled_at:
                continue
            
            if task.type == TaskType.AI_SCHEDULED and task.auto_action:
                await self.executor.execute_ai_task(fresh_task)
            # MANUAL tasks: no auto-execution, surfaced via API only
```

### 4.3 Task Executor

**File:** `apps/backend/src/backend/workers/task_executor.py`

```python
class TaskExecutor:
    """Executes AI-scheduled tasks by calling Sales Agent."""
    
    def __init__(
        self,
        task_repo: TaskRepository,
        sales_agent_client: SalesAgentClient,
        order_service: OrderService,
    ):
        self.task_repo = task_repo
        self.sales_agent_client = sales_agent_client
        self.order_service = order_service
    
    async def execute_ai_task(self, task: Task) -> None:
        logger.info("Executing AI task", task_id=task.id, auto_action=task.auto_action, attempt=task.attempt_count + 1)
        
        # Record attempt
        await self.task_repo.record_attempt(task.id)
        
        try:
            if task.subject_type != TaskSubjectType.ORDER:
                raise ValueError(f"Unsupported subject type: {task.subject_type}")
            
            # Resolve order, thread, and connector
            order = await self.order_service.get_order(
                task.company_id, task.get_order_id()
            )
            thread = await Thread.get(active_order=order)  # FK relation, not active_order_id
            connector = await Connector.get(id=thread.connector_id)
            
            payload = TaskExecutionRequest(
                context=ConnectorContext(
                    connector_id=thread.connector_id,
                    company_id=task.company_id,
                    type=connector.type,  # From Connector, not Thread
                    channel_type=thread.channel_type,
                    debounce=DebounceConfig(),  # Not used for task execution
                ),
                thread_id=thread.thread_id,
                order_id=order.id,
                task_id=task.id,
                auto_action=task.auto_action,
                title=task.title,
                description=task.description,
            )
            
            await self.sales_agent_client.execute_task(payload)
            await self.task_repo.complete_task(task.id, completed_by_type=CompletedByType.SYSTEM)
            
            logger.info("AI task completed", task_id=task.id)
            
        except Exception as e:
            logger.exception("Failed to execute AI task", task_id=task.id)
            await self.task_repo.record_failure(task.id, failure_reason=str(e))
            # Task remains pending for retry on next poll cycle
```

---

## Phase 5: Sales Agent Integration

### 5.1 Shared Base Class for Internal Requests

**File:** `libs/common/src/common/models/outbound.py`

Extract common fields into base class — minimal refactoring, zero consumer changes:

```python
class BaseInternalRequest(BaseModel):
    """Base class for internal Backend → Sales Agent requests."""
    context: ConnectorContext
    thread_id: str = Field(description="Backend-created thread ID")
    order_id: int | None = Field(default=None, description="Active order ID")

class InternalInboundRequest(BaseInternalRequest):
    """Internal request for inbound message processing (existing, unchanged API)."""
    envelope: InboundEnvelope
    order_stage: dict[str, Any] | None = Field(default=None)
    qualification_workflow: str | None = Field(default=None)
    qualification_examples: str | None = Field(default=None)

class TaskExecutionRequest(BaseInternalRequest):
    """Internal request for scheduled task execution."""
    task_id: int
    auto_action: TaskAutoAction
    title: str
    description: str | None = None
```

### 5.2 Task Execution Endpoint

**File:** `apps/sales-agent/src/sales_agent/api/internal.py` (extend existing file)

```python
# Add imports
from common.models import TaskExecutionRequest, TaskAutoAction
from src.sales_agent.agents.prompts.reminder_formatter import format_reminder_prompt
from src.sales_agent.services.message_processor import process_reminder

# Create separate router for tasks (existing router is for /messages)
tasks_router = APIRouter(prefix="/api/v1/internal/tasks", tags=["internal-tasks"])

@tasks_router.post("/execute")
async def execute_task(
    request: TaskExecutionRequest,
) -> dict:
    """Execute a scheduled task action.
    
    Called by backend scheduler. No user auth — internal only.
    """
    match request.auto_action:
        case TaskAutoAction.SEND_FOLLOWUP_MESSAGE:
            instructions = format_reminder_prompt(
                title=request.title,
                description=request.description,
            )
            await process_reminder(
                context=request.context,
                thread_id=request.thread_id,
                order_id=request.order_id,
                reminder_instructions=instructions,
            )
        case _:
            raise HTTPException(400, f"Unknown auto_action: {request.auto_action}")
    
    return {"status": "executed", "task_id": request.task_id}
```

### 5.3 Reminder Processing (message_processor.py)

**File:** `apps/sales-agent/src/sales_agent/services/message_processor.py` (add function)

```python
async def process_reminder(
    context: ConnectorContext,
    thread_id: str,
    order_id: int | None,
    reminder_instructions: str,
) -> None:
    """
    Process scheduled reminder via existing pipeline.
    
    Builds minimal SimpleMessage with metadata, calls pipeline with
    reminder_instructions which get injected into system prompt.
    Response is sent to backend via normal outbound flow.
    """
    # Build SimpleMessage with required metadata
    simple_msg = SimpleMessage(
        text="",  # No user text for reminders
        from_user=SimpleUser(id=0),
        chat=SimpleChat(id=0),
        message_id=0,
        metadata={
            "company_id": context.company_id,
            "connector_id": context.connector_id,
            "connector_type": context.type,
            "channel_type": context.channel_type,
            "thread_id": thread_id,
            "order_id": order_id,
        },
    )
    
    # Get dependencies (same as in create_batch_processor)
    # These are available from app state
    result = await process_user_message_agents(
        simple_msg,
        settings=app.state.settings,
        large_llm_client=app.state.large_llm_client,
        tracer=app.state.tracer,
        backend_client=app.state.backend_client,
        connector_context=connector_context,
        reminder_instructions=reminder_instructions,  # NEW PARAM
    )
    
    # Send response via backend (same as handle_agent_batch)
    if result.text and result.text.strip():
        outbound_request = OutboundDeliveryRequest(
            connector_id=context.connector_id,
            conversation_id=thread_id,
            thread_id=thread_id,
            replies=[result.text],
            metadata={"company_id": context.company_id},
        )
        await app.state.backend_client.send_outbound_message(outbound_request)
```

### 5.4 Reminder Prompt Template

**File:** `apps/sales-agent/src/sales_agent/agents/prompts/reminder.md`

```markdown
## Scheduled Reminder

You have a scheduled task to follow up with this customer.

**Reminder:** {{ title }}
{% if description %}
**Details:** {{ description }}
{% endif %}

{% if order_context %}
**Current Order State:**
- Stage: {{ order_context.stage_name }}
- Fields: {{ order_context.fields | tojson }}
{% endif %}

{% if recent_summary %}
**Recent Conversation:**
{{ recent_summary }}
{% endif %}

---

**Your task:** Follow up with the customer naturally. Reference the conversation history and reminder context to craft a relevant, personalized message. Do not mention that this is an automated reminder.
```

**File:** `apps/sales-agent/src/sales_agent/agents/prompts/reminder_formatter.py`

```python
from pathlib import Path
from typing import Any

from jinja2 import Template

REMINDER_TEMPLATE_PATH = Path(__file__).parent / "reminder.md"

def format_reminder_prompt(
    title: str,
    description: str | None = None,
    order_context: dict[str, Any] | None = None,
    recent_summary: str | None = None,
) -> str:
    """Format reminder prompt with full context.
    
    Easy to extend: add new parameters here and update template.
    """
    template = Template(REMINDER_TEMPLATE_PATH.read_text())
    return template.render(
        title=title,
        description=description,
        order_context=order_context,
        recent_summary=recent_summary,
    )
```

### 5.5 Pipeline Extension

**File:** `apps/sales-agent/src/sales_agent/agents/pipeline.py`

Add `reminder_instructions` parameter:

```python
async def process_user_message_agents(
    message: SimpleMessage,
    settings: Settings,
    large_llm_client: LLMClient,
    tracer: Tracer,
    backend_client: BackendClient,
    connector_context: ConnectorContext | None = None,
    reminder_instructions: str | None = None,  # NEW
) -> AgentsPipelineResult:
```

Modify empty text check (around line 227):

```python
    text = (message.text or "").strip()
    
    # For reminders: no user text, use trigger message
    if not text and reminder_instructions:
        text = "[Выполни напоминание согласно инструкциям в системном промпте]"
    elif not text:
        return AgentsPipelineResult(text="Пожалуйста, отправьте текстовое сообщение.")
```

Modify system prompt construction (where qualifier_prompt is built):

```python
    # Append reminder instructions to system prompt if provided
    if reminder_instructions:
        qualifier_prompt = f"{qualifier_prompt}\n\n---\n\n{reminder_instructions}"
```

That's it — two small changes to existing function, no new abstractions

### 5.3 AI Tool: Schedule Reminder

**File:** `apps/sales-agent/src/sales_agent/agents/tools/tasks.py`

#### Design: Minimal AI Input, Context-Derived Fields

AI tools should require **minimal cognitive load** — AI provides only semantic information, our code fills technical fields from context.

**How it works:**
1. AI generates tool arguments according to schema: `{title, due_date, description}`
2. Tool handler has `order_id` and `company_id` bound via closure (same pattern as `build_qualifier_tools`)
3. We construct the full API payload ourselves, adding fields AI shouldn't think about

This approach reduces cost, latency, and hallucination risk.

**Implementation note:** Follow existing pattern in `core/tools/registry.py` where `order_id` is passed to `build_qualifier_tools()` and injected into handlers via closure.

```python
# Tool schema for OpenAI function calling
SCHEDULE_REMINDER_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "What to remind about, e.g. 'Позвонить клиенту'"},
        "due_date": {"type": "string", "description": "When to send the reminder (ISO 8601 format)"},
        "description": {"type": "string", "description": "Additional details (optional)"},
    },
    "required": ["title", "due_date"],
}

def _create_schedule_reminder_handler(company_id: int, order_id: int) -> Any:
    """Create handler for schedule_reminder tool.
    
    Follows existing pattern from build_qualifier_tools where order_id
    is injected via closure, not passed by AI.
    """
    async def handler(args: dict[str, Any]) -> dict[str, Any]:
        backend_client = get_backend_client()
        
        # WE construct the full payload — AI only provides title, due_date, description
        payload = {
            "title": args["title"],
            "due_date": args["due_date"],
            "description": args.get("description"),
            # Technical fields filled by us, not AI:
            "type": "ai_scheduled",
            "auto_action": "send_followup_message",
        }
        
        result = await backend_client.create_order_task(
            company_id=company_id,
            order_id=order_id,
            data=payload,
        )
        return {"success": True, "task_id": result["id"], "due_date": result["due_date"]}
    
    return handler
```

**Note:** Add `create_order_task` method to `BackendClient` in sales-agent.

#### Task Lifecycle: No AI `complete_task` Tool Needed

The scheduler owns task completion, not AI:

1. Task becomes due → scheduler detects it
2. Scheduler calls Sales Agent internal endpoint with task payload
3. Sales Agent executes action (sends follow-up)
4. Sales Agent returns success
5. **Scheduler marks task complete** (not AI)

AI doesn't need a `complete_task` tool because:
- Scheduled tasks are completed by scheduler after execution
- AI doesn't "pick up" tasks from a list — tasks come TO AI via scheduler
- Failure handling: scheduler logs and retries on next cycle

---

## Phase 6: Testing

### 6.1 Unit Tests

**File:** `apps/backend/tests/modules/tasks/test_service.py`

```python
class TestTaskService:
    async def test_create_order_task_success(self): ...
    async def test_create_task_validates_order_exists(self): ...
    async def test_create_ai_task_requires_auto_action(self): ...
    async def test_create_manual_task_rejects_auto_action(self): ...
    async def test_complete_task_idempotent(self): ...
    async def test_complete_task_logs_to_order(self): ...
```

### 6.2 Integration Tests

**File:** `apps/backend/tests/integration/test_tasks_api.py`

```python
class TestTasksAPI:
    async def test_create_and_list_order_tasks(self): ...
    async def test_complete_task_flow(self): ...
    async def test_my_tasks_endpoint(self): ...
    async def test_task_permissions(self): ...
```

### 6.3 Scheduler Tests

**File:** `apps/backend/tests/workers/test_task_scheduler.py`

```python
class TestTaskScheduler:
    async def test_processes_due_tasks(self): ...
    async def test_skips_completed_tasks(self): ...
    async def test_handles_execution_failure_gracefully(self): ...
    async def test_at_least_once_delivery(self): ...
```

---

## Decisions

1. **thread_id resolution** — Backend looks up `thread_id` from order before calling Sales Agent. Included in `TaskExecutionRequest` payload via `BaseInternalRequest.thread_id`.

2. **CASCADE delete for order tasks** — App-level cascade in `OrderService.delete_order()` — explicit is better.

3. **Pipeline extension** — Existing `process_user_message_agents` extended with single param:
   - `reminder_instructions: str | None` — appended to system prompt when provided

4. **Direct pipeline call** — `process_reminder()` in `message_processor.py` calls pipeline directly, no debouncer involved. Debouncer is for batching rapid user messages; reminders are single deliberate triggers.

5. **Internal API location** — Extend existing `internal.py` file with separate `tasks_router`. Keeps internal endpoints in one file.

---

## Implementation Order

1. **Phase 1** — Data model, migration (Aerich + manual schema fix), repository
2. **Phase 2** — Service layer with validation
3. **Phase 3** — REST API endpoints
4. **Phase 4** — Scheduler worker (can run in parallel with Phase 5)
5. **Phase 5** — Sales Agent integration (`schedule_reminder` tool + internal endpoint)
6. **Phase 6** — Tests throughout each phase

---

## Files to Create/Modify

### Backend (new)
- `apps/backend/src/backend/modules/tasks/__init__.py`
- `apps/backend/src/backend/modules/tasks/models.py`
- `apps/backend/src/backend/modules/tasks/repository.py`
- `apps/backend/src/backend/modules/tasks/service.py`
- `apps/backend/src/backend/modules/tasks/schemas.py`
- `apps/backend/src/backend/modules/tasks/routes.py`
- `apps/backend/src/backend/modules/tasks/exceptions.py`
- `apps/backend/src/backend/workers/__init__.py`
- `apps/backend/src/backend/workers/README.md` ✅ (created)
- `apps/backend/src/backend/workers/task_scheduler.py`
- `apps/backend/src/backend/workers/task_executor.py`

### Libs/Common (modify)
- `libs/common/src/common/models/outbound.py` — add:
  - `TaskAutoAction` enum (shared between backend and sales-agent)
  - `BaseInternalRequest` base class
  - Make `InternalInboundRequest` inherit from `BaseInternalRequest`
  - `TaskExecutionRequest` class
- `libs/common/src/common/models/__init__.py` — export `TaskAutoAction`, `BaseInternalRequest`, `TaskExecutionRequest`

### Backend (modify)
- `apps/backend/src/backend/api/router.py` — register task routes
- `apps/backend/src/backend/modules/orders/models.py` — add `TASK_CREATED` and `TASK_COMPLETED` to `OrderLogType` enum
- `apps/backend/src/backend/modules/orders/service.py` — add:
  - `get_order(company_id, order_id)` method (currently only `get_by_id` in repo)
  - `log_event(order_id, event_type, data)` helper method — consolidates `OrderLog.create()` calls, refactor existing transactional code to use it
  - `delete_order()` — add cascade delete for tasks
- `apps/backend/src/backend/modules/messages/sales_agent_client.py` — add `execute_task()` method:
  ```python
  async def execute_task(self, request: TaskExecutionRequest) -> None:
      """Execute scheduled task via Sales Agent."""
      client = self._get_client()
      response = await client.post(
          "/api/v1/internal/tasks/execute",  # Note: different from /messages
          json=request.model_dump(mode="json"),
      )
      response.raise_for_status()
  ```

### Sales Agent (new)
- `apps/sales-agent/src/sales_agent/agents/prompts/reminder.md` — Jinja2 template for reminder instructions
- `apps/sales-agent/src/sales_agent/agents/prompts/reminder_formatter.py` — `format_reminder_prompt()` util

### Sales Agent (modify)
- `apps/sales-agent/src/sales_agent/api/internal.py` — add `tasks_router` with `/execute` endpoint
- `apps/sales-agent/src/sales_agent/main.py` — register `tasks_router` from `internal.py`
- `apps/sales-agent/src/sales_agent/core/tools/registry.py` — add `schedule_reminder` tool + handler
- `apps/sales-agent/src/sales_agent/services/backend_client.py` — add `create_order_task()` method
- `apps/sales-agent/src/sales_agent/services/message_processor.py` — add `process_reminder()` function
- `apps/sales-agent/src/sales_agent/agents/pipeline.py` — add `reminder_instructions` param (2 small changes)

### Infrastructure (modify)
- `docker-compose.yml` — add task-scheduler service after `backend`:

```yaml
  task-scheduler:
    build:
      context: .
      dockerfile: docker/python-service.Dockerfile
      args:
        PACKAGE_NAME: backend
        APP_PATH: apps/backend
        PYTHONPATH_SUFFIX: ""
        UVICORN_MODULE_PATH: src.backend.main:app  # not used, but required by Dockerfile
    restart: unless-stopped
    depends_on:
      redis:
        condition: service_healthy
      backend-migrations:
        condition: service_completed_successfully
    env_file:
      - .env.shared.dev
      - apps/backend/.env
    environment:
      EVENTING__ENABLED: "false"  # worker doesn't need eventing
    command: ["/app/.venv/bin/python", "-m", "backend.workers.task_scheduler"]
```

Note: No ports exposed — this is a background worker, not a web service.

---

## Validation Notes (codebase checks)

Validated against codebase on 2026-02-04:

### Confirmed ✓
- `PaginatedResponse` and `PaginationParams` exist in `libs/common/src/common/models/pagination.py`
- `Thread` model has `thread_id`, `connector_id`, `channel_type`, `active_order` (FK to Order)
- `Connector` model has `type` field (CharEnumField with ConnectorType enum)
- Jinja2 is already a dependency in sales-agent
- Tool handler pattern uses closures for `order_id` injection (see `_create_update_order_*` handlers)
- Internal API pattern exists at `apps/sales-agent/src/sales_agent/api/internal.py`
- `SalesAgentClient` in backend has `forward_inbound()` — add `execute_task()` following same pattern

### Missing (to implement)
- `OrderService.get_order(company_id, order_id)` — currently only uses `orders_repo.get_by_id()`
- `OrderService.log_event()` — currently `OrderLog.create()` called directly in repository
- `OrderService.delete_order()` — does not exist, needed for cascade task deletion
- `OrderLogType` needs `TASK_CREATED` and `TASK_COMPLETED` entries
- `process_user_message_agents` lacks `reminder_instructions` param
- `process_reminder()` function in `message_processor.py`

### Edge Cases to Handle
1. **Task execution failure** — recorded via `record_failure()`, task stays pending for retry
2. **Order deleted before task due** — task deleted via cascade (to implement)
3. **Thread lookup fails** — log error, record failure, retry on next cycle
4. **Sales Agent unavailable** — HTTP error recorded as failure, automatic retry
