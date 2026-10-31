---
name: async-patterns
description: Apply when writing async Python code, FastAPI endpoints, asyncio, aiohttp, Redis or PostgreSQL operations
allowed-tools: Read, Grep
---

- Только `aiohttp`/`httpx`, никогда `requests`
- `asyncio.sleep()`, никогда `time.sleep()`
- Все FastAPI endpoints — `async def`
- Переиспользуй connection pools для Redis и asyncpg, не создавай в каждом запросе
- `asyncio.gather()` для параллельных операций
- Не блокируй event loop CPU-тяжёлыми операциями — используй `run_in_executor`
