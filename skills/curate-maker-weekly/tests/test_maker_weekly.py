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

    def test_physical_gate_failures_do_not_occupy_platform_top_five(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            evidence = {"checks": {"creator_made_physical": True, "physical_is_core": True, "built_result_visible": True, "human_process_visible": True}, "evidence": [{"type": "video", "url": "https://example.com/build.mp4"}]}
            captured = "2026-08-12T00:00:00Z"
            source_a = [
                {"title": "Embodied-AI-Guide", "url": "https://example.com/guide", "published_at": "2026-08-11T10:00:00Z", "source_score": 999, "metrics": {"stars": 50000}, "metrics_captured_at": captured},
                {"title": "Physical robot one", "url": "https://example.com/one", "published_at": "2026-08-11T10:00:00Z", "source_score": 100, "metrics": {"stars": 1200}, "metrics_captured_at": captured, "physical_evidence": evidence},
                {"title": "Physical robot two", "url": "https://example.com/two", "published_at": "2026-08-10T10:00:00Z", "source_score": 80, "metrics": {"stars": 1100}, "metrics_captured_at": captured, "physical_evidence": evidence},
            ]
            source_b = []
            (root / "a.json").write_text(json.dumps(source_a), encoding="utf-8")
            (root / "b.json").write_text(json.dumps(source_b), encoding="utf-8")
            config = {
                "lookback_days": 7,
                "top_per_source": 2,
                "final_top": 3,
                "keywords": ["stl", "printable", "parametric"],
                "sources": [
                    {"id": "a", "type": "manual", "platform": "GitHub", "path": "a.json"},
                    {"id": "b", "type": "manual", "platform": "GitHub", "path": "b.json"},
                ],
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            as_of = datetime(2026, 8, 12, tzinfo=timezone.utc)
            raw = maker_weekly.collect_raw_envelope(config_path, as_of)
            annotated, physical = maker_weekly.physical_prefilter_envelopes(raw, workers=1)
            payload = maker_weekly.editorial_candidates_envelope(physical, as_of)

            rejected = next(item for item in annotated["items"] if item["title"] == "Embodied-AI-Guide")
            self.assertEqual(rejected["physical_gate"]["status"], "fail")
            self.assertEqual(len(physical["items"]), 2)
            self.assertEqual({item["title"] for item in payload["items"]}, {"Physical robot one", "Physical robot two"})

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

    def test_publication_window_rejects_old_project_updated_this_week(self):
        old = {"published_at": "2018-06-29T23:57:16Z", "metrics": {"pushed_at": "2026-08-06T15:43:16Z"}}
        new = {"published_at": "2026-08-06T12:00:00Z"}
        since = datetime(2026, 8, 3, tzinfo=timezone.utc)
        as_of = datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc)
        self.assertFalse(maker_weekly.publication_is_in_window(old, since, as_of))
        self.assertTrue(maker_weekly.publication_is_in_window(new, since, as_of))

    def test_verified_social_heat_gates(self):
        youtube_low = {"platform": "YouTube", "metrics": {"views": 199999, "channel_subscribers": 49999}, "metric_verification": {"status": "ok"}}
        youtube_channel = {"platform": "YouTube", "metrics": {"views": 10, "channel_subscribers": 50000}, "metric_verification": {"status": "ok"}}
        reddit_low = {"platform": "Reddit", "metrics": {"score": 4900, "comments": 99}, "metric_verification": {"status": "ok"}}
        reddit_pass = {"platform": "Reddit", "metrics": {"score": 4900, "comments": 100}, "metric_verification": {"status": "ok"}}
        self.assertFalse(maker_weekly.verified_platform_heat_passes(youtube_low))
        self.assertTrue(maker_weekly.verified_platform_heat_passes(youtube_channel))
        self.assertFalse(maker_weekly.verified_platform_heat_passes(reddit_low))
        self.assertTrue(maker_weekly.verified_platform_heat_passes(reddit_pass))

    def test_reddit_rss_excludes_question_posts_before_enrichment(self):
        feed = b"""<feed xmlns='http://www.w3.org/2005/Atom'>
        <entry><title>What's the most useful thing you have built?</title><link href='https://www.reddit.com/r/maker/comments/question001/example/'/><published>2026-08-07T00:00:00Z</published></entry>
        <entry><title>I built a working robot from scratch</title><link href='https://www.reddit.com/r/maker/comments/project001/example/'/><published>2026-08-07T00:00:00Z</published></entry>
        </feed>"""
        source = {
            "id": "reddit-rss", "type": "rss", "platform": "Reddit", "feed_url": "https://reddit.test/feed",
            "required_patterns": [r"\b(i|we)\s+(built|made|designed|created)\b"],
            "excluded_patterns": [r"\bwhat.s\b"],
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
            "lookback_days": 7, "keywords": [],
        }
        with mock.patch.object(maker_weekly, "request_bytes", return_value=feed):
            items = maker_weekly.collect_rss(source, context)
        self.assertEqual([item["title"] for item in items], ["I built a working robot from scratch"])

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
        self.assertEqual(items[0]["metric_verification"]["status"], "blocked")
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

    def test_zero_gate_rejects_named_software_and_knowledge_pollution(self):
        names = [
            "Embodied-AI-Guide", "YOLO26 on Dragonwing NPU performance test",
            "Edge AI Yocto Integration SDK tutorial", "VendPro Toolkit ebook",
        ]
        for name in names:
            with self.subTest(name=name):
                item = {"title": name, "summary": name, "platform": "GitHub", "url": "https://example.test/item", "author": "Author"}
                page = {"source_url": item["url"], "text": name, "media_urls": ["https://example.test/screenshot.png"], "structured_steps": 5, "author": "Author"}
                gate = maker_weekly.derive_physical_gate(item, page)
                self.assertEqual(gate["status"], "fail")
                self.assertEqual(gate["rejection_reason"], "未找到真实物理造物证据")

    def test_zero_gate_rejects_music_story_and_content_products(self):
        for name in ["Placid Drive music album", "THE ISLAND FORTRESS story only", "Business Starter ebook toolkit"]:
            with self.subTest(name=name):
                item = {"title": name, "summary": name, "platform": "Kickstarter", "url": "https://example.test/campaign", "author": "Creator"}
                page = {"source_url": item["url"], "text": name, "media_urls": ["https://example.test/cover.jpg"], "structured_steps": 6, "author": "Creator"}
                self.assertEqual(maker_weekly.derive_physical_gate(item, page)["status"], "fail")

    def test_zero_gate_rejects_concept_or_marketing_campaign(self):
        item = {"title": "AI Robot Coming Soon", "summary": "Concept rendering and prelaunch product marketing", "platform": "Kickstarter", "url": "https://example.test/concept", "author": "Brand"}
        page = {"source_url": item["url"], "text": item["summary"], "media_urls": ["https://example.test/render.jpg"], "structured_steps": 0, "author": "Brand"}
        self.assertEqual(maker_weekly.derive_physical_gate(item, page)["status"], "fail")

    def test_zero_gate_accepts_documented_physical_robot(self):
        item = {"title": "Workshop robot", "platform": "Hackster.io", "url": "https://example.test/robot", "author": "Small Team"}
        page = {
            "source_url": item["url"],
            "text": "We designed and built a working robot device. We printed the enclosure, soldered the circuit, assembled the motor and tested two prototype iterations.",
            "media_urls": ["https://example.test/robot-running.mp4"], "structured_steps": 5, "author": "Small Team",
        }
        gate = maker_weekly.derive_physical_gate(item, page)
        self.assertEqual(gate["status"], "pass")
        self.assertTrue(all(gate["checks"].values()))

    def test_readme_badges_logos_and_screenshots_are_not_physical_evidence(self):
        item = {"title": "Robot hardware toolkit", "platform": "GitHub", "url": "https://github.com/example/tool", "author": "Developer"}
        text = "We built and assembled robot hardware, soldered a circuit, tested a prototype and documented a BOM."
        for media in ["https://img.shields.io/badge/hardware-open.svg", "https://example.test/logo.png", "https://example.test/screenshot.png"]:
            with self.subTest(media=media):
                gate = maker_weekly.derive_physical_gate(item, {"source_url": item["url"], "text": text, "media_urls": [media], "structured_steps": 5, "author": "Developer"})
                self.assertEqual(gate["status"], "fail")

    def test_social_detail_failures_become_coverage_error_or_blocked(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config = {"sources": [
                {"id": "youtube", "type": "rss", "platform": "YouTube", "feed_url": "https://youtube.test/feed"},
                {"id": "reddit", "type": "rss", "platform": "Reddit", "feed_url": "https://reddit.test/feed"},
            ]}
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")

            def fake(source, _context):
                if source["id"] == "youtube":
                    raise maker_weekly.AccessBlocked("login challenge")
                raise RuntimeError("parser failed")

            with mock.patch.dict(maker_weekly.COLLECTORS, {"rss": fake}):
                payload = maker_weekly.collect_raw_envelope(path, datetime(2026, 8, 12, tzinfo=timezone.utc))
            self.assertEqual([status["status"] for status in payload["source_status"]], ["blocked", "error"])

    def test_all_physical_detail_challenges_mark_platform_blocked(self):
        payload = {
            "source_status": [{"source_id": "kickstarter", "platform": "Kickstarter", "status": "ok", "raw_count": 1}],
            "items": [{"source_id": "kickstarter", "platform": "Kickstarter", "url": "https://kickstarter.test/project", "title": "Project"}],
        }
        gate = {"status": "fail", "checks": {}, "evidence": [], "rejection_reason": "未找到真实物理造物证据", "verification_status": "blocked"}
        with mock.patch.object(maker_weekly, "inspect_physical_candidate", return_value=gate):
            annotated, _ = maker_weekly.physical_prefilter_envelopes(payload, workers=1)
        self.assertEqual(annotated["source_status"][0]["status"], "blocked")

    def test_raw_discoveries_renderer_is_explicitly_non_publishable(self):
        payload = {"selection_method": "raw-discovery-audit-only", "as_of": "2026-08-09T23:59:59Z", "config_summary": {"final_top": 15}, "source_status": [], "items": [{"rank": 1, "id": "raw", "title": "Placid Drive", "url": "https://example.test/music", "platform": "Kickstarter", "metrics": {}}]}
        report = maker_weekly.render_markdown(payload)
        self.assertIn("原始发现审计报告（不可发布）", report)
        self.assertNotIn("本周项目", report)
        self.assertNotIn("入选理由", report)
        self.assertNotIn("Top 12", report)

    def test_post_cutoff_heat_cannot_backfill_an_issue(self):
        item = {"platform": "YouTube", "url": "https://youtube.com/watch?v=abcdef1", "metrics": {"views": 999999}, "metrics_captured_at": "2026-08-12T00:00:00Z"}
        gate = maker_weekly.evaluate_heat_gate(item, datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc))
        self.assertEqual(gate["status"], "fail")
        self.assertIn("晚于周末截止", gate["observed"])

    def test_formal_default_has_all_13_platforms_and_broad_social_rss(self):
        config_path = Path(__file__).parents[1] / "assets" / "config.example.json"
        config = maker_weekly.load_config(config_path)
        self.assertEqual(len(config["sources"]), 13)
        by_id = {source["id"]: source for source in config["sources"]}
        self.assertTrue(by_id["kickstarter"]["enabled"])
        self.assertTrue(by_id["youtube-rss"]["enabled"])
        self.assertTrue(by_id["reddit-rss"]["enabled"])
        self.assertNotIn("required_patterns", by_id["youtube-rss"])
        self.assertNotIn("required_patterns", by_id["reddit-rss"])
        self.assertGreaterEqual(len(by_id["youtube-rss"]["feed_urls"]), 29)
        reddit_communities = set()
        for url in by_id["reddit-rss"]["feed_urls"]:
            bundle = url.split("/r/", 1)[1].split("/top/", 1)[0]
            reddit_communities.update(bundle.split("+"))
        self.assertGreaterEqual(len(reddit_communities), 20)

    def test_github_physical_gate_reads_raw_readme_without_detail_api(self):
        readme = b"""# Working Robot\nWe designed and built a working robot device from scratch.\n## Hardware build\nWe printed the enclosure, soldered the sensor circuit, assembled motors, tested the prototype, and iterated.\n![running robot](images/robot.jpg)\n"""
        item = {
            "platform": "GitHub", "title": "maker/robot", "url": "https://github.com/maker/robot",
            "author": "maker", "provider_data": {"default_branch": "trunk"},
        }
        with mock.patch.object(maker_weekly, "request_bytes", return_value=readme) as request:
            gate = maker_weekly.inspect_physical_candidate(item, 10)
        requested_url = request.call_args.args[0]
        self.assertEqual(requested_url, "https://raw.githubusercontent.com/maker/robot/trunk/README.md")
        self.assertNotIn("api.github.com", requested_url)
        self.assertEqual(gate["status"], "pass")

    def test_kickstarter_official_posts_feed_can_prove_physical_process(self):
        feed = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry>
        <title>Six prototype generations</title>
        <content type='html'>&lt;p&gt;I designed and built a working robot device from scratch. The first prototype used motors and sensors. We printed the enclosure, assembled the circuit, tested it, and completed six redesign iterations.&lt;/p&gt;&lt;figure&gt;&lt;div url='https://youtube.com/watch?v=abcdef1'&gt;&lt;/div&gt;&lt;/figure&gt;</content>
        </entry></feed>"""
        item = {"platform": "Kickstarter", "title": "Physical robot", "url": "https://www.kickstarter.com/projects/maker/physical-robot", "author": "Maker Team"}
        with mock.patch.object(maker_weekly, "request_bytes", return_value=feed) as request:
            gate = maker_weekly.inspect_physical_candidate(item, 10)
        self.assertTrue(request.call_args.args[0].endswith("/posts.atom"))
        self.assertEqual(gate["status"], "pass")

    def test_rss_embedded_author_text_and_media_feed_physical_gate(self):
        feed = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry>
        <title>I built a working robot device</title><link href='https://www.reddit.com/r/maker/comments/abc123/robot/'/>
        <published>2026-08-07T00:00:00Z</published><author><name>actual_maker</name></author>
        <content type='html'>&lt;p&gt;I designed and built this working robot from scratch. I printed the enclosure, soldered the sensor circuit, assembled its motors, tested the prototype and iterated.&lt;/p&gt;&lt;img src='https://i.redd.it/robot-build.jpg'/&gt;</content>
        </entry></feed>"""
        source = {"id": "reddit-rss", "type": "rss", "platform": "Reddit", "feed_url": "https://reddit.test/feed"}
        context = {"timeout": 10, "limit": 10, "since": datetime(2026, 8, 3, tzinfo=timezone.utc), "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc), "lookback_days": 7, "keywords": []}
        with mock.patch.object(maker_weekly, "request_bytes", return_value=feed):
            items = maker_weekly.collect_rss(source, context)
        self.assertEqual(items[0]["author"], "actual_maker")
        self.assertIn("https://i.redd.it/robot-build.jpg", items[0]["physical_page"]["media_urls"])
        self.assertEqual(maker_weekly.inspect_physical_candidate(items[0], 10)["status"], "pass")

    def test_reddit_software_agent_post_and_plain_links_fail_physical_gate(self):
        item = {"platform": "Reddit", "title": "Autoresearch for Robotics Hardware", "url": "https://reddit.com/r/robotics/comments/abc/software", "author": "developer"}
        page = {
            "source_url": item["url"],
            "text": "I let autoresearch coding agents run 1200 code experiments to discover a physics model and new algorithm architectures. The CLI uses git for experiment tracking.",
            "media_urls": [item["url"], "https://github.com/example/software"], "structured_steps": 5, "author": "developer",
        }
        gate = maker_weekly.derive_physical_gate(item, page)
        self.assertEqual(gate["status"], "fail")


if __name__ == "__main__":
    unittest.main()
