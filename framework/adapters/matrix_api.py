"""
MatrixApiAdapter — реализация BaseAdapter через Matrix HTTP Client-Server API.

Использует httpx.AsyncClient с кастомным транспортом из NetworkController.
Это позволяет контролировать сетевые условия (задержки, перехваты) на уровне
конкретного экземпляра клиента, не затрагивая другие клиенты в том же тесте.
"""
from __future__ import annotations

import uuid
from typing import Optional

import httpx

from framework.adapters.base import BaseAdapter
from framework.controllers.network import NetworkController
from framework.models.message import Message
from framework.models.room import Room
from framework.models.user import User


class MatrixApiAdapter(BaseAdapter):
    """
    Адаптер для Matrix Client-Server API (v3).

    Args:
        network_controller: контроллер сети данного клиента.
                            Если None — используется стандартный транспорт.
    """

    def __init__(self, network_controller: Optional[NetworkController] = None) -> None:
        self._nc = network_controller or NetworkController()
        self._user: Optional[User] = None
        # Клиент создаётся при login, чтобы использовать актуальный транспорт
        self._client: Optional[httpx.AsyncClient] = None

    # ------------------------------------------------------------------
    # BaseAdapter implementation
    # ------------------------------------------------------------------

    async def login(self, user: User) -> None:
        """
        Инициализирует httpx-клиент с токеном пользователя.
        Применяет NetworkController как кастомный транспорт.
        """
        self._user = user
        self._client = httpx.AsyncClient(
            base_url=user.homeserver,
            headers={"Authorization": f"Bearer {user.access_token}"},
            transport=self._nc.build_transport(),
        )

    async def send_message(self, room: Room, body: str, txn_id: str = "") -> Message:
        """
        Отправляет m.room.message через PUT /send/<txnId>.
        Matrix гарантирует идемпотентность по txnId:
        повторный запрос с тем же txnId вернёт тот же event_id.
        """
        client, user = self._ensure_logged_in()
        if not txn_id:
            txn_id = uuid.uuid4().hex

        resp = await client.put(
            f"/_matrix/client/v3/rooms/{room.room_id}/send/m.room.message/{txn_id}",
            json={"msgtype": "m.text", "body": body},
        )
        resp.raise_for_status()
        data = resp.json()

        return Message(
            event_id=data["event_id"],
            body=body,
            sender=user.user_id,
            txn_id=txn_id,
            timestamp=0,      # сервер вернёт timestamp позже через /messages
            room_id=room.room_id,
        )

    async def get_messages(self, room: Room, limit: int = 10) -> list[Message]:
        """
        Получает последние сообщения через GET /messages.
        Возвращает только события типа m.room.message.
        """
        client, _ = self._ensure_logged_in()

        resp = await client.get(
            f"/_matrix/client/v3/rooms/{room.room_id}/messages",
            params={"limit": limit, "dir": "b"},  # dir=b — от новых к старым
        )
        resp.raise_for_status()
        data = resp.json()

        messages = []
        for event in reversed(data.get("chunk", [])):
            if event.get("type") != "m.room.message":
                continue
            content = event.get("content", {})
            messages.append(Message(
                event_id=event["event_id"],
                body=content.get("body", ""),
                sender=event["sender"],
                txn_id=event.get("unsigned", {}).get("transaction_id", ""),
                timestamp=event.get("origin_server_ts", 0),
                room_id=room.room_id,
            ))

        return messages

    async def create_room(self, name: str = "", is_private: bool = True) -> Room:
        """Создаёт комнату и возвращает объект Room."""
        client, _ = self._ensure_logged_in()

        body: dict = {
            "preset": "private_chat" if is_private else "public_chat",
        }
        if name:
            body["name"] = name

        resp = await client.post(
            "/_matrix/client/v3/createRoom",
            json=body,
        )
        resp.raise_for_status()
        data = resp.json()

        return Room(
            room_id=data["room_id"],
            name=name,
        )

    async def leave_room(self, room: Room) -> None:
        """Покидает комнату (POST /leave)."""
        client, _ = self._ensure_logged_in()
        resp = await client.post(
            f"/_matrix/client/v3/rooms/{room.room_id}/leave"
        )
        resp.raise_for_status()

    # ------------------------------------------------------------------
    # Вспомогательные методы
    # ------------------------------------------------------------------

    async def aclose(self) -> None:
        """Закрывает httpx-клиент. Вызывается фикстурой после теста."""
        if self._client:
            await self._client.aclose()

    def _ensure_logged_in(self) -> tuple[httpx.AsyncClient, User]:
        if not self._client or not self._user:
            raise RuntimeError("Вызовите login() перед использованием адаптера")
        return self._client, self._user

    # ------------------------------------------------------------------
    # Контекстный менеджер
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "MatrixApiAdapter":
        return self

    async def __aexit__(self, *args) -> None:
        await self.aclose()
