from pydantic import BaseModel, Field

from src.backend.modules.fields.models import FieldLevel


class FieldOptionResponse(BaseModel):
    """Опция для ENUM поля"""

    id: int
    value: str
    order: int


class FieldOptionRequest(BaseModel):
    """Запрос на создание опции поля"""

    value: str
    order: int = 0


class FieldOptionPatch(BaseModel):
    """Запрос на обновление опции поля"""

    value: str | None = None
    order: int | None = None


class FieldBase(BaseModel):
    """Базовая модель поля"""

    name: str
    question: str
    type: str
    required: bool = False
    display_name: str | None = None
    level: FieldLevel = FieldLevel.CUSTOMER
    is_system: bool = False
    category_id: int | None = None
    product_id: int | None = None


class FieldRequest(FieldBase):
    """Запрос на создание поля"""

    pass


class FieldPatch(BaseModel):
    """Запрос на обновление поля"""

    name: str | None = None
    question: str | None = None
    type: str | None = None
    required: bool | None = None
    display_name: str | None = None
    level: FieldLevel | None = None
    is_system: bool | None = None
    category_id: int | None = None
    product_id: int | None = None


class FieldResponse(BaseModel):
    """Кастомное поле компании"""

    id: int
    name: str
    question: str
    type: str
    required: bool
    display_name: str | None = None
    level: FieldLevel
    is_system: bool
    category_id: int | None = None
    product_id: int | None = None
    options: list[FieldOptionResponse] = Field(default_factory=list)
