from __future__ import annotations

import unittest

from stashy.frontier import canonicalize_url, compute_geo_signals, frontier_candidates


class FrontierTests(unittest.TestCase):
    def test_canonicalize_url(self) -> None:
        self.assertEqual(
            canonicalize_url("https://Example.com/maps/path#frag"),
            "https://example.com/maps/path",
        )

    def test_geo_signals_detect_geospatial_text(self) -> None:
        payload = {
            "title": "City-scale VPS and 3D reconstruction",
            "description": "Mapping pipeline for localization and AR",
            "main_content": "This geospatial system uses VPS localization, pointcloud mesh fusion, and city mapping.",
            "links": [{"href": "https://x.com/vps", "text": "VPS docs"}],
            "article_date": "2026-01-10",
        }
        signals = compute_geo_signals("https://example.com/research/vps", payload)
        self.assertGreater(signals.aggregate_score, 0.35)

    def test_frontier_candidates_respect_depth(self) -> None:
        payload = {
            "links": [{"href": "https://example.com/maps/vps", "text": "VPS mapping"}],
            "title": "VPS",
            "main_content": "",
            "description": "",
        }
        cands = frontier_candidates(
            parent_url="https://example.com/",
            payload=payload,
            html="",
            current_depth=2,
            max_depth=2,
            max_links=10,
            page_geo_score=0.7,
        )
        self.assertEqual([], cands)


if __name__ == "__main__":
    unittest.main()
