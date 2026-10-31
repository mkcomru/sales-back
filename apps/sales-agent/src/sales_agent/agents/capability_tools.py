"""Capability tool handlers for integration-driven agent tools.

Each handler calls the corresponding Backend internal capability endpoint.
Concrete tool handlers are added by integration-specific plans.

Pattern:

    async def get_available_slots(context: RunContextWrapper, ...) -> str:
        response = await backend_client.post(
            "/api/v1/internal/capabilities/scheduling/slots",
            json={...},
        )
        return response.text
"""
