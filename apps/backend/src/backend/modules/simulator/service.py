from datetime import UTC, datetime

import httpx
import structlog

from src.backend.modules.companies.exceptions import CompanyNotFoundError
from src.backend.modules.companies.repository import CompaniesRepository
from src.backend.modules.core.settings import get_settings
from src.backend.modules.simulator.repository import SimulatorRepository
from src.backend.modules.simulator.schemas import (
    SimulatorMessageResponse,
    SimulatorResetResponse,
)
from src.backend.modules.users.models import CompanyUser

log = structlog.get_logger(__name__)


class SimulatorService:
    """Service for AI agent simulator/sandbox."""

    def __init__(self):
        self.repository = SimulatorRepository()
        self.companies_repository = CompaniesRepository()

    async def reset_session(self, company_id: int, user_id: int) -> SimulatorResetResponse:
        """Reset simulator session (clear history and context)."""
        company = await self.companies_repository.get_by_id(company_id)
        if not company:
            raise CompanyNotFoundError()

        company_user = await CompanyUser.filter(company_id=company_id, user_id=user_id).first()

        if not company_user:
            raise CompanyNotFoundError()

        await self.repository.reset_session(company_user.id)

        return SimulatorResetResponse(
            success=True,
            message="Simulator session reset successfully",
        )

    async def process_message(self, company_id: int, user_id: int, text: str) -> SimulatorMessageResponse:
        """Process user message in simulator and return AI response.

        This method:
        1. Loads or creates simulator session
        2. Adds user message to history
        3. Calls Sales Agent (TODO: integrate with Sales Agent)
        4. Adds AI response to history
        5. Returns response

        Currently returns mock response until Sales Agent integration.
        """
        company = await self.companies_repository.get_by_id(company_id)
        if not company:
            raise CompanyNotFoundError()

        company_user = await CompanyUser.filter(company_id=company_id, user_id=user_id).first()

        if not company_user:
            raise CompanyNotFoundError()

        timestamp = datetime.now(UTC)
        timestamp_str = timestamp.isoformat()

        await self.repository.add_message(
            company_user_id=company_user.id,
            role="user",
            content=text,
            timestamp=timestamp_str,
        )

        ai_response = await self._generate_ai_response(company_id, text, user_id=str(user_id))

        await self.repository.add_message(
            company_user_id=company_user.id,
            role="assistant",
            content=ai_response,
            timestamp=timestamp_str,
        )

        return SimulatorMessageResponse(
            text=ai_response,
            timestamp=timestamp,
        )

    async def _generate_ai_response(self, company_id: int, text: str, user_id: str = "simulator_user") -> str:
        """Generate AI response by calling Sales Agent in simulator mode.

        Args:
            company_id: Company ID
            text: User message text
            user_id: Simulated user ID

        Returns:
            AI assistant response
        """
        settings = get_settings()
        sales_agent_url = settings.sales_agent.url

        if not sales_agent_url:
            company = await self.companies_repository.get_by_id(company_id)
            assistant_name = company.assistant_name if company else "AI"
            return (
                f"[Simulator Mode - Offline] Привет! Я {assistant_name}. "
                f"Вы написали: '{text}'. "
                "Sales Agent URL не настроен в конфигурации."
            )

        payload = {
            "text": text,
            "company_id": company_id,
            "user_id": user_id,
        }

        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{sales_agent_url}api/simulator/message",
                    json=payload,
                )
                response.raise_for_status()
                data = response.json()
                return data.get("text", "")

        except httpx.HTTPStatusError as exc:
            log.error(
                "simulator.sales_agent.http_error",
                status_code=exc.response.status_code,
                error=str(exc),
            )
            return f"Ошибка при обращении к Sales Agent: {exc.response.status_code}"

        except httpx.RequestError as exc:
            log.error(
                "simulator.sales_agent.connection_error",
                error=str(exc),
            )
            return f"Не удалось подключиться к Sales Agent: {str(exc)}"

        except Exception as exc:
            log.exception(
                "simulator.sales_agent.unexpected_error",
                error=str(exc),
            )
            return f"Неожиданная ошибка: {str(exc)}"
