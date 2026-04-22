# Отчет
Потрачено 4 часа.
Можно много чего еще реализовать, но это ведь тестовое задание. Нет аллюра.
Network controller в реальном проекте будет значительно сложнее выглядеть. Нужно будет что-то вроде chaos mesh.
В целом артефакты моей работы примерно так и выглядят.

# QA Team Lead — Тестовое задание

Ответы на задание QA Team Lead для Matrix-мессенджера (Element-форк, Electron + web + mobile).

---

## Структура репозитория

```
├── answers/                          # Текстовые ответы на задания 1–4
│   ├── 01_audit_and_strategy.md
│   ├── 02_automation_and_ci.md
│   ├── 03_idempotency_concurrency.md
│   └── 04_people_and_process.md
│
├── framework/                        # Тестовый фреймворк
│   ├── models/                       # Датаклассы (User, Room, Message)
│   ├── adapters/                     # MatrixApiAdapter, UiAdapter
│   ├── controllers/                  # NetworkController, SessionController
│   └── fixtures/                     # Pytest-фикстуры
│
├── tests/
│   ├── api/test_idempotency.py       # Задание 3.2: тест гонки при отправке
│   └── e2e/test_send_message.py      # Задание 5: логин → создание комнаты → отправка → проверка
│
├── conftest.py
├── pytest.ini
├── pyproject.toml                    # Зависимости (uv)
├── Makefile
└── .gitlab-ci.yml
```

---

## Быстрый старт

### Требования

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) — менеджер зависимостей
- Docker — для Synapse

### 1. Установить зависимости

```bash
make install
```

### 2. Поднять сервисы

Первый раз (скачать образы и сгенерировать конфиги):

```bash
make services-setup
```

Запустить:

```bash
make services-start
```

После этого доступны:
- Synapse: `http://localhost:8008`
- Element Web: `http://localhost:8080`

### 3. Запустить тесты

```bash
# API-тесты (без браузера)
make test-api

# E2E-тесты (Playwright, headless Chromium)
make test-e2e
```

---

## Все команды

```
make help
```

| Команда | Описание |
|---|---|
| `install` | uv sync + playwright install chromium |
| `lint` | flake8 + mypy |
| `synapse-setup` | Pull образ + сгенерировать конфиг в `./synapse-data` |
| `synapse-start` | Запустить контейнер Synapse на :8008 |
| `synapse-stop` | Остановить контейнер |
| `synapse-logs` | Логи Synapse |
| `element-download` | Скачать Element Web v1.12.15 в /tmp |
| `element-start` | Запустить Element Web на :8080 |
| `element-stop` | Остановить Element Web |
| `services-setup` | = synapse-setup + element-download |
| `services-start` | = synapse-start + element-start |
| `services-stop` | = synapse-stop + element-stop |
| `test-api` | API-тесты |
| `test-e2e` | E2E-тесты |

Переменные:

```bash
make test-e2e HOMESERVER=http://my-server:8008 BASE_URL=http://my-element:8080
make element-download ELEMENT_VER=1.11.0
make synapse-setup SYNAPSE_DATA=/custom/path
```

---

## Архитектура фреймворка

**Adapter pattern** — тест-код не зависит от реализации клиента:

- `framework/adapters/base.py` — `BaseAdapter` Protocol: `login`, `send_message`, `get_messages`, `create_room`, `leave_room`
- `framework/adapters/matrix_api.py` — HTTP через httpx
- `framework/adapters/ui.py` — Playwright (async, без зависимости от sync-фикстур pytest-playwright)

**Session isolation** — `SessionController` регистрирует случайного пользователя перед тестом, деактивирует после. Нулевое пересечение состояний между тестами.

**Network control** — `NetworkController` инжектирует задержки и перехватчики на уровне httpx transport (API) или `page.route()` (UI). Позволяет детерминированно воспроизводить race conditions.

---

## Допущения

1. **Synapse** должен быть с `enable_registration: true` и `enable_registration_without_verification: true`. `make synapse-setup` выставляет это автоматически.

2. **Element Web** `config.json` должен указывать на `http://localhost:8008`. `make element-download` настраивает автоматически.

3. **E2EE-верификационный диалог** не появляется для свежих пользователей (первый логин на новом сервере). Тесты создают пользователей через API перед каждым запуском — проблемы нет.

4. **Admin token** не требуется для базовых тестов. Без него `SessionController` делает мягкую очистку (`/logout`). Для полного удаления — передать `--admin-token`.

---

## Что не реализовано

**E2EE-тесты** — проверка ротации Megolm-сессии требует двух клиентов с полным E2EE-стеком (`matrix-nio` с `libolm` или `matrix-js-sdk`). Выходит за рамки задания по времени.

**Мобильные тесты** — структура в `.gitlab-ci.yml` описана, код не написан. Реализация: `appium-python-client` + те же API-фикстуры для создания пользователей.

**Performance** — нагрузочное тестирование `/sync` при 10k клиентах: `locust` или `k6`.
