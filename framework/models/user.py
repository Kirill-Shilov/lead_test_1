"""
Модель пользователя Matrix.
Используется во всех адаптерах и фикстурах как единый тип данных.
"""
from dataclasses import dataclass


@dataclass
class User:
    """Зарегистрированный пользователь Matrix."""
    user_id: str           # полный MXID, например @test_abc:matrix.org
    access_token: str      # токен для Bearer-авторизации
    device_id: str         # идентификатор устройства (нужен для E2EE)
    homeserver: str = "http://localhost:8008"  # базовый URL homeserver'а
    password: str = ""     # пароль (нужен UiAdapter для логина через форму)

    @property
    def localpart(self) -> str:
        """Локальная часть MXID без @ и домена."""
        return self.user_id.split(":")[0].lstrip("@")
