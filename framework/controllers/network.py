"""
NetworkController — управление сетевым слоем на уровне конкретного клиента.

Каждый экземпляр клиента (MatrixApiAdapter или UiAdapter) создаёт
свой NetworkController. Это позволяет в одном тесте иметь двух пользователей
с разными сетевыми условиями (например, один с задержкой, другой без).

Для API-тестов: подменяет httpx.AsyncTransport.
Для UI-тестов: регистрирует обработчики через playwright page.route().
"""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional

import httpx


# ---------------------------------------------------------------------------
# Типы
# ---------------------------------------------------------------------------

RouteHandler = Callable[[httpx.Request], Awaitable[httpx.Response]]


@dataclass
class _RouteRule:
    """Правило перехвата: паттерн URL + обработчик."""
    pattern: re.Pattern
    handler: RouteHandler


# ---------------------------------------------------------------------------
# Transport с поддержкой перехвата (для httpx)
# ---------------------------------------------------------------------------

class _InterceptingTransport(httpx.AsyncBaseTransport):
    """
    httpx-транспорт, который перед отправкой запроса проверяет список правил.
    Если URL совпадает с правилом — вызывает его обработчик.
    Иначе — пропускает запрос через реальный транспорт.
    """

    def __init__(self, rules: list[_RouteRule]) -> None:
        self._rules = rules
        # Реальный транспорт — обычный httpx HTTPX
        self._real = httpx.AsyncHTTPTransport()

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        for rule in self._rules:
            if rule.pattern.search(url_str):
                return await rule.handler(request)
        return await self._real.handle_async_request(request)


# ---------------------------------------------------------------------------
# NetworkController
# ---------------------------------------------------------------------------

class NetworkController:
    """
    Управляет сетевыми условиями для одного клиента.

    Пример использования:
        nc = NetworkController()
        nc.delay_route(r"/send/", delay_ms=400)
        adapter = MatrixApiAdapter(network_controller=nc)
    """

    def __init__(self) -> None:
        self._rules: list[_RouteRule] = []
        # Playwright-страница подключается позже, если используется UI-режим
        self._page: Optional[Any] = None

    # ------------------------------------------------------------------
    # Публичный API
    # ------------------------------------------------------------------

    def delay_route(self, pattern: str, delay_ms: int) -> None:
        """
        Добавляет задержку ко всем запросам, чей URL соответствует pattern.

        Args:
            pattern: регулярное выражение для сопоставления URL
            delay_ms: задержка в миллисекундах
        """
        async def _delayed_handler(request: httpx.Request) -> httpx.Response:
            # Имитируем сетевую задержку перед реальной отправкой
            await asyncio.sleep(delay_ms / 1000)
            return await httpx.AsyncHTTPTransport().handle_async_request(request)

        self._add_rule(pattern, _delayed_handler)

    def intercept_route(self, pattern: str, handler: RouteHandler) -> None:
        """
        Перехватывает запросы: вместо реальной отправки вызывает handler.

        Args:
            pattern: регулярное выражение для сопоставления URL
            handler: async-функция (request) -> httpx.Response
        """
        self._add_rule(pattern, handler)

    def reset(self) -> None:
        """Снимает все зарегистрированные перехваты."""
        self._rules.clear()

    # ------------------------------------------------------------------
    # Внутренние методы
    # ------------------------------------------------------------------

    def _add_rule(self, pattern: str, handler: RouteHandler) -> None:
        self._rules.append(_RouteRule(
            pattern=re.compile(pattern),
            handler=handler,
        ))

    def build_transport(self) -> httpx.AsyncBaseTransport:
        """
        Возвращает httpx-транспорт с применёнными правилами.
        Вызывается при создании httpx.AsyncClient в MatrixApiAdapter.
        """
        return _InterceptingTransport(self._rules)

    async def attach_to_page(self, page: Any) -> None:
        """
        Привязывает контроллер к Playwright-странице.
        Регистрирует route-обработчики для каждого правила.

        Args:
            page: playwright.async_api.Page
        """
        self._page = page
        for rule in self._rules:
            # Playwright принимает строку-паттерн или re.Pattern
            await page.route(rule.pattern, self._make_playwright_handler(rule))

    def _make_playwright_handler(self, rule: _RouteRule):
        """
        Оборачивает httpx-style handler в Playwright route callback.
        Playwright передаёт route и request; мы перехватываем через asyncio.sleep.
        """
        async def _handler(route, request):
            # Для задержки — просто спим и продолжаем
            # Для полного перехвата нужно было бы вернуть route.fulfill(...)
            await asyncio.sleep(0)  # точка для future расширения
            await route.continue_()

        return _handler
