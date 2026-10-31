from __future__ import annotations

from pydantic import BaseModel, Field


class PaginationParams(BaseModel):
    """Параметры пагинации для запросов"""

    limit: int = Field(default=50, ge=1, le=1000, description="Количество элементов на странице")
    offset: int = Field(default=0, ge=0, description="Смещение от начала списка")


class PaginatedResponse[T: BaseModel](BaseModel):
    """Абстрактная модель ответа с пагинацией для всех list view"""

    items: list[T] = Field(default_factory=list, description="Список элементов")
    total: int = Field(ge=0, description="Общее количество элементов")
    limit: int = Field(ge=1, description="Количество элементов на странице")
    offset: int = Field(ge=0, description="Смещение от начала списка")

    @property
    def has_next(self) -> bool:
        """Есть ли следующая страница"""
        return self.offset + self.limit < self.total

    @property
    def has_previous(self) -> bool:
        """Есть ли предыдущая страница"""
        return self.offset > 0

    @property
    def total_pages(self) -> int:
        """Общее количество страниц"""
        if self.total == 0:
            return 0
        return (self.total + self.limit - 1) // self.limit

    @property
    def current_page(self) -> int:
        """Текущий номер страницы (начиная с 1)"""
        if self.limit == 0:
            return 1
        return (self.offset // self.limit) + 1
