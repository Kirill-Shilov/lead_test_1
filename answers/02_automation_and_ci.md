# Задание 2: Стратегия автоматизации и CI/CD

---

## 2.1 Выбор фреймворка и языка

### Выбор: Python + Playwright (web/desktop) + Appium (mobile)

**Почему Python:**
- QA-команды традиционно сильнее в Python, чем в TypeScript — ниже порог входа для нового автоматизатора
- `pytest` — зрелая экосистема с богатым набором плагинов (`pytest-asyncio`, `pytest-rerunfailures`, `pytest-html`, `allure-pytest`)
- `httpx` с async-поддержкой идеально ложится на Matrix API, который по своей природе асинхронен
- Датаклассы Python нативно поддерживают неизменяемые модели данных без лишнего бойлерплейта

**Почему Playwright (не Cypress, не Selenium):**

| Критерий | Playwright | Cypress | Selenium |
|---|---|---|---|
| Поддержка Electron | ✅ Нативная (launch Electron через `playwright.launch()`) | ❌ Нет | ⚠️ Через ChromeDriver, нестабильно |
| Auto-wait | ✅ Встроен | ✅ Встроен | ❌ Ручные ожидания |
| Network interception | ✅ `page.route()` | ✅ `cy.intercept()` | ❌ Только через proxy |
| Параллельность | ✅ Встроена | ⚠️ Требует Cypress Cloud | ✅ Grid |
| Трейс-вьювер | ✅ `playwright show-trace` | ❌ | ❌ |
| Python API | ✅ Первоклассный | ❌ Только JS | ✅ |

Playwright выигрывает за счёт нативной поддержки Electron и мощного инструментария отладки (трейсы, видео, скриншоты из коробки).

**Почему Appium для мобилок (не Detox):**
- Detox работает только с React Native — мобильный клиент на базе Element iOS/Android не является RN-приложением
- Appium поддерживает нативные приложения на iOS (XCUITest) и Android (UIAutomator2)
- Единый Python-код для обеих платформ через `appium-python-client`

---

## 2.2 Структура тестового проекта

```
matrix-qa/
├── framework/                   # Ядро фреймворка (не содержит тест-кейсов)
│   ├── models/                  # Датаклассы — единые типы данных
│   │   ├── user.py              # @dataclass User
│   │   ├── room.py              # @dataclass Room
│   │   └── message.py           # @dataclass Message
│   │
│   ├── adapters/                # Реализации протокола BaseAdapter
│   │   ├── base.py              # Protocol/ABC (интерфейс)
│   │   ├── matrix_api.py        # HTTP API-адаптер (httpx)
│   │   └── ui.py                # Playwright UI-адаптер
│   │
│   ├── controllers/             # Управление инфраструктурой теста
│   │   ├── network.py           # NetworkController — перехват, задержки
│   │   └── session.py           # SessionController — жизненный цикл юзера
│   │
│   └── fixtures/                # Pytest-фикстуры, реиспользуемые между тестами
│       ├── api.py               # matrix_user, room, matrix_api, network_controller
│       └── ui.py                # ui_client, browser_page
│
├── tests/
│   ├── api/                     # Тесты через Matrix HTTP API
│   │   ├── test_idempotency.py  # Задание 3.2
│   │   └── test_sync.py         # Тесты /sync, пагинация, timeline
│   │
│   ├── e2e/                     # E2E через Playwright (браузер)
│   │   ├── test_send_message.py # Задание 5
│   │   ├── test_login.py
│   │   └── test_e2ee.py         # Проверка E2EE UI-индикаторов
│   │
│   └── mobile/                  # Appium-тесты (будущее)
│       └── test_send_message_ios.py
│
├── conftest.py                  # Корневой: регистрирует fixtures, CLI-опции
├── pytest.ini                   # asyncio_mode, маркеры, таймауты
├── requirements.txt
└── .gitlab-ci.yml
```

**Принципы архитектуры:**

- **Адаптеры изолируют протокол**: тест пишется через `BaseAdapter`, не зная, API это или UI. Замена адаптера = смена канала тестирования без переписывания теста.
- **NetworkController — один на клиент**: позволяет в одном тесте иметь Алису с нормальной сетью и Боба с задержкой.
- **Датаклассы вместо словарей**: тест не работает с сырым JSON. `message.body` вместо `data["content"]["body"]` — нет опечаток, есть автодополнение.
- **Фикстуры управляют lifecycle**: создание и удаление пользователей/комнат через `yield`-фикстуры, независимо от результата теста.

