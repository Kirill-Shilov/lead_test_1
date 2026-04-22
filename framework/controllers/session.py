"""
SessionController — управление жизненным циклом пользовательской сессии.

Отвечает за регистрацию, логин и удаление тестового аккаунта.
Используется фикстурами для изоляции тестов: каждый тест получает
свежего пользователя и комнату, которые удаляются после завершения.
"""
from __future__ import annotations

import uuid

import httpx

from framework.models.user import User


class SessionController:
    """
    Управляет созданием и удалением тестовых пользователей через Matrix API.

    Args:
        homeserver: базовый URL homeserver'а (например, http://localhost:8008)
        admin_token: access_token администратора (нужен для деактивации через Admin API)
    """

    def __init__(self, homeserver: str, admin_token: str = "") -> None:
        self._homeserver = homeserver.rstrip("/")
        self._admin_token = admin_token

    async def register_random_user(self) -> User:
        """
        Регистрирует нового пользователя со случайным именем.
        Использует endpoint регистрации без пароля (для тестового сервера).

        Returns:
            User с заполненными user_id, access_token, device_id
        """
        username = f"test_{uuid.uuid4().hex[:8]}"
        password = uuid.uuid4().hex

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._homeserver}/_matrix/client/v3/register",
                json={
                    "username": username,
                    "password": password,
                    "auth": {"type": "m.login.dummy"},  # без капчи на тестовом сервере
                },
            )
            resp.raise_for_status()
            data = resp.json()

        return User(
            user_id=data["user_id"],
            access_token=data["access_token"],
            device_id=data["device_id"],
            homeserver=self._homeserver,
            password=password,
        )

    async def deactivate_user(self, user: User) -> None:
        """
        Деактивирует пользователя через Synapse Admin API.
        Если admin_token не задан — просто разлогинивает (мягкая очистка).

        Args:
            user: пользователь для удаления
        """
        async with httpx.AsyncClient() as client:
            if self._admin_token:
                # Жёсткое удаление через Admin API (Synapse)
                await client.post(
                    f"{self._homeserver}/_synapse/admin/v1/deactivate/{user.user_id}",
                    headers={"Authorization": f"Bearer {self._admin_token}"},
                    json={"erase": True},
                )
            else:
                # Мягкая очистка: просто удаляем токен
                await client.post(
                    f"{self._homeserver}/_matrix/client/v3/logout",
                    headers={"Authorization": f"Bearer {user.access_token}"},
                )
