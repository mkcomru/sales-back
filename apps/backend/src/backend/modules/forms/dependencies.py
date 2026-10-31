"""Dependencies for forms module."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from src.backend.modules.forms.models import FormTemplate
from src.backend.modules.forms.repository import FormsRepository
from src.backend.modules.forms.service import FormsService
from src.backend.modules.forms.utils import hash_form_api_key


async def get_forms_service() -> FormsService:
    """Get forms service instance."""
    return FormsService()


FormsServiceDep = Annotated[FormsService, Depends(get_forms_service)]


async def get_form_by_api_key(x_form_key: str = Header(..., alias="X-Form-Key")) -> FormTemplate:
    """Validate X-Form-Key header and return FormTemplate."""
    key_hash = hash_form_api_key(x_form_key)
    repo = FormsRepository()
    form = await repo.get_by_key_hash(key_hash)
    if not form or not form.enabled:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or disabled form key")
    return form


FormByApiKeyDep = Annotated[FormTemplate, Depends(get_form_by_api_key)]
