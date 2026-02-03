"""Playwright-based page loader and DOM capture for the agentic crawler."""
from __future__ import annotations

import asyncio
from typing import Any

from playwright.async_api import async_playwright, Browser, Page, BrowserContext, TimeoutError as PlaywrightTimeout

# Default timeout and viewport for consistent DOM
DEFAULT_TIMEOUT_MS = 30000
DEFAULT_VIEWPORT = {"width": 1280, "height": 720}
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (compatible; Stashy/1.0; +https://github.com/stashy)"
)


async def get_page_html(
    url: str,
    *,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
    user_agent: str = DEFAULT_USER_AGENT,
    wait_until: str = "domcontentloaded",
) -> tuple[str | None, int | None, str | None]:
    """
    Load URL with Playwright and return (html, status_code, content_type).
    On failure returns (None, status_code_or_0, None).
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context(
                user_agent=user_agent,
                viewport=DEFAULT_VIEWPORT,
                ignore_https_errors=True,
            )
            page = await context.new_page()
            await page.set_default_timeout(timeout_ms)
            response = await page.goto(url, wait_until=wait_until, timeout=timeout_ms)
            status = response.status if response else None
            content_type = None
            if response and response.headers.get("content-type"):
                content_type = response.headers["content-type"].split(";")[0].strip()
            html = await page.content()
            return (html, status, content_type)
        except PlaywrightTimeout:
            return (None, 0, None)
        except Exception:
            return (None, 0, None)
        finally:
            await browser.close()


def _build_dom_summary(html: str, max_chars: int = 50000) -> str:
    """
    Build a compact DOM summary for the LLM: tag structure and key attributes,
    truncating very large pages to stay within context limits.
    """
    import re
    # Strip scripts and styles to reduce noise
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.I)
    # Keep tag names and important attributes (id, class, data-*, role)
    def simplify_tag(m):
        tag = m.group(1).lower()
        rest = m.group(2) or ""
        attrs = []
        for attr in ("id", "class", "role", "data-testid", "itemprop", "itemtype"):
            ma = re.search(rf'\b{attr}\s*=\s*["\']([^"\']*)["\']', rest, re.I)
            if ma:
                attrs.append(f'{attr}="{ma.group(1)[:80]}"')
        attr_str = " " + " ".join(attrs) if attrs else ""
        return f"<{tag}{attr_str}>"
    text = re.sub(r"<(\w+)([^>]*)>", simplify_tag, text)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n... [truncated]"
    return text


def build_dom_summary(html: str, max_chars: int = 50000) -> str:
    """Public wrapper for DOM summary used by the LLM analyzer."""
    return _build_dom_summary(html, max_chars)
