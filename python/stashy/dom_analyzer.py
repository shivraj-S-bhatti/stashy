"""LLM + heuristic DOM analysis for extraction and geospatial signal generation."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from .crawler import build_dom_summary

SYSTEM_PROMPT = """You are an expert web extraction engine for geospatial AI indexing.
Given a simplified DOM, extract a compact JSON payload with this exact shape:
{
  "title": string|null,
  "main_content": string,
  "links": [{"href": string, "text": string}],
  "description": string|null,
  "article_date": string|null,
  "author": string|null,
  "geo_entities": [string],
  "location_hints": [string],
  "vps_relevance": number,
  "reconstruction_relevance": number,
  "recency_signal": number
}
Rules:
- Return JSON only (no markdown).
- vps_relevance, reconstruction_relevance, recency_signal must be floats in [0,1].
- links must be <= 50 items.
- main_content should be concise and readable text.
"""

USER_PROMPT_TEMPLATE = """Analyze and extract structured content from this page.

URL: {url}
DOM summary:
{dom_summary}
"""


def get_llm() -> ChatOpenAI | None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None
    base_url = os.environ.get("LLM_API_BASE")
    model = os.environ.get("LLM_MODEL", "gpt-4o-mini")
    kwargs: dict[str, Any] = {"model": model, "temperature": 0, "api_key": api_key}
    if base_url:
        kwargs["base_url"] = base_url
    return ChatOpenAI(**kwargs)


def _ensure_float_01(value: Any, default: float = 0.0) -> float:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    return max(0.0, min(1.0, f))


def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    links = payload.get("links")
    if not isinstance(links, list):
        links = []
    norm_links = []
    for item in links[:50]:
        if not isinstance(item, dict):
            continue
        href = str(item.get("href") or "").strip()
        text = str(item.get("text") or "").strip()
        if href:
            norm_links.append({"href": href[:2048], "text": text[:220]})

    geo_entities = payload.get("geo_entities")
    if not isinstance(geo_entities, list):
        geo_entities = []
    location_hints = payload.get("location_hints")
    if not isinstance(location_hints, list):
        location_hints = []

    return {
        "title": (str(payload.get("title")).strip()[:500] if payload.get("title") else None),
        "main_content": str(payload.get("main_content") or "")[:12000],
        "links": norm_links,
        "description": (
            str(payload.get("description")).strip()[:500] if payload.get("description") else None
        ),
        "article_date": (
            str(payload.get("article_date")).strip()[:80] if payload.get("article_date") else None
        ),
        "author": (str(payload.get("author")).strip()[:180] if payload.get("author") else None),
        "geo_entities": [str(x)[:120] for x in geo_entities[:25]],
        "location_hints": [str(x)[:120] for x in location_hints[:25]],
        "vps_relevance": _ensure_float_01(payload.get("vps_relevance"), 0.0),
        "reconstruction_relevance": _ensure_float_01(payload.get("reconstruction_relevance"), 0.0),
        "recency_signal": _ensure_float_01(payload.get("recency_signal"), 0.0),
    }


def _extract_links_regex(html: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for m in re.finditer(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        href = m.group(1).strip()[:2048]
        text = re.sub(r"<[^>]+>", " ", m.group(2))
        text = " ".join(text.split())[:220]
        if href:
            out.append({"href": href, "text": text})
        if len(out) >= 50:
            break
    return out


def _fallback_extraction(html: str, url: str) -> tuple[dict[str, Any], float]:
    payload: dict[str, Any] = {
        "title": None,
        "main_content": "",
        "links": [],
        "description": None,
        "article_date": None,
        "author": None,
        "geo_entities": [],
        "location_hints": [],
        "vps_relevance": 0.0,
        "reconstruction_relevance": 0.0,
        "recency_signal": 0.0,
    }

    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE | re.DOTALL)
    if m:
        payload["title"] = m.group(1).strip()[:500]

    m = re.search(
        r'<meta\s+name=["\']description["\'][^>]*content=["\']([^"\']+)["\']',
        html,
        re.IGNORECASE,
    )
    if m:
        payload["description"] = m.group(1).strip()[:500]

    payload["links"] = _extract_links_regex(html)

    text = re.sub(r"<script[^>]*>[\s\S]*?</script>", " ", html, flags=re.IGNORECASE)
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = " ".join(text.split())
    payload["main_content"] = text[:10000]

    combined = f"{url}\n{payload['title'] or ''}\n{payload['description'] or ''}\n{text[:4000]}".lower()

    geo_terms = [
        "map",
        "mapping",
        "geospatial",
        "city",
        "street",
        "vps",
        "localization",
        "positioning",
        "navigation",
        "3d",
        "reconstruction",
        "sfm",
        "mesh",
        "pointcloud",
        "ar",
        "xr",
        "robot",
    ]
    hits = [term for term in geo_terms if term in combined]

    payload["geo_entities"] = hits[:15]
    payload["location_hints"] = re.findall(
        r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){0,2})\b", (payload["main_content"] or "")[:2500]
    )[:10]

    payload["vps_relevance"] = max(0.0, min(1.0, 0.08 * len([h for h in hits if h in {"vps", "localization", "positioning", "ar", "xr"}])))
    payload["reconstruction_relevance"] = max(0.0, min(1.0, 0.08 * len([h for h in hits if h in {"3d", "reconstruction", "sfm", "mesh", "pointcloud"}])))
    payload["recency_signal"] = 0.8 if re.search(r"\b(202[4-9]|203\d)\b", combined) else 0.3

    confidence = 0.67 if payload["main_content"] else 0.45
    return (_normalize_payload(payload), confidence)


def analyze_dom_with_llm(html: str, url: str, max_dom_chars: int = 50000) -> tuple[dict[str, Any], float]:
    llm = get_llm()
    if not llm:
        return _fallback_extraction(html, url)

    dom_summary = build_dom_summary(html, max_chars=max_dom_chars)
    user_content = USER_PROMPT_TEMPLATE.format(dom_summary=dom_summary, url=url)
    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=user_content)]

    response = llm.invoke(messages)
    text = response.content if hasattr(response, "content") else str(response)

    if "```json" in text:
        text = text.split("```json", 1)[1].split("```", 1)[0].strip()
    elif "```" in text:
        text = text.split("```", 1)[1].split("```", 1)[0].strip()

    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = {"raw": text, "parse_error": True}

    normalized = _normalize_payload(payload)

    has_main = bool(normalized.get("main_content"))
    has_links = bool(normalized.get("links"))
    parse_error = bool(payload.get("parse_error"))
    confidence = 0.95 if (has_main and has_links and not parse_error) else 0.62

    return (normalized, confidence)
