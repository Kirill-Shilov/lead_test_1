"""
Задание 3.2 — Тест идемпотентности и конкурентности.

Сценарий: пользователь дважды нажимает «Отправить» подряд.
Первый запрос /send уходит с задержкой (имитация сети),
второй — с тем же txnId (как делает клиент при double-click).

Ожидаем: сервер вернёт один event_id, в истории комнаты — одно сообщение.

Архитектурный комментарий:
    Каждый «клиент» (MatrixApiAdapter) имеет свой NetworkController.
    В этом тесте мы настраиваем контроллер первого адаптера с задержкой,
    а параллельный запрос отправляем через тот же адаптер — это точно
    имитирует гонку внутри одного клиентского процесса.
"""
import asyncio
import uuid

import pytest

from framework.adapters.matrix_api import MatrixApiAdapter
from framework.controllers.network import NetworkController
from framework.models.room import Room
from framework.models.user import User


@pytest.mark.asyncio
async def test_no_duplicate_message_on_double_send(
    matrix_user: User,
    room: Room,
) -> None:
    """
    Проверяем, что при двух параллельных отправках с одним txnId
    в комнате появляется ровно одно сообщение.

    Шаги:
    1. Создаём NetworkController с задержкой на /send (имитация медленной сети)
    2. Запускаем два asyncio-таска с одинаковым txnId одновременно
    3. Проверяем количество сообщений через GET /messages
    """
    # -- Настройка сети --
    nc = NetworkController()
    # Первый запрос к /send будет задержан на 300 мс,
    # чтобы второй запрос успел «обогнать» его в очереди
    nc.delay_route(r"/send/", delay_ms=300)

    # -- Создаём адаптер с задержкой --
    async with MatrixApiAdapter(network_controller=nc) as api:
        await api.login(matrix_user)

        # Один и тот же txnId для обоих запросов — как при double-click
        txn_id = uuid.uuid4().hex
        message_body = f"идемпотентный тест {uuid.uuid4().hex[:6]}"

        # -- Параллельная отправка --
        # asyncio.gather запускает оба корутина одновременно.
        # Первый будет задержан на 300 мс транспортом,
        # второй пройдёт сразу (или будет задержан тоже — оба используют nc).
        results = await asyncio.gather(
            api.send_message(room, message_body, txn_id=txn_id),
            api.send_message(room, message_body, txn_id=txn_id),
            return_exceptions=True,  # не падаем если один из запросов вернул ошибку
        )

        # -- Проверяем event_id --
        # Matrix должен вернуть один и тот же event_id для обоих запросов
        event_ids = {
            r.event_id
            for r in results
            if isinstance(r, object) and hasattr(r, "event_id")
        }
        assert len(event_ids) == 1, (
            f"Ожидали один event_id, получили {len(event_ids)}: {event_ids}"
        )

        # -- Проверяем историю комнаты --
        # Небольшая пауза, чтобы сервер успел обработать оба запроса
        await asyncio.sleep(0.5)

        messages = await api.get_messages(room, limit=20)
        # Фильтруем только наше тестовое сообщение
        our_messages = [m for m in messages if m.body == message_body]

        assert len(our_messages) == 1, (
            f"Обнаружен дубликат сообщения! Найдено {len(our_messages)} "
            f"сообщений с текстом '{message_body}'"
        )


@pytest.mark.asyncio
async def test_different_txn_ids_produce_two_messages(
    matrix_user: User,
    room: Room,
) -> None:
    """
    Граничный случай: два запроса с РАЗНЫМИ txnId должны дать два сообщения.
    Это позитивный тест — убеждаемся, что механизм идемпотентности
    не «схлопывает» разные сообщения.
    """
    async with MatrixApiAdapter() as api:
        await api.login(matrix_user)

        body = "сообщение без дублей"
        txn_id_1 = uuid.uuid4().hex
        txn_id_2 = uuid.uuid4().hex  # другой txnId — другое сообщение

        await asyncio.gather(
            api.send_message(room, body, txn_id=txn_id_1),
            api.send_message(room, body, txn_id=txn_id_2),
        )

        await asyncio.sleep(0.3)
        messages = await api.get_messages(room, limit=20)
        our_messages = [m for m in messages if m.body == body]

        assert len(our_messages) == 2, (
            f"Ожидали 2 сообщения с разными txnId, получили {len(our_messages)}"
        )
