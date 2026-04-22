"""
Pytest-фикстуры для API-тестов.

Каждый тест получает изолированного пользователя и комнату,
которые создаются перед тестом и удаляются после.
"""
from __future__ import annotations

from typing import AsyncGenerator

import pytest
import pytest_asyncio

from framework.adapters.matrix_api import MatrixApiAdapter
from framework.controllers.network import NetworkController
from framework.controllers.session import SessionController
from framework.models.room import Room
from framework.models.user import User


# ---------------------------------------------------------------------------
# Вспомогательная фикстура: SessionController (singleton на сессию)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def session_ctrl(homeserver_url: str, admin_token: str) -> SessionController:
    """
    Один SessionController на всю тестовую сессию.
    homeserver_url и admin_token берутся из pytest.ini или CLI-опций.
    """
    return SessionController(homeserver=homeserver_url, admin_token=admin_token)


# ---------------------------------------------------------------------------
# Пользователь — изолирован на каждый тест
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def matrix_user(session_ctrl: SessionController) -> AsyncGenerator[User, None]:
    """
    Создаёт случайного пользователя перед тестом, удаляет после.
    Обеспечивает полную изоляцию: тесты не пересекаются по аккаунтам.
    """
    user = await session_ctrl.register_random_user()
    yield user
    # Очистка: деактивируем пользователя после завершения теста
    await session_ctrl.deactivate_user(user)


# ---------------------------------------------------------------------------
# Адаптер — создаётся под конкретного пользователя
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def matrix_api(
    matrix_user: User,
    network_controller: NetworkController,
) -> AsyncGenerator[MatrixApiAdapter, None]:
    """
    MatrixApiAdapter, авторизованный под matrix_user.
    NetworkController инжектируется отдельно — тест может менять сеть.
    """
    adapter = MatrixApiAdapter(network_controller=network_controller)
    await adapter.login(matrix_user)
    yield adapter
    await adapter.aclose()


# ---------------------------------------------------------------------------
# NetworkController — один на тест, сбрасывается автоматически
# ---------------------------------------------------------------------------

@pytest.fixture
def network_controller() -> NetworkController:
    """
    Свежий NetworkController для каждого теста.
    Тест может добавлять задержки/перехваты, после теста всё сбрасывается.
    """
    return NetworkController()


# ---------------------------------------------------------------------------
# Комната — создаётся и удаляется вместе с тестом
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def room(
    matrix_api: MatrixApiAdapter,
    matrix_user: User,
) -> AsyncGenerator[Room, None]:
    """
    Создаёт приватную комнату для теста, покидает её после.
    """
    r = await matrix_api.create_room(name="test-room", is_private=True)
    yield r
    # Покидаем комнату после теста (сервер удалит пустую комнату)
    await matrix_api.leave_room(r)
