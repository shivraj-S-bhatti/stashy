"""Agentic frontier expansion and geospatial relevance scoring."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlparse, urlunparse
import math
import re


GEO_TERMS = {
    "map",
    "mapping",
    "geospatial",
    "geography",
    "terrain",
    "satellite",
    "imagery",
    "street",
    "city",
    "urban",
    "vps",
    "localization",
    "positioning",
    "ar",
    "xr",
    "robot",
    "robotics",
    "autonomous",
    "drone",
    "navigation",
    "wayfinding",
    "3d",
    "reconstruction",
    "sfm",
    "gaussian",
    "splatting",
    "mesh",
    "pointcloud",
    "coordinate",
    "gis",
    "lidar",
}

NOISE_TERMS = {
    "login",
    "signup",
    "privacy",
    "terms",
    "careers",
    "contact",
    "cookie",
    "advertise",
    "sponsor",
}


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True)
class FrontierCandidate:
    url: str
    geo_score: float
    priority: int
    reason: str


@dataclass(frozen=True)
class GeoSignals:
    geo_term_density: float
    freshness_signal: float
    structured_data_signal: float
    link_quality_signal: float

    @property
    def aggregate_score(self) -> float:
        score = (
            self.geo_term_density * 0.42
            + self.freshness_signal * 0.18
            + self.structured_data_signal * 0.22
            + self.link_quality_signal * 0.18
        )
        return _clamp(score)


def canonicalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"}:
        return ""
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    cleaned = urlunparse((parsed.scheme, netloc, path, "", parsed.query, ""))
    return cleaned


def _keyword_hits(text: str, words: set[str]) -> float:
    lowered = text.lower()
    if not lowered:
        return 0.0
    hits = sum(1 for word in words if word in lowered)
    return hits / max(1, len(words) * 0.35)


def compute_geo_signals(url: str, payload: dict[str, Any]) -> GeoSignals:
    main_content = str(payload.get("main_content") or "")
    title = str(payload.get("title") or "")
    description = str(payload.get("description") or "")
    blob = f"{url}\n{title}\n{description}\n{main_content[:5000]}"

    geo_density = _clamp(_keyword_hits(blob, GEO_TERMS) * 3.4)
    freshness_signal = 0.0
    if payload.get("article_date"):
        freshness_signal = 0.65
    if re.search(r"\b(202[4-9]|203\d)\b", blob):
        freshness_signal = max(freshness_signal, 0.8)

    structured_signal = 0.0
    if "application/ld+json" in main_content.lower():
        structured_signal = 0.7
    if any(k in main_content.lower() for k in ("schema.org", "geo", "latitude", "longitude")):
        structured_signal = max(structured_signal, 0.6)

    links = payload.get("links") or []
    strong = 0
    for link in links:
        href = str(link.get("href") or "")
        text = str(link.get("text") or "")
        if any(term in f"{href} {text}".lower() for term in GEO_TERMS):
            strong += 1
    quality_signal = _clamp(strong / max(1, min(len(links), 15)))

    return GeoSignals(
        geo_term_density=geo_density,
        freshness_signal=freshness_signal,
        structured_data_signal=structured_signal,
        link_quality_signal=quality_signal,
    )


def extract_links(html: str, base_url: str, max_links: int = 80) -> list[dict[str, str]]:
    seen: set[str] = set()
    out: list[dict[str, str]] = []
    if not html:
        return out

    for m in re.finditer(
        r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>',
        html,
        re.IGNORECASE | re.DOTALL,
    ):
        href_raw = m.group(1).strip()
        anchor_html = m.group(2)
        anchor_text = re.sub(r"<[^>]+>", " ", anchor_html)
        anchor_text = " ".join(anchor_text.split())[:220]
        abs_url = canonicalize_url(urljoin(base_url, href_raw))
        if not abs_url or abs_url in seen:
            continue
        seen.add(abs_url)
        out.append({"href": abs_url, "text": anchor_text})
        if len(out) >= max_links:
            break
    return out


def _host_affinity(parent_url: str, candidate_url: str) -> float:
    parent_host = urlparse(parent_url).netloc.lower()
    cand_host = urlparse(candidate_url).netloc.lower()
    if not parent_host or not cand_host:
        return 0.0
    if parent_host == cand_host:
        return 1.0
    if parent_host.split(".")[-2:] == cand_host.split(".")[-2:]:
        return 0.78
    return 0.45


def score_frontier_candidate(parent_url: str, href: str, text: str = "") -> tuple[float, str]:
    blob = f"{href} {text}".lower()
    geo = _clamp(_keyword_hits(blob, GEO_TERMS) * 3.7)
    noise = _clamp(_keyword_hits(blob, NOISE_TERMS) * 2.6)
    depth_penalty = 0.0
    path = urlparse(href).path
    slash_count = path.count("/")
    if slash_count > 5:
        depth_penalty = min(0.28, (slash_count - 5) * 0.05)

    host = _host_affinity(parent_url, href)
    score = geo * 0.62 + host * 0.28 + (1.0 - noise) * 0.10 - depth_penalty
    score = _clamp(score)

    if geo > 0.7:
        reason = "geo-dense"
    elif host > 0.9:
        reason = "host-affinity"
    elif noise > 0.3:
        reason = "likely-noise"
    else:
        reason = "explore"
    return score, reason


def frontier_candidates(
    *,
    parent_url: str,
    payload: dict[str, Any],
    html: str,
    current_depth: int,
    max_depth: int,
    max_links: int,
    page_geo_score: float,
) -> list[FrontierCandidate]:
    if current_depth >= max_depth:
        return []

    links: list[dict[str, str]] = []
    payload_links = payload.get("links") or []
    for link in payload_links:
        href = canonicalize_url(str(link.get("href") or ""))
        if not href:
            continue
        text = str(link.get("text") or "")[:220]
        links.append({"href": href, "text": text})

    if len(links) < max_links // 2:
        links.extend(extract_links(html, parent_url, max_links=max_links))

    dedup: dict[str, str] = {}
    for link in links:
        href = canonicalize_url(link.get("href", ""))
        if not href:
            continue
        if href not in dedup:
            dedup[href] = link.get("text", "")

    out: list[FrontierCandidate] = []
    for href, text in dedup.items():
        score, reason = score_frontier_candidate(parent_url, href, text)
        blended_score = _clamp(score * 0.72 + page_geo_score * 0.28)
        priority = int(math.ceil(blended_score * 100.0)) + max(0, 20 - current_depth * 6)
        out.append(
            FrontierCandidate(
                url=href,
                geo_score=blended_score,
                priority=priority,
                reason=reason,
            )
        )

    out.sort(key=lambda item: (item.geo_score, item.priority), reverse=True)
    return out[:max_links]
