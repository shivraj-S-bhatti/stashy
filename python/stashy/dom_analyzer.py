"""LLM-based DOM pattern analysis for high-accuracy extraction across site structures."""
from __future__ import annotations

import json
import os
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .crawler import build_dom_summary

# Default extraction schema: title, main content, links, optional metadata
EXTRACTION_SCHEMA = {
    "title": "string or null",
    "main_content": "string (primary readable text)",
    "links": "array of {href, text}",
    "description": "string or null (meta description or summary)",
    "article_date": "string or null (ISO date if present)",
    "author": "string or null",
}

SYSTEM_PROMPT = """You are an expert at analyzing web page DOM structure to extract content accurately.
Given a simplified DOM (tags with id/class/role/data attributes), infer the best way to describe the page content.
Output valid JSON only, with these keys:
- title: page title or main heading
- main_content: the primary readable body text (concise, no HTML)
- links: list of {href, text} for important links (limit 50)
- description: meta description or short summary if evident
- article_date: publication date in ISO format if present, else null
- author: author if present, else null
Aim for high extraction accuracy; if a field cannot be determined, use null."""

USER_PROMPT_TEMPLATE = """Analyze this DOM structure and extract content as JSON.

DOM (simplified):
{dom_summary}

URL: {url}

Return only valid JSON."""


def get_llm() -> ChatOpenAI | None:
    """Build LLM with optional base URL for compatible APIs. Returns None if no API key."""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    base_url = os.environ.get("LLM_API_BASE")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    kwargs = {"model": model, "temperature": 0, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _fallback_extraction(html: str, url: str) -> tuple[dict[str, Any], float]:
    """Simple regex-based extraction when LLM is not configured."""
    import re
    payload = {"title": None, "main_content": None, "links": [], "description": None, "article_date": None, "author": None}
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.I | re.S)
    if m:
        payload["title"] = m.group(1).strip()[:500]
    m = re.search(r'<meta\s+name=["\']description["\'][^>]*content=["\']([^"\']+)["\']', html, re.I)
    if m:
        payload["description"] = m.group(1).strip()[:500]
    for m in re.finditer(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([^<]*)</a>', html, re.I):
        payload["links"].append({"href": m.group(1)[:2048], "text": m.group(2).strip()[:200]})
        if len(payload["links"]) >= 50:
            break
    # Crude main content: first long text block
    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.I)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    if len(text) > 200:
        payload["main_content"] = text[:10000]
    return (payload, 0.6)


def analyze_dom_with_llm(html: str, url: str, max_dom_chars: int = 50000) -> tuple[dict[str, Any], float]:
    """
    Run LLM DOM pattern analysis on page HTML. Returns (payload dict, confidence 0–1).
    """
    llm = get_llm()
    if not llm:
        return _fallback_extraction(html, url)
    dom_summary = build_dom_summary(html, max_chars=max_dom_chars)
    user_content = USER_PROMPT_TEMPLATE.format(dom_summary=dom_summary, url=url)
    messages = [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=user_content),
    ]
    response = llm.invoke(messages)
    text = response.content if hasattr(response, "content") else str(response)
    # Strip markdown code block if present
    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {"raw": text, "parse_error": True}
    # Heuristic confidence: 1.0 if all main fields present and no parse error
    has_main = isinstance(payload.get("main_content"), str) and len(payload.get("main_content", "")) > 0
    confidence = 0.94 if (has_main and not payload.get("parse_error")) else 0.5
    return (payload, confidence)
