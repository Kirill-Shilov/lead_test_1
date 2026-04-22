"""
UiAdapter — реализация BaseAdapter через Playwright (браузерный клиент).

Реализует тот же интерфейс, что MatrixApiAdapter, но работает через UI.
Это позволяет писать тесты, которые можно переключать между API и UI,
просто подменяя адаптер в фикстуре.

Локаторы основаны на Element Web (форк, на котором строится продукт).
При необходимости замените CSS-классы на data-testid атрибуты.
"""
from __future__ import annotations

import uuid
from typing import Optional

from playwright.async_api import Page

from framework.controllers.network import NetworkController
from framework.models.message import Message
from framework.models.room import Room
from framework.models.user import User


class UiAdapter:
    """
    Адаптер для управления веб-клиентом Matrix через Playwright.

    Args:
        page: объект Playwright Page
        base_url: URL веб-клиента (например, https://app.element.io)
        network_controller: контроллер сети; если задан — подключается к странице
    """

    def __init__(
        self,
        page: Page,
        base_url: str = "http://localhost:8080",
        network_controller: Optional[NetworkController] = None,
    ) -> None:
        self._page = page
        self._base_url = base_url.rstrip("/")
        self._nc = network_controller
        self._user: Optional[User] = None

    # ------------------------------------------------------------------
    # BaseAdapter implementation
    # ------------------------------------------------------------------

    async def login(self, user: User) -> None:
        """
        Выполняет вход в Element Web через форму логина.
        После входа ждёт появления главного экрана (список комнат).

        Алгоритм:
        1. Открыть страницу логина
        2. Сменить homeserver на тестовый (Element Web по умолчанию — matrix.org)
        3. Ввести localpart + пароль и подтвердить
        """
        self._user = user

        # Подключаем NetworkController к странице (если задан)
        if self._nc:
            await self._nc.attach_to_page(self._page)

        await self._page.goto(f"{self._base_url}/#/login")

        # Ждём загрузки формы логина
        await self._page.wait_for_selector("input[name='username']", timeout=15_000)

        # Вводим localpart и пароль (homeserver уже задан в config.json Element Web)
        await self._page.fill("input[name='username']", user.localpart)
        await self._page.fill("input[name='password']", user.password)
        await self._page.click("button[type='submit']")

        # Ждём появления домашнего экрана
        await self._page.wait_for_selector(".mx_LeftPanel", timeout=20_000)

    async def send_message(self, room: Room, body: str, txn_id: str = "") -> Message:
        """
        Вводит сообщение в поле ввода и нажимает Enter.
        Возвращает приблизительный объект Message (event_id неизвестен до API-запроса).
        """
        # Поле ввода сообщений в Element Web
        composer = self._page.locator(".mx_SendMessageComposer [contenteditable='true']")
        await composer.click()
        await composer.fill(body)
        await composer.press("Enter")

        # Ждём появления нашего сообщения в ленте
        await self._page.wait_for_selector(
            f".mx_EventTile_body >> text={body}",
            timeout=10_000,
        )

        return Message(
            event_id="",          # UI не возвращает event_id напрямую
            body=body,
            sender=self._user.user_id if self._user else "",
            txn_id=txn_id or uuid.uuid4().hex,
            timestamp=0,
            room_id=room.room_id,
        )

    async def get_messages(self, room: Room, limit: int = 10) -> list[Message]:
        """
        Читает видимые сообщения из ленты.
        Возвращает текстовые блоки в порядке отображения.
        """
        tiles = await self._page.locator(".mx_EventTile_body").all_text_contents()
        return [
            Message(
                event_id="",
                body=text,
                sender="",
                txn_id="",
                timestamp=0,
                room_id=room.room_id,
            )
            for text in tiles[-limit:]
        ]

    async def create_room(self, name: str = "", is_private: bool = True) -> Room:
        """
        Создаёт комнату через UI (кнопка «+» в списке комнат).
        Возвращает Room с name (room_id из URL).
        """
        # Кнопка создания комнаты
        await self._page.click("[aria-label='Add room']")
        await self._page.click("[data-testid='new-room-button']")

        # Вводим имя комнаты
        name_input = self._page.locator("[data-testid='room-name-input']")
        if name:
            await name_input.fill(name)
        else:
            name = f"test-room-{uuid.uuid4().hex[:6]}"
            await name_input.fill(name)

        await self._page.click("[data-testid='create-room-button']")

        # Ждём перехода в новую комнату
        await self._page.wait_for_url("**/#/room/**", timeout=10_000)

        # Извлекаем room_id из URL вида /#/room/!abc:matrix.org
        url = self._page.url
        room_id = url.split("#/room/")[-1].split("?")[0]

        return Room(room_id=room_id, name=name)

    async def leave_room(self, room: Room) -> None:
        """Покидает текущую комнату через меню настроек."""
        await self._page.click("[data-testid='room-header-settings-button']")
        await self._page.click("[data-testid='leave-room-button']")
        await self._page.click("[data-testid='confirm-leave-room']")

    # ------------------------------------------------------------------
    # Вспомогательные методы только для UI
    # ------------------------------------------------------------------

    async def open_room(self, room: Room) -> None:
        """Открывает комнату по room_id (переходит по URL)."""
        await self._page.goto(f"{self._base_url}/#/room/{room.room_id}")
        # Ждём загрузки комнаты
        await self._page.wait_for_selector(".mx_RoomView", timeout=10_000)

    async def last_message_text(self) -> str:
        """Возвращает текст последнего видимого сообщения в ленте."""
        tiles = self._page.locator(".mx_EventTile_body")
        count = await tiles.count()
        if count == 0:
            return ""
        return await tiles.nth(count - 1).text_content() or ""

    async def message_count(self) -> int:
        """Возвращает количество видимых сообщений в ленте."""
        return await self._page.locator(".mx_EventTile_body").count()
