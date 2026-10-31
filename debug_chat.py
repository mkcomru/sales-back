#!/usr/bin/env python3
# flake8: noqa: E501
"""
Интерактивный скрипт для отладки sales-agent через Bitrix webhook API.

Использование:
    python debug_chat.py

Опции:
    --port PORT         Порт sales-agent (по умолчанию 8009)
    --host HOST         Хост sales-agent (по умолчанию localhost)
    --user-id ID        ID пользователя (по умолчанию debug_user)
    --conversation CONV ID разговора (по умолчанию debug_conversation)
    --token TOKEN       Bitrix token (опционально)
    --wait SECONDS      Время ожидания ответа в секундах (по умолчанию 120)
"""

import argparse
import asyncio
import sys
import time
import uuid
from datetime import datetime

import httpx


class ChatDebugger:
    def __init__(
        self,
        host: str = "localhost",
        port: int = 8009,
        user_id: str = "debug_user",
        conversation_id: str = "debug_conversation",
        token: str | None = None,
        wait_seconds: int = 120,
    ):
        self.base_url = f"http://{host}:{port}"
        self.user_id = user_id
        self.conversation_id = conversation_id
        self.token = token
        self.wait_seconds = wait_seconds
        self.message_counter = 0

        # Save original prefixes for generating new IDs
        self._original_user_prefix = user_id
        self._original_conversation_prefix = conversation_id

    def _build_webhook_payload(self, text: str) -> dict:
        """Создать payload для webhook."""
        self.message_counter += 1
        payload = {
            "company_id": 1,
            "conversation_id": self.conversation_id,
            "user_id": self.user_id,
            "text": text,
            "ts": time.time(),
            "metadata": {
                "source": "debug_script",
                "timestamp": datetime.now().isoformat(),
                "message_number": self.message_counter,
            },
        }

        if self.token:
            payload["token"] = self.token

        # Добавляем фейковые данные для более реалистичного тестирования
        if self.message_counter == 1:
            payload.update(
                {
                    "lead_id": "debug_lead_123",
                    "phone": "+7999123456",
                    "metadata": {
                        **payload["metadata"],
                        "lead_source": "debug",
                        "bitrix_user_name": "Debug User",
                    },
                }
            )

        return payload

    def reset_session(self):
        """Сбросить сессию - создать новые ID и очистить счетчик."""
        # Генерируем новые уникальные ID
        session_suffix = str(uuid.uuid4())[:8]
        self.user_id = f"{self._original_user_prefix}_{session_suffix}"
        self.conversation_id = f"{self._original_conversation_prefix}_{session_suffix}"
        self.message_counter = 0

        print("🔄 Новая сессия:")
        print(f"   User ID: {self.user_id}")
        print(f"   Conversation ID: {self.conversation_id}")
        print("   История диалога сброшена")

    def create_new_session(self, custom_user_id: str | None = None):
        """Создать новую сессию с опциональным custom user_id."""
        session_suffix = str(uuid.uuid4())[:8]

        if custom_user_id:
            self.user_id = f"{custom_user_id}_{session_suffix}"
            self._original_user_prefix = custom_user_id
        else:
            self.user_id = f"{self._original_user_prefix}_{session_suffix}"

        self.conversation_id = f"{self._original_conversation_prefix}_{session_suffix}"
        self.message_counter = 0

        print("🆕 Новая сессия создана:")
        print(f"   User ID: {self.user_id}")
        print(f"   Conversation ID: {self.conversation_id}")
        print("   История диалога сброшена")

    def show_presets(self):
        """Показать готовые тестовые фразы для отладки."""
        presets = {
            "Инвестор (новостройка)": [
                "Привет! Интересует ремонт новостройки под аренду",
                "Москва, ЖК Триумф Палас, 65 кв.м, 2 комнаты",
                "Чистовая отделка, ключи на руках, бюджет 2.5 млн",
            ],
            "FAQ запросы": [
                "Какие у вас цены за квадратный метр?",
                "Сколько длится ремонт?",
                "Какие гарантии вы даете?",
                "Покажите примеры ваших работ",
            ],
            "Жесткие ворота": [
                "Нужен ремонт квартиры для себя",
                "Интересует ремонт вторички",
                "Есть частный дом в Подмосковье",
                "Квартира в Екатеринбурге",
            ],
            "Сложные кейсы": [
                "Москва, но далеко от метро - 25 минут пешком",
                "СПб, но за КАД - 5 км от кольцевой",
                "Очень маленький бюджет - 500 тысяч на всё",
            ],
        }

        print("\n📋 Готовые тестовые фразы:")
        print("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        for category, phrases in presets.items():
            print(f"\n🔸 {category}:")
            for i, phrase in enumerate(phrases, 1):
                print(f"   {i}. {phrase}")

        print("\n💡 Скопируйте и вставьте любую фразу для тестирования!")

    async def send_message(self, text: str) -> bool:
        """Отправить сообщение в webhook."""
        payload = self._build_webhook_payload(text)

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(f"{self.base_url}/bitrix/webhook", json=payload)
                response.raise_for_status()
                data = response.json()

                print(
                    f"✓ Сообщение отправлено (ack: {data.get('ok', False)}, окно: {data.get('window_seconds', 'N/A')}с)"
                )
                return True

        except httpx.HTTPError as e:
            print(f"✗ Ошибка отправки: {e}")
            if isinstance(e, httpx.HTTPStatusError):
                response = e.response
                try:
                    error_data = response.json()
                    print(f"  Детали: {error_data}")
                except Exception:
                    print(f"  HTTP {response.status_code}: {response.text}")
            return False
        except Exception as e:
            print(f"✗ Неожиданная ошибка: {e}")
            return False

    async def poll_replies(self) -> list[str]:
        """Получить ответы через poll endpoint."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(
                    f"{self.base_url}/bitrix/poll",
                    params={"conversation_id": self.conversation_id},
                )
                response.raise_for_status()
                data = response.json()
                return data.get("replies", [])

        except httpx.HTTPError as e:
            print(f"✗ Ошибка получения ответов: {e}")
            return []
        except Exception as e:
            print(f"✗ Неожиданная ошибка при poll: {e}")
            return []

    async def wait_for_replies(self) -> list[str]:
        """Ждать ответы с периодическим опросом."""
        print(f"⏳ Ждем ответ (до {self.wait_seconds}с, опрос каждые 5с)...")

        start_time = time.time()
        while time.time() - start_time < self.wait_seconds:
            replies = await self.poll_replies()
            if replies:
                return replies

            remaining = int(self.wait_seconds - (time.time() - start_time))
            if remaining > 0:
                print(f"   ⏰ Осталось ~{remaining}с...")
                await asyncio.sleep(5)

        print("⏰ Время ожидания истекло")
        return []

    async def check_health(self) -> bool:
        """Проверить доступность sales-agent."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{self.base_url}/healthz")
                response.raise_for_status()
                data = response.json()
                print(f"✓ Sales-agent доступен: {data}")
                return True
        except Exception as e:
            print(f"✗ Sales-agent недоступен: {e}")
            return False

    async def interactive_chat(self):
        """Основной интерактивный цикл."""
        print(
            f"""
🤖 Debug Chat для Sales Agent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Подключение: {self.base_url}
  Пользователь: {self.user_id}
  Разговор: {self.conversation_id}
  Токен: {"установлен" if self.token else "не установлен"}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Команды:
  - Любой текст: отправить сообщение боту
  - /health: проверить статус sales-agent
  - /info: показать текущие настройки
  - /clear: начать новый диалог (сброс истории и ID)
  - /new [user_id]: создать новую сессию с заданным user_id
  - /preset: показать готовые тестовые фразы
  - /quit, /exit: выйти

Для начала проверим доступность сервиса...
        """
        )

        if not await self.check_health():
            print("\n⚠️  Sales-agent не отвечает. Убедитесь что он запущен:")
            print("   cd apps/sales-agent")
            print("   poetry run uvicorn src.main:app --reload --port 8009")
            return

        print("\n💬 Можете начинать чат! Введите сообщение:")

        while True:
            try:
                # Ввод пользователя
                user_input = input("\n👤 Вы: ").strip()

                if not user_input:
                    continue

                # Обработка команд
                if user_input in ["/quit", "/exit"]:
                    print("👋 До свидания!")
                    break
                elif user_input == "/health":
                    await self.check_health()
                    continue
                elif user_input == "/info":
                    print(
                        f"""
📋 Текущие настройки:
   URL: {self.base_url}
   User ID: {self.user_id}
   Conversation ID: {self.conversation_id}
   Сообщений отправлено: {self.message_counter}
   Время ожидания: {self.wait_seconds}с
                    """
                    )
                    continue
                elif user_input == "/clear":
                    self.reset_session()
                    continue
                elif user_input.startswith("/new"):
                    # Парсим /new [optional_user_id]
                    parts = user_input.split(maxsplit=1)
                    custom_user_id = parts[1] if len(parts) > 1 else None
                    self.create_new_session(custom_user_id)
                    continue
                elif user_input == "/preset":
                    self.show_presets()
                    continue

                # Отправка сообщения
                if not await self.send_message(user_input):
                    continue

                # Ожидание ответа
                replies = await self.wait_for_replies()

                if replies:
                    print("\n🤖 Бот ответил:")
                    for i, reply in enumerate(replies, 1):
                        if len(replies) > 1:
                            print(f"   {i}. {reply}")
                        else:
                            print(f"   {reply}")
                else:
                    print("🤷 Ответ не получен")

            except KeyboardInterrupt:
                print("\n\n👋 Прервано пользователем. До свидания!")
                break
            except EOFError:
                print("\n\n👋 Ввод завершен. До свидания!")
                break
            except Exception as e:
                print(f"❌ Неожиданная ошибка: {e}")


async def main():
    parser = argparse.ArgumentParser(
        description="Интерактивный отладчик для sales-agent",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--host", default="localhost", help="Хост sales-agent")
    parser.add_argument("--port", type=int, default=8009, help="Порт sales-agent")
    parser.add_argument("--user-id", default="debug_user", help="ID пользователя")
    parser.add_argument("--conversation", default="debug_conversation", help="ID разговора")
    parser.add_argument("--token", help="Bitrix токен (если требуется)")
    parser.add_argument("--wait", type=int, default=120, help="Время ожидания ответа")

    args = parser.parse_args()

    debugger = ChatDebugger(
        host=args.host,
        port=args.port,
        user_id=args.user_id,
        conversation_id=args.conversation,
        token=args.token,
        wait_seconds=args.wait,
    )

    await debugger.interactive_chat()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 До свидания!")
        sys.exit(0)
