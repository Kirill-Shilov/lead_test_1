"""
Pytest-фикстуры для E2E UI-тестов (Playwright).

Использует async_playwright() напрямую чтобы избежать конфликта event loop
между pytest-playwright (sync фикстуры) и pytest-asyncio (asyncio_mode=auto).
"""
from __future__ import annotations

from typing import AsyncGenerator

import pytest_asyncio
from playwright.async_api import async_playwright

from framework.adapters.ui import UiAdapter
from framework.controllers.network import NetworkController
from framework.models.user import User

# Импортируем API-фикстуры для создания пользователей и комнат через API
# (быстрее и надёжнее, чем делать это через UI)
from framework.fixtures.api import matrix_user, session_ctrl, room  # noqa: F401


# ---------------------------------------------------------------------------
# UiAdapter — запускает браузер внутри того же asyncio event loop
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def ui_client(
    matrix_user: User,
    base_url: str,
) -> AsyncGenerator[UiAdapter, None]:
    """
    UiAdapter со своим браузером (chromium headless).
    Браузер живёт ровно один тест и закрывается в teardown.
    """
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        adapter = UiAdapter(
            page=page,
            base_url=base_url or "http://localhost:8080",
        )
        yield adapter
        await browser.close()
