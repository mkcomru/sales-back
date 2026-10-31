import uvicorn
from fastapi import FastAPI

from common import SalesAgentSettings
from common.fastapi import apply_cors

from src.sales_agent.lifespan import lifespan

app = FastAPI(title="Sales Agent", lifespan=lifespan)
apply_cors(app, SalesAgentSettings().cors)


@app.get("/healthz")
async def healthz():
    return {"ok": True, "service": "sales-agent", "mode": "connector-webhook"}


if __name__ == "__main__":
    uvicorn.run(
        "src.sales_agent.main:app",
        host="0.0.0.0",
        port=8000,
        log_config=None,
    )
