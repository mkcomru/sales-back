from pydantic import BaseModel


class PromptRequest(BaseModel):
    """Запрос на создание/обновление промпта"""

    content: str


class PromptResponse(BaseModel):
    """Промпт агента"""

    id: int
    agent_type: str
    content: str
