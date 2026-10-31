from src.backend.modules.core.base_repo import BaseRepository
from src.backend.modules.simulator.models import SimulatorSession


class SimulatorRepository(BaseRepository[SimulatorSession]):
    """Repository for simulator sessions."""

    def __init__(self):
        super().__init__(SimulatorSession)

    async def get_or_create_session(self, company_user_id: int) -> tuple[SimulatorSession, bool]:
        """Get or create simulator session for company user.

        Returns:
            (session, created) tuple
        """
        session = await SimulatorSession.filter(
            company_user_id=company_user_id,
        ).first()

        if session:
            return session, False

        session = await SimulatorSession.create(
            company_user_id=company_user_id,
            messages=[],
            context={},
        )
        return session, True

    async def reset_session(self, company_user_id: int) -> None:
        """Reset (clear) simulator session for company user."""
        session = await SimulatorSession.filter(
            company_user_id=company_user_id,
        ).first()

        if session:
            session.messages = []
            session.context = {}
            await session.save()

    async def add_message(
        self,
        company_user_id: int,
        role: str,
        content: str,
        timestamp: str,
    ) -> SimulatorSession:
        """Add message to simulator session history."""
        session, _ = await self.get_or_create_session(company_user_id)

        message = {
            "role": role,
            "content": content,
            "timestamp": timestamp,
        }

        messages = session.messages or []
        messages.append(message)
        session.messages = messages

        await session.save()
        return session
