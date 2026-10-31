from typing import Annotated

from fastapi import Depends

from src.backend.modules.simulator.service import SimulatorService


async def get_simulator_service() -> SimulatorService:
    """Get simulator service instance."""
    return SimulatorService()


SimulatorServiceDep = Annotated[SimulatorService, Depends(get_simulator_service)]
