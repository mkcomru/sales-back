from typing import TypeVar

from src.backend.modules.core.base_model import BaseModel

ModelType = TypeVar("ModelType", bound=BaseModel)


class BaseRepository[ModelType: BaseModel]:
    def __init__(self, model: type[ModelType]):
        self.model = model

    async def _get(self, id: int) -> ModelType | None:
        return await self.model.get_or_none(id=id)

    async def _create(self, *args, **kwargs) -> ModelType:
        return await self.model.create(*args, **kwargs)

    async def _delete(self, id: int) -> bool:
        instance = await self.model.get_or_none(id=id)

        if instance is not None:
            await instance.delete()

        return bool(instance)

    async def _list(self) -> list[ModelType]:
        return await self.model.all()

    async def _update(self, id: int, updates: dict) -> ModelType | None:
        instance = await self.model.get_or_none(id=id)

        if instance is None:
            return None

        for key, value in updates.items():
            setattr(instance, key, value)

        await instance.save()

        return instance
