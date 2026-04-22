"""
Корневой conftest.py — точка входа pytest.

Подключает все фикстуры из framework/fixtures/ и регистрирует
CLI-опции для передачи конфигурации тестового окружения.
"""
import pytest

# Регистрируем все фикстуры из обеих групп
pytest_plugins = [
    "framework.fixtures.api",
    "framework.fixtures.ui",
]


# ---------------------------------------------------------------------------
# CLI-опции и конфигурация окружения
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    """Добавляет CLI-аргументы для настройки тестового окружения."""
    parser.addoption(
        "--homeserver",
        default="http://localhost:8008",
        help="URL Matrix homeserver'а (по умолчанию: локальный Synapse)",
    )
    parser.addoption(
        "--admin-token",
        default="",
        help="Access token администратора (для деактивации пользователей)",
    )


# ---------------------------------------------------------------------------
# Фикстуры для передачи опций в SessionController и UiAdapter
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def homeserver_url(request: pytest.FixtureRequest) -> str:
    """URL homeserver'а из CLI или переменной окружения."""
    return request.config.getoption("--homeserver")


@pytest.fixture(scope="session")
def admin_token(request: pytest.FixtureRequest) -> str:
    """Admin token для управления пользователями через Synapse Admin API."""
    return request.config.getoption("--admin-token")

# base_url fixture и --base-url опция предоставляются pytest-base-url (зависимость pytest-playwright)
