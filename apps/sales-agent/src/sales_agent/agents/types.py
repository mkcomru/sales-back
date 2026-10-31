from __future__ import annotations

from pydantic import BaseModel

JsonScalar = str | int | float | bool | None


class FieldUpdate(BaseModel):
    key: str
    value: JsonScalar
