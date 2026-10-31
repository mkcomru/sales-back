"""Dependencies for sync module."""

from typing import Annotated

from fastapi import Depends

from src.backend.modules.chat.dependencies import ChatServiceDep
from src.backend.modules.sync.service import SyncService


def sync_service(chat_service: ChatServiceDep) -> SyncService:
    return SyncService(chat_service=chat_service)


SyncServiceDep = Annotated[SyncService, Depends(sync_service)]
