# Задание 3: Тестирование идемпотентности и конкурентности

---

## 3.1 Сценарий тестирования: гонка при двойном нажатии «Отправить»

### Контекст

Matrix Client-Server API гарантирует идемпотентность отправки через `txnId`:

```
PUT /_matrix/client/v3/rooms/{roomId}/send/m.room.message/{txnId}
```

Если клиент отправит два запроса с одинаковым `txnId`, сервер вернёт один и тот же `event_id` и не создаст дубликат. Однако **клиент может создать дубликат в UI** до получения ответа от сервера:

1. Пользователь нажимает «Отправить» → клиент добавляет «pending» сообщение в UI с временным ID
2. Первый запрос ушёл на сервер, но застрял (медленная сеть, 400ms задержка)
3. Пользователь нажимает «Отправить» снова → клиент генерирует тот же `txnId` (или второй «pending» с новым ID)
4. Второй запрос уходит на сервер, сервер видит тот же `txnId`, возвращает тот же `event_id`
5. **Баг**: клиент теперь показывает два «pending» сообщения, а когда приходит ответ — непонятно, какое из них «подтверждённое»

### Шаги сценария

```
Предусловия:
  - Зарегистрированный пользователь
  - Созданная комната
  - Задержка первого /send запроса на 400ms (имитация плохой сети)

Шаги:
  1. Перехватить запросы на /_matrix/client/v3/rooms/.../send/...
  2. Добавить задержку 400ms к первому запросу
  3. Параллельно запустить два запроса с одинаковым txnId
  4. Дождаться завершения обоих запросов
  5. Получить историю комнаты через GET /messages

Ожидаемый результат:
  - Оба запроса вернули одинаковый event_id
  - В истории комнаты ровно одно сообщение с данным текстом
  - В UI (если проверяем E2E): одна плитка сообщения, не две

Граничные случаи:
  - Второй запрос приходит ДО первого (первый задержан дольше)
  - Первый запрос завершается с ошибкой 5xx, второй — успешно
  - Оба запроса завершаются с ошибкой (нет дублей, нет сообщения)
```

---

## 3.2 Код автотеста

Полный рабочий код находится в `tests/api/test_idempotency.py`. Ниже — детальная аннотация логики.

### Ядро теста (с пояснениями)

```python
import asyncio
import uuid

import httpx
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
    Гонка при двойном нажатии «Отправить».

    Архитектура теста:
      - NetworkController задерживает первый /send на 300ms
      - asyncio.gather запускает два корутина одновременно
      - Оба используют один txnId (как реальный клиент при double-click)
      - Проверяем: один event_id, одно сообщение в истории
    """

    # ---------------------------------------------------------------
    # 1. Настраиваем сеть: задержка первого запроса к /send
    # ---------------------------------------------------------------
    nc = NetworkController()
    # Паттерн соответствует: /rooms/.../send/m.room.message/<txnId>
    nc.delay_route(r"/send/m\.room\.message/", delay_ms=300)

    # ---------------------------------------------------------------
    # 2. Создаём адаптер с задержкой, авторизуемся
    # ---------------------------------------------------------------
    async with MatrixApiAdapter(network_controller=nc) as api:
        await api.login(matrix_user)

        # Один txnId для обоих запросов — ключевое условие теста
        txn_id = uuid.uuid4().hex
        body = f"двойная отправка {uuid.uuid4().hex[:6]}"

        # ---------------------------------------------------------------
        # 3. Параллельная отправка — имитация double-click
        # ---------------------------------------------------------------
        # asyncio.gather запускает оба корутина в одном event loop.
        # Первый запрос будет задержан транспортом на 300ms,
        # второй может уйти на сервер раньше.
        # return_exceptions=True: не прерываемся если один из них упал.
        results = await asyncio.gather(
            api.send_message(room, body, txn_id=txn_id),
            api.send_message(room, body, txn_id=txn_id),
            return_exceptions=True,
        )

        # ---------------------------------------------------------------
        # 4. Проверяем event_id — должен быть один
        # ---------------------------------------------------------------
        # Matrix возвращает одинаковый event_id для повторного txnId.
        # Если event_id разные — значит сервер создал дубликат.
        successful = [r for r in results if isinstance(r, object)
                      and hasattr(r, "event_id")]
        event_ids = {r.event_id for r in successful}

        assert len(event_ids) == 1, (
            f"Ожидался один event_id (идемпотентность), "
            f"получили {len(event_ids)}: {event_ids}"
        )

        # ---------------------------------------------------------------
        # 5. Проверяем историю комнаты через API
        # ---------------------------------------------------------------
        # Небольшая пауза: сервер должен закоммитить оба запроса
        await asyncio.sleep(0.5)

        messages = await api.get_messages(room, limit=20)
        our = [m for m in messages if m.body == body]

        assert len(our) == 1, (
            f"В истории комнаты {len(our)} сообщений с текстом '{body}', "
            f"ожидалось 1. Дубликат попал в хранилище."
        )
```

