"""
Задание 5 — E2E-тест: логин, создание комнаты, отправка сообщения, проверка в UI.

Тест использует UiAdapter для управления браузером через Playwright
и API-фикстуры для создания пользователя (быстрее и надёжнее, чем через UI).

Предполагает запущенный Element Web на base_url и Synapse на homeserver_url.

Запуск:
    pytest tests/e2e/test_send_message.py --base-url http://localhost:8080 \
        --homeserver http://localhost:8008 --headed
"""
import pytest

from framework.adapters.ui import UiAdapter
from framework.models.room import Room
from framework.models.user import User


@pytest.mark.asyncio
async def test_send_message_appears_in_chat(
    ui_client: UiAdapter,
    matrix_user: User,
    room: Room,
) -> None:
    """
    Полный позитивный сценарий:
    1. Авторизоваться в Element Web
    2. Открыть созданную через API комнату
    3. Отправить текстовое сообщение через UI
    4. Убедиться, что сообщение отображается в ленте
    """
    expected_text = "Привет, это автоматический тест!"

    # Шаг 1: Логин в Element Web
    # Комната уже создана через API (фикстура room),
    # пользователь зарегистрирован (фикстура matrix_user)
    await ui_client.login(matrix_user)

    # Шаг 2: Переходим в нужную комнату
    # Используем прямой переход по room_id через URL
    await ui_client.open_room(room)

    # Шаг 3: Отправляем сообщение через поле ввода
    await ui_client.send_message(room, expected_text)

    # Шаг 4: Проверяем, что сообщение появилось в ленте
    last_text = await ui_client.last_message_text()
    assert last_text == expected_text, (
        f"Ожидали сообщение '{expected_text}', "
        f"в ленте отображается: '{last_text}'"
    )


@pytest.mark.asyncio
async def test_sent_message_count_increases(
    ui_client: UiAdapter,
    matrix_user: User,
    room: Room,
) -> None:
    """
    Проверяем, что после отправки N сообщений их количество в ленте
    увеличивается ровно на N (нет дублей, нет потерь).
    """
    await ui_client.login(matrix_user)
    await ui_client.open_room(room)

    count_before = await ui_client.message_count()

    # Отправляем 3 разных сообщения
    messages_to_send = [
        "Первое тестовое сообщение",
        "Второе тестовое сообщение",
        "Третье тестовое сообщение",
    ]
    for text in messages_to_send:
        await ui_client.send_message(room, text)

    count_after = await ui_client.message_count()

    assert count_after == count_before + len(messages_to_send), (
        f"Ожидали {count_before + len(messages_to_send)} сообщений, "
        f"отображается {count_after}"
    )
