from pydantic import BaseModel


class ToolItemResponse(BaseModel):
    name: str
    description: str


class ToolGroupResponse(BaseModel):
    group: str
    tools: list[ToolItemResponse]
