"""One shared Chromium instance with a tab per source."""

from __future__ import annotations

from playwright.sync_api import sync_playwright


class BrowserHub:
    def __init__(self, headless: bool = False, locale: str = "en-US"):
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=headless)
        self._ctx = self._browser.new_context(locale=locale)

    def new_page(self):
        return self._ctx.new_page()

    def close(self):
        self._ctx.close()
        self._browser.close()
        self._pw.stop()
