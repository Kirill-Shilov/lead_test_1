"""
Базовый протокол (интерфейс) для всех адаптеров.

Все адаптеры (MatrixApiAdapter, UiAdapter, будущий MobileAdapter)
реализуют этот Protocol. Это позволяет тестам быть независимыми
от конкретной реализации (API или UI).

Принцип: тест получает абстрактный BaseAdapter и не знает,
как именно отправляется сообщение — через HTTP или через браузер.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from framework.models.message import Message
from framework.models.room import Room
from framework.models.user import User


@runtime_checkable
class BaseAdapter(Protocol):
    """
    Общий интерфейс для взаимодействия с Matrix-клиентом.
    Все методы асинхронные.
    """

    async def login(self, user: User) -> None:
        """Авторизует адаптер под указанным пользователем."""
        ...

    async def send_message(self, room: Room, body: str, txn_id: str = "") -> Message:
        """
        Отправляет текстовое сообщение в комнату.

        Args:
            room: целевая комната
            body: текст сообщения
            txn_id: клиентский transaction ID (для идемпотентности)

        Returns:
            Message с event_id от сервера
        """
        ...

    async def get_messages(self, room: Room, limit: int = 10) -> list[Message]:
        """
        Получает последние сообщения из комнаты.

        Args:
            room: комната
            limit: максимальное количество сообщений

        Returns:
            список Message в хронологическом порядке
        """
        ...

    async def create_room(self, name: str = "", is_private: bool = True) -> Room:
        """
        Создаёт новую комнату.

        Args:
            name: имя комнаты
            is_private: если True — комната инвайт-only

        Returns:
            Room с заполненным room_id
        """
        ...

    async def leave_room(self, room: Room) -> None:
        """Покидает комнату (и удаляет если пусто)."""
        ...
