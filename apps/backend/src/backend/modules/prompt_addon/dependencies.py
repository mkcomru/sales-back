from typing import Annotated

from fastapi import Depends

from src.backend.modules.prompt_addon.service import PromptAddonsService

PromptAddonsServiceDep = Annotated[PromptAddonsService, Depends(PromptAddonsService)]
