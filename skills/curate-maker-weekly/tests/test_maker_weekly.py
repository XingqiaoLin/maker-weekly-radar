import importlib.util
import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).parents[1] / "scripts" / "maker_weekly.py"
SPEC = importlib.util.spec_from_file_location("maker_weekly", MODULE_PATH)
maker_weekly = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(maker_weekly)


class MakerWeeklyTests(unittest.TestCase):
    def test_parse_datetime_accepts_epoch_milliseconds(self):
        parsed = maker_weekly.parse_datetime(1786039200000)
        self.assertEqual(parsed, datetime(2026, 8, 6, 18, 0, tzinfo=timezone.utc))

    def test_canonical_url_removes_tracking(self):
        first = maker_weekly.canonical_url("https://Example.com/project/?utm_source=x&id=7")
        second = maker_weekly.canonical_url("https://example.com/project?id=7")
        self.assertEqual(first, second)

    def test_collect_caps_each_source_and_deduplicates(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            source_a = [
                {"title": "Open source robotic arm STL", "url": "https://example.com/arm?utm_source=a", "published_at": "2026-08-11T10:00:00Z", "source_score": 100},
                {"title": "Parametric storage bins", "url": "https://example.com/bins", "published_at": "2026-08-10T10:00:00Z", "source_score": 80},
                {"title": "Third item should be capped", "url": "https://example.com/third", "published_at": "2026-08-09T10:00:00Z", "source_score": 20},
            ]
            source_b = [
                {"title": "Open source robotic arm STL", "url": "https://example.com/arm", "published_at": "2026-08-11T11:00:00Z", "source_score": 90},
                {"title": "Printable microscope", "url": "https://example.com/microscope", "published_at": "2026-08-11T09:00:00Z", "source_score": 70},
                {"title": "Another capped item", "url": "https://example.com/fourth", "published_at": "2026-08-09T10:00:00Z", "source_score": 10},
            ]
            (root / "a.json").write_text(json.dumps(source_a), encoding="utf-8")
            (root / "b.json").write_text(json.dumps(source_b), encoding="utf-8")
            config = {
                "lookback_days": 7,
                "top_per_source": 2,
                "final_top": 3,
                "keywords": ["stl", "printable", "parametric"],
                "sources": [
                    {"id": "a", "type": "manual", "platform": "A", "path": "a.json"},
                    {"id": "b", "type": "manual", "platform": "B", "path": "b.json"},
                ],
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            payload = maker_weekly.collect_envelope(config_path, datetime(2026, 8, 12, tzinfo=timezone.utc))

            self.assertEqual([status["count"] for status in payload["source_status"]], [2, 2])
            self.assertEqual(len(payload["items"]), 3)
            arm = next(item for item in payload["items"] if "robotic arm" in item["title"].lower())
            self.assertEqual(len(arm["also_seen_on"]), 1)

            ranked = maker_weekly.baseline_envelope(payload)
            self.assertEqual(len(ranked["items"]), 3)
            self.assertEqual([item["rank"] for item in ranked["items"]], [1, 2, 3])
            self.assertEqual(maker_weekly.validate_ranking(ranked), [])
            report = maker_weekly.render_markdown(ranked)
            self.assertIn("Top 3", report)
            self.assertIn("来源覆盖", report)

    def test_github_rejects_ambiguous_3d_repositories(self):
        response = {
            "items": [
                {
                    "id": 1,
                    "full_name": "maker/printable-arm",
                    "html_url": "https://github.com/maker/printable-arm",
                    "description": "Open-source 3D printed robot arm with STL files",
                    "owner": {"login": "maker"},
                    "created_at": "2026-08-11T00:00:00Z",
                    "stargazers_count": 10,
                    "forks_count": 2,
                    "subscribers_count": 1,
                    "open_issues_count": 0,
                    "topics": ["3d-printing", "robotics"],
                },
                {
                    "id": 2,
                    "full_name": "games/physics-3d",
                    "html_url": "https://github.com/games/physics-3d",
                    "description": "A 3D game physics engine",
                    "owner": {"login": "games"},
                    "created_at": "2026-08-11T00:00:00Z",
                    "stargazers_count": 100,
                    "forks_count": 20,
                    "subscribers_count": 5,
                    "open_issues_count": 0,
                    "topics": ["3d", "physics"],
                },
            ]
        }
        source = {
            "id": "github",
            "type": "github",
            "platform": "GitHub",
            "queries": ["topic:3d-printing"],
            "required_terms": ["3d print", "3d-print", "stl"],
        }
        context = {"since": datetime(2026, 8, 5, tzinfo=timezone.utc), "as_of": datetime(2026, 8, 12, 23, 59, 59, tzinfo=timezone.utc), "limit": 5, "timeout": 10}
        with mock.patch.object(maker_weekly, "request_json", return_value=response) as request:
            items = maker_weekly.collect_github(source, context)
        self.assertEqual([item["title"] for item in items], ["maker/printable-arm"])
        self.assertIn("created%3A2026-08-05..2026-08-12", request.call_args.args[0])

    def test_rss_bundle_merges_feeds_before_source_cap(self):
        first = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Printed arm</title><link href='https://one.test/arm'/><published>2026-08-11T00:00:00Z</published><summary>3D print project</summary></entry></feed>"""
        second = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Printed gearbox</title><link href='https://two.test/gear'/><published>2026-08-10T00:00:00Z</published><summary>3D printer STL</summary></entry></feed>"""
        source = {
            "id": "youtube-rss",
            "type": "rss",
            "platform": "YouTube",
            "feed_urls": ["https://one.test/feed", "https://two.test/feed"],
        }
        context = {
            "timeout": 10,
            "since": datetime(2026, 8, 5, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 12, tzinfo=timezone.utc),
            "lookback_days": 7,
            "keywords": ["3d print", "stl"],
        }
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[first, second]):
            items = maker_weekly.collect_rss(source, context)
        ranked = maker_weekly.cap_and_rank(items, 1)
        self.assertEqual(len(items), 2)
        self.assertEqual(len(ranked), 1)
        self.assertEqual(ranked[0]["platform"], "YouTube")

    def test_rss_rejects_items_after_as_of(self):
        feed = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Future item</title><link href='https://one.test/future'/><published>2026-08-13T00:00:00Z</published><summary>3D print project</summary></entry></feed>"""
        source = {"id": "rss", "type": "rss", "platform": "News", "feed_url": "https://one.test/feed"}
        context = {
            "timeout": 10,
            "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
            "lookback_days": 7,
            "keywords": ["3d print"],
        }
        with mock.patch.object(maker_weekly, "request_bytes", return_value=feed):
            items = maker_weekly.collect_rss(source, context)
        self.assertEqual(items, [])

    def test_youtube_public_enrichment_reads_views_and_subscribers(self):
        page = b'''<html><script>var ytInitialPlayerResponse={"videoDetails":{"videoId":"abc123_X","viewCount":"15394"}};</script>
        <script>{"subscriberCountText":{"simpleText":"701K subscribers"}}</script></html>'''
        item = {"url": "https://www.youtube.com/shorts/abc123_X", "metrics": {}, "evidence": []}
        with mock.patch.object(maker_weekly, "request_bytes", return_value=page) as request:
            maker_weekly.enrich_youtube_public(item, 10)
        self.assertEqual(request.call_args.args[0], "https://www.youtube.com/watch?v=abc123_X")
        self.assertEqual(item["metrics"]["views"], 15394)
        self.assertEqual(item["metrics"]["channel_subscribers"], 701000)
        self.assertEqual(item["metric_verification"]["status"], "ok")
        self.assertEqual(item["metric_verification"]["ranking_basis"], "views/200000 + channel_subscribers/50000")
        self.assertAlmostEqual(item["_raw_score"], 15394 / 200000 + 701000 / 50000)

    def test_reddit_old_enrichment_reads_score_and_comments(self):
        page = b'''<html><div class=" thing link" id="thing_t3_post123" data-comments-count="41" data-score="24" data-type="link"></div></html>'''
        item = {"url": "https://www.reddit.com/r/maker/comments/post123/example/", "metrics": {}, "evidence": []}
        with mock.patch.object(maker_weekly, "request_bytes", return_value=page) as request:
            maker_weekly.enrich_reddit_public(item, 10)
        self.assertEqual(request.call_args.args[0], "https://old.reddit.com/r/maker/comments/post123/example/")
        self.assertEqual(item["metrics"]["score"], 24)
        self.assertEqual(item["metrics"]["comments"], 41)
        self.assertEqual(item["metric_verification"]["status"], "ok")
        self.assertEqual(item["metric_verification"]["ranking_basis"], "score + comments")
        self.assertEqual(item["_raw_score"], 65)

    def test_rss_detail_failure_preserves_candidate_as_unknown(self):
        feed = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Maker video</title><link href='https://www.youtube.com/watch?v=abc123_X'/><published>2026-08-06T00:00:00Z</published></entry></feed>"""
        source = {
            "id": "youtube-rss", "type": "rss", "platform": "YouTube",
            "feed_url": "https://youtube.test/feed", "detail_enrichment": "youtube_public",
        }
        context = {
            "timeout": 10, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
            "lookback_days": 7, "keywords": [],
        }
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[feed, maker_weekly.AccessBlocked("challenge")]):
            items = maker_weekly.collect_rss(source, context)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["metric_verification"]["status"], "error")
        self.assertNotIn("views", items[0]["metrics"])
        self.assertEqual(items[0]["_raw_score"], -1)

    def test_rss_detail_shortlist_is_bounded_before_public_page_requests(self):
        feed = b"""<feed xmlns='http://www.w3.org/2005/Atom'>
        <entry><title>First</title><link href='https://www.youtube.com/watch?v=video001'/><published>2026-08-08T00:00:00Z</published></entry>
        <entry><title>Second</title><link href='https://www.youtube.com/watch?v=video002'/><published>2026-08-07T00:00:00Z</published></entry>
        <entry><title>Third</title><link href='https://www.youtube.com/watch?v=video003'/><published>2026-08-06T00:00:00Z</published></entry>
        </feed>"""
        detail = b'''<html><script>{"videoDetails":{"viewCount":"200000"}}</script></html>'''
        source = {
            "id": "youtube-rss", "type": "rss", "platform": "YouTube",
            "feed_url": "https://youtube.test/feed", "detail_enrichment": "youtube_public",
            "detail_candidate_limit": 2, "detail_workers": 1,
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
            "lookback_days": 7, "keywords": [],
        }
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[feed, detail, detail]) as request:
            items = maker_weekly.collect_rss(source, context)
        self.assertEqual(len(items), 2)
        self.assertEqual(request.call_count, 3)

    def test_web_html_extracts_public_project_and_metrics(self):
        listing = b"""<html><body><a href='/projects/maker/robot-arm'>Robot Arm</a></body></html>"""
        detail = b"""<html><head><meta property='og:title' content='Workshop Robot Arm'/>
        <meta property='og:description' content='A DIY hardware robot.'/>
        <meta property='article:published_time' content='2026-08-07T12:00:00Z'/>
        <meta property='og:url' content='https://example.test/projects/maker/robot-arm'/></head>
        <body>Built from scratch. 250 backers pledged $30,000.</body></html>"""
        source = {
            "id": "crowdfund", "type": "web_html", "platform": "Crowdfund",
            "listing_url": "https://example.test/discover", "link_pattern": r"^https://example\.test/projects/[^/]+/[^/]+$",
            "keywords": ["robot"],
            "metric_patterns": {
                "backers": [r"([0-9,.]+)\s+backers"],
                "usd_pledged": [r"pledged\s+\$([0-9,.]+)"],
            },
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        }
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[listing, detail]):
            items = maker_weekly.collect_web_html(source, context)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["metrics"]["backers"], 250)
        self.assertEqual(items[0]["metrics"]["usd_pledged"], 30000)
        self.assertEqual(items[0]["published_at"], "2026-08-07T12:00:00Z")

    def test_web_html_reports_access_challenge(self):
        source = {
            "id": "blocked", "type": "web_html", "platform": "Blocked",
            "listing_url": "https://blocked.test/discover", "link_pattern": r"/projects/",
        }
        context = {"timeout": 10, "limit": 5}
        with mock.patch.object(maker_weekly, "request_bytes", return_value=b"<title>Just a moment...</title><p>Enable JavaScript and cookies to continue</p>"):
            with self.assertRaises(maker_weekly.AccessBlocked):
                maker_weekly.collect_web_html(source, context)

    def test_kickstarter_kicktraq_uses_official_widget_metrics(self):
        listing = b'''<html><a href="/projects/maker/robot-arm/">Robot Arm</a></html>'''
        payload = {
            "name": "Open Hardware Robot Arm", "blurb": "A DIY robot arm built and tested from scratch.",
            "goal": 10000, "state": "live", "currency": "USD", "backers_count": 250,
            "usd_pledged": "30000", "staff_pick": True, "launched_at": 1785859200,
            "deadline": 1788451200, "creator": {"name": "Small Maker Team"},
            "category": {"parent_name": "Technology", "name": "Robots"},
            "urls": {"web": {"project": "https://www.kickstarter.com/projects/maker/robot-arm"}},
        }
        encoded = maker_weekly.html.escape(json.dumps(payload))
        widget = f'<html><script>window.current_project = "{encoded}";</script></html>'.encode()
        source = {
            "id": "kickstarter", "type": "kickstarter_kicktraq", "platform": "Kickstarter",
            "listing_url": "https://www.kicktraq.com/categories/technology/robots/?sort=new",
            "keywords": ["robot", "hardware"], "detail_workers": 1,
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        }
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[listing, widget]) as request:
            items = maker_weekly.collect_kickstarter_kicktraq(source, context)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["metrics"]["backers"], 250)
        self.assertEqual(items[0]["metrics"]["usd_pledged"], 30000)
        self.assertEqual(items[0]["metric_verification"]["status"], "ok")
        self.assertIn("/widget/card.html?v=2", request.call_args_list[1].args[0])

    def test_indiegogo_public_api_filters_window_and_preserves_currency(self):
        projects = [
            {
                "projectName": "Workshop CNC Machine", "shortDescription": "Open hardware fabrication machine",
                "campaignStartDate": "2026-08-07T10:00:00Z", "campaignEndDate": "2026-09-07T10:00:00Z",
                "campaignGoal": 10000, "fundsGathered": 25000, "currencyShortName": "USD", "backerCount": 220,
                "commentCount": 4, "updateCount": 2, "creatorName": "Tiny Workshop",
                "projectHomeUrl": "https://www.indiegogo.com/projects/tiny-workshop/workshop-cnc-machine",
            },
            {
                "projectName": "Old Robot", "shortDescription": "A robot",
                "campaignStartDate": "2026-07-01T10:00:00Z", "fundsGathered": 90000,
                "currencyShortName": "EUR", "backerCount": 500,
                "projectHomeUrl": "https://www.indiegogo.com/projects/old/old-robot",
            },
        ]
        source = {
            "id": "indiegogo", "type": "indiegogo_public", "platform": "Indiegogo",
            "endpoint": "https://www.indiegogo.com/api/public/projects/getActiveCrowdfundingProjects",
            "keywords": ["hardware", "robot", "cnc"],
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        }
        with mock.patch.object(maker_weekly, "request_bytes", return_value=json.dumps(projects).encode()):
            items = maker_weekly.collect_indiegogo_public(source, context)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["metrics"]["usd_pledged"], 25000)
        self.assertEqual(items[0]["metrics"]["backers"], 220)
        self.assertEqual(items[0]["metric_verification"]["status"], "ok")

    def test_instructables_web_uses_public_page_search_configuration(self):
        bootstrap = b"""<html><script id='js-page-context' type='application/json'>
        {"typesenseProxy":"/api_proxy/search","typesenseApiKey":"public-page-token"}
        </script></html>"""
        search = {
            "hits": [{"document": {
                "title": "Featured Robot", "urlString": "Featured-Robot", "screenName": "Maker",
                "favorites": 12, "views": 3400, "featureFlag": True, "IMadeItCount": 4,
                "publishDate": "2026-08-06T10:00:00Z", "primaryClassification": {"category": "Circuits", "channel": "Robots"},
            }}]
        }
        source = {
            "id": "instructables", "type": "instructables_web", "platform": "Instructables",
            "bootstrap_url": "https://www.instructables.com/circuits/projects/", "categories": ["Circuits"],
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        }
        with mock.patch.object(maker_weekly, "request_bytes", return_value=bootstrap), mock.patch.object(maker_weekly, "request_json", return_value=search) as request:
            items = maker_weekly.collect_instructables_web(source, context)
        self.assertEqual(len(items), 1)
        self.assertTrue(items[0]["metrics"]["featured"])
        self.assertEqual(items[0]["author"], "Maker")
        self.assertIn("featureFlag%3A%3Dtrue", request.call_args.args[0])

    def test_invalid_ranking_is_rejected(self):
        payload = {
            "config_summary": {"final_top": 1},
            "items": [{"id": "x", "title": "x", "url": "https://x.test", "platform": "x", "rank": 1, "ai_score": 120}],
        }
        errors = maker_weekly.validate_ranking(payload)
        self.assertTrue(any("ai_score" in error for error in errors))
        self.assertTrue(any("score_breakdown" in error for error in errors))

    def test_editorial_decisions_merge_source_evidence(self):
        candidate = {
            "id": "abc",
            "title": "Printable arm",
            "url": "https://example.test/arm",
            "platform": "GitHub",
            "evidence": ["https://example.test/arm"],
        }
        collected = {"config_summary": {"final_top": 15}, "items": [candidate]}
        decisions = {
            "selection_method": "codex-ai-rubric-v1",
            "items": [{
                "id": "abc",
                "ai_score": 88,
                "score_breakdown": {"maker_usefulness": 25},
                "why_selected": "Reproducible and useful.",
                "risks_or_unknowns": [],
            }],
        }
        ranked = maker_weekly.editorial_envelope(collected, decisions)
        self.assertEqual(ranked["items"][0]["rank"], 1)
        self.assertEqual(ranked["items"][0]["evidence"], ["https://example.test/arm"])
        self.assertEqual(ranked["selection_method"], "codex-ai-rubric-v1")


if __name__ == "__main__":
    unittest.main()