---

## 2.3 Внедрение автотестов в GitLab CI

### Стадии пайплайна

```
lint → unit → e2e:web → e2e:desktop → e2e:mobile → pages (отчёт)
```

**Детали каждой стадии:**

**`lint`** (2–3 мин):
- `flake8` + `mypy` — статический анализ
- Блокирует MR при ошибках

**`unit`** (3–5 мин):
- Тесты без браузера и сервера (моки через `unittest.mock`)
- Проверяет логику адаптеров, парсинг ответов

**`e2e:web`** (10–15 мин):
- Docker-сервисы: `matrixdotorg/synapse` + `vectorim/element-web`
- Параллельный запуск: `parallel: 3` в GitLab CI — фреймворк разделяет тесты автоматически
- Smoke (2–3 мин) — при каждом push
- Full suite (15 мин) — только на MR и `main`

**`e2e:desktop`** (15–20 мин):
- Запускается только при изменениях в `desktop-client/**`
- Требует Linux-раннера с Xvfb для headless Electron

**`e2e:mobile`** (30–40 мин):
- macOS-раннер с Xcode (iOS) / Android emulator
- `allow_failure: true` — не блокирует релиз (нестабильная инфраструктура)
- Запускается только на `main`

### Параллельный запуск

```yaml
e2e:web:full:
  parallel: 3  # GitLab создаёт 3 джоба, pytest-split делит тесты
```

Используем `pytest-split` (или встроенный `--splits N --group M`): каждый из 3 воркеров получает свою группу тестов. Общее время сокращается в ~3 раза.

### Артефакты

```yaml
artifacts:
  when: always          # собираем даже при падении
  expire_in: 7 days
  paths:
    - reports/          # JUnit XML + HTML
    - test-results/     # Playwright трейсы, скриншоты, видео
  reports:
    junit: reports/junit.xml  # GitLab парсит и показывает в MR
```

Playwright автоматически сохраняет:
- **Скриншот** — при падении (`--screenshot=only-on-failure`)
- **Видео** — при падении (`--video=retain-on-failure`)
- **Трейс** — при падении (`--tracing=retain-on-failure`), открывается через `playwright show-trace`

---

## 2.4 Борьба с флаки-тестами

### Корень проблемы: асинхронность Matrix

Matrix — асинхронная система. Сообщение отправлено — это не значит, что оно уже в `/sync`. Классическая ошибка новичков: `time.sleep(1)` вместо ожидания конкретного события.

### Конкретные механизмы

**1. Семантические ожидания вместо `sleep`:**
```python
# ❌ Плохо — произвольная пауза
await asyncio.sleep(2)
assert await page.locator(".mx_EventTile").count() == 1

# ✅ Хорошо — ждём конкретный сетевой ответ
async with page.expect_response("**/messages**") as resp:
    await ui_client.send_message("hello")
await resp.value  # блокируемся до получения ответа
assert await page.locator(".mx_EventTile").count() == 1
```

**2. Изоляция тестов — уникальные аккаунты и комнаты:**
- Каждый тест получает свежего пользователя (через `SessionController.register_random_user()`)
- Каждый тест работает в своей комнате
- Нет shared state → нет гонок между тестами

**3. NetworkController.reset() в `teardown`:**
```python
@pytest.fixture
def network_controller():
    nc = NetworkController()
    yield nc
    nc.reset()  # снимаем все перехваты после теста
```

**4. Ретраи только в CI, не локально:**
```ini
# pytest.ini
# addopts = --reruns=2  # НЕ включаем глобально
```
```yaml
# .gitlab-ci.yml
script:
  - pytest ... --reruns=2  # только в CI
```
Локально флаки должны быть видны сразу — не скрываем ретраями.

**5. Карантин для стабильно нестабильных тестов:**
```python
@pytest.mark.flaky(reruns=3, reason="Matrix /sync нестабилен на CI-сервере")
async def test_sync_after_reconnect():
    ...
```
Карантинные тесты — в отдельный suite, не блокируют MR, алерт в Slack при каждом падении.

**6. Детерминированные тестовые данные:**
- Уникальные тела сообщений через `uuid4()` — никогда нет конфликта с чужим тестом
- Фиксированные таймауты через `pytest-timeout` — тест не висит вечно при зависании сервера