### Вариант с UI-проверкой (E2E)

```python
@pytest.mark.asyncio
async def test_no_duplicate_in_ui_on_double_send(
    ui_client,        # UiAdapter с Playwright
    matrix_user: User,
    room: Room,
    ui_network_controller: NetworkController,
) -> None:
    """
    То же самое, но проверяем UI: в ленте должна быть одна плитка.

    NetworkController привязывается к Playwright page.route(),
    задерживая запросы к /send на уровне браузера.
    """
    # Задержка на уровне браузера (через page.route)
    ui_network_controller.delay_route(r"/send/m\.room\.message/", delay_ms=400)

    await ui_client.login(matrix_user)
    await ui_client.open_room(room)

    body = f"ui двойная отправка {uuid.uuid4().hex[:6]}"
    composer = ui_client._page.locator(
        ".mx_SendMessageComposer [contenteditable='true']"
    )

    # Вводим текст
    await composer.fill(body)

    # Эмулируем double-click: два нажатия Enter без паузы
    await composer.press("Enter")
    await composer.press("Enter")  # второе нажатие — пока первый запрос в полёте

    # Ждём стабилизации ленты (оба запроса завершились)
    await ui_client._page.wait_for_timeout(1000)

    # Считаем плитки с нашим текстом в ленте
    tiles = ui_client._page.locator(f".mx_EventTile_body:has-text('{body}')")
    count = await tiles.count()

    assert count == 1, (
        f"В UI отображается {count} сообщений с текстом '{body}'. "
        f"Дубликат виден пользователю."
    )
```

---

## 3.3 Метрика для отслеживания дублей в продакшене

### Метрика: `duplicate_message_rate`

**Определение:**
```
duplicate_message_rate = количество_дублей_за_период / общее_число_отправленных_сообщений
```

**Как считать:**

Matrix-клиент логирует каждую отправку с `txnId` и полученным `event_id`. Если два разных `txnId` породили одинаковый текст в одной комнате в течение 1 секунды — потенциальный дубликат. Если один `txnId` получил два разных `event_id` (дефект сервера) — гарантированный дубликат.

**Структурированный лог клиента:**
```json
{
  "event": "message_sent",
  "room_id": "!abc:matrix.org",
  "txn_id": "a1b2c3",
  "event_id": "$xyz:matrix.org",
  "timestamp": 1714000000000,
  "attempt": 1
}
```

**Детектор дублей (server-side):**
```python
# Агрегация в Grafana/ClickHouse
SELECT
  date_trunc('hour', timestamp) AS hour,
  COUNT(*) FILTER (WHERE attempt > 1 AND event_id = prev_event_id) AS duplicates,
  COUNT(*) AS total,
  duplicates::float / total AS duplicate_rate
FROM message_send_log
GROUP BY 1
```

**Алертинг:**
- Порог: `duplicate_message_rate > 0.001` (0.1%) за скользящие 15 минут
- Алерт в Slack/PagerDuty
- Dashboard в Grafana: timeseries + аномалии

**Почему именно такой порог:**
- При 10 000 клиентах и 100 сообщениях в день на клиента = 1 млн сообщений/день
- 0.1% = 1 000 дублей в день — это уже заметно пользователям и требует реакции
- 0% недостижим (есть единичные краши клиента), но > 1% = системная проблема
