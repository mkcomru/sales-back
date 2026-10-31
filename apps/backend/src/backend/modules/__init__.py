"""Central router aggregator for all app packages."""

from fastapi import APIRouter

import src.backend.integrations  # noqa: F401  — triggers provider registration
from src.backend.modules.auth.routers import router as auth_router
from src.backend.modules.billing.routers import router as billing_router
from src.backend.modules.categories.routers import router as categories_router
from src.backend.modules.chat.routers import (
    internal_router as chat_internal_router,
)
from src.backend.modules.chat.routers import (
    public_router as chat_public_router,
)
from src.backend.modules.chat.routers import (
    websocket_router as chat_websocket_router,
)
from src.backend.modules.companies.routers import (
    internal_router as companies_internal_router,
)
from src.backend.modules.companies.routers import (
    public_router as companies_public_router,
)
from src.backend.modules.fields.routers import router as fields_router
from src.backend.modules.forms.routers import public_router as forms_public_router
from src.backend.modules.forms.routers import router as forms_router
from src.backend.modules.integrations.capability_routes import router as capabilities_internal_router
from src.backend.modules.integrations.routers import router as integrations_router
from src.backend.modules.messages.routers import (
    internal_router as messages_internal_router,
)
from src.backend.modules.messages.routers import router as messages_router
from src.backend.modules.orders.routers import (
    internal_router as orders_internal_router,
)
from src.backend.modules.orders.routers import public_router as orders_public_router
from src.backend.modules.pings.routers import router as pings_router
from src.backend.modules.products.routers import public_router as products_public_router
from src.backend.modules.products.routers import router as products_router
from src.backend.modules.prompt_addon.routers import router as prompt_addon_router
from src.backend.modules.prompts.routers import router as agents_router
from src.backend.modules.s3_storage.routers import (
    internal_router as artifacts_internal_router,
)
from src.backend.modules.s3_storage.routers import (
    public_direct_router as artifacts_public_direct_router,
)
from src.backend.modules.s3_storage.routers import (
    public_router as artifacts_public_router,
)
from src.backend.modules.simulator.routers import router as simulator_router
from src.backend.modules.stages.routers import public_router as stages_public_router
from src.backend.modules.sync.routers import router as sync_router
from src.backend.modules.tasks.routes import internal_router as tasks_internal_router
from src.backend.modules.tasks.routes import router as tasks_router
from src.backend.modules.tools.routers import router as tools_router
from src.backend.modules.transport.routers import router as transport_router
from src.backend.modules.users.routers import company_users_router
from src.backend.modules.users.routers import router as users_router

router = APIRouter(prefix="/api/v1")

router.include_router(artifacts_public_direct_router)
router.include_router(auth_router)
router.include_router(users_router)
router.include_router(company_users_router)
router.include_router(companies_public_router)
router.include_router(companies_internal_router)
router.include_router(categories_router)
router.include_router(products_router)
router.include_router(products_public_router)
router.include_router(agents_router)
router.include_router(tools_router)
router.include_router(transport_router)
router.include_router(prompt_addon_router)
router.include_router(messages_router)
router.include_router(messages_internal_router)
router.include_router(fields_router)
router.include_router(forms_router)
router.include_router(forms_public_router)
router.include_router(artifacts_public_router)
router.include_router(chat_public_router)
router.include_router(chat_websocket_router)
router.include_router(chat_internal_router)
router.include_router(orders_public_router)
router.include_router(orders_internal_router)
router.include_router(stages_public_router)
router.include_router(artifacts_internal_router)
router.include_router(sync_router)
router.include_router(simulator_router)
router.include_router(billing_router)
router.include_router(tasks_router)
router.include_router(tasks_internal_router)
router.include_router(integrations_router)
router.include_router(capabilities_internal_router)
router.include_router(pings_router)

__all__ = ["router"]
