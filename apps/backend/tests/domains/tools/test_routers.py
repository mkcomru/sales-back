"""Router tests for tools."""

import httpx


async def test_list_available_tools(api_client: httpx.AsyncClient, authenticated_user_with_company):
    auth = authenticated_user_with_company
    company_id = auth["company"].id
    response = await api_client.get(
        f"/api/v1/companies/{company_id}/tools/available",
        headers=auth["headers"],
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    for group in data:
        assert "group" in group
        assert "tools" in group
        assert isinstance(group["tools"], list)
        for tool in group["tools"]:
            assert "name" in tool
            assert "description" in tool
            assert isinstance(tool["description"], str)
            assert tool["description"]
