"""Central exception handlers registry.

Collects all exception handlers from packages for FastAPI app.
"""

from src.backend.modules.categories.exceptions import (
    CategoryNotFoundError,
    category_not_found_handler,
)
from src.backend.modules.companies.exceptions import (
    CompanyNotFoundError,
    FAQNotFoundError,
    company_not_found_handler,
    faq_not_found_handler,
)
from src.backend.modules.fields.exceptions import (
    FieldNotFoundError,
    FieldOptionNotFoundError,
    SystemFieldError,
    field_not_found_handler,
    field_option_not_found_handler,
    system_field_error_handler,
)
from src.backend.modules.forms.exceptions import (
    FormNotFoundError,
    FormValidationError,
    form_not_found_handler,
    form_validation_error_handler,
)
from src.backend.modules.integrations.exceptions import (
    IntegrationCapabilityConflictError,
    IntegrationConflictError,
    IntegrationNotFoundError,
    integration_capability_conflict_handler,
    integration_conflict_handler,
    integration_not_found_handler,
)
from src.backend.modules.products.exceptions import (
    ProductNotFoundError,
    product_not_found_handler,
)
from src.backend.modules.prompt_addon.exceptions import (
    PromptAddonNotFoundError,
    prompt_addon_not_found_handler,
)
from src.backend.modules.prompts.exceptions import (
    PromptNotFoundError,
    prompt_not_found_handler,
)
from src.backend.modules.s3_storage.exceptions import (
    S3FileNotFoundError,
    S3StorageError,
    s3_file_not_found_handler,
    s3_storage_error_handler,
)
from src.backend.modules.simulator.exceptions import (
    SimulatorSessionNotFoundError,
    simulator_session_not_found_handler,
)
from src.backend.modules.tools.exceptions import (
    ToolNotFoundError,
    tool_not_found_handler,
)
from src.backend.modules.transport.exceptions import (
    ConnectorNotFoundError,
    connector_not_found_handler,
)
from src.backend.modules.users.exceptions import (
    UserAlreadyExistsError,
    user_already_exists_handler,
)

exception_handlers = {
    PromptNotFoundError: prompt_not_found_handler,
    UserAlreadyExistsError: user_already_exists_handler,
    CategoryNotFoundError: category_not_found_handler,
    CompanyNotFoundError: company_not_found_handler,
    FAQNotFoundError: faq_not_found_handler,
    FieldNotFoundError: field_not_found_handler,
    FieldOptionNotFoundError: field_option_not_found_handler,
    SystemFieldError: system_field_error_handler,
    FormNotFoundError: form_not_found_handler,
    FormValidationError: form_validation_error_handler,
    ProductNotFoundError: product_not_found_handler,
    ToolNotFoundError: tool_not_found_handler,
    ConnectorNotFoundError: connector_not_found_handler,
    SimulatorSessionNotFoundError: simulator_session_not_found_handler,
    S3FileNotFoundError: s3_file_not_found_handler,
    S3StorageError: s3_storage_error_handler,
    PromptAddonNotFoundError: prompt_addon_not_found_handler,
    IntegrationNotFoundError: integration_not_found_handler,
    IntegrationConflictError: integration_conflict_handler,
    IntegrationCapabilityConflictError: integration_capability_conflict_handler,
}
