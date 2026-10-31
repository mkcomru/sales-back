---
name: db-migrations
description: Apply when working with Tortoise ORM models, Aerich migrations, or database schema changes
allowed-tools: Read, Bash
---

- Никогда не редактируй файлы миграций вручную
- После изменения модели: `aerich migrate --name describe_change`
- Затем: `aerich upgrade`
- Для отката: `aerich downgrade`
- Используй `fields.UUIDField(pk=True)` для primary keys
- Все даты через `fields.DatetimeField(auto_now_add=True)`
