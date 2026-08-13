import importlib.util
import json
import http.client
import tempfile
import unittest
import urllib.error
from collections import Counter
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

    def test_cli_defaults_to_bundled_zero_credential_config(self):
        args = maker_weekly.build_parser().parse_args(["run", "--output-dir", "output"])
        self.assertEqual(args.config, maker_weekly.DEFAULT_CONFIG_PATH)
        self.assertTrue(args.config.is_file())

    def test_github_reuses_existing_gh_cli_login_without_configuration(self):
        source = {
            "id": "github", "type": "github", "platform": "GitHub",
            "queries": ["topic:open-hardware"], "required_terms": ["hardware"],
            "date_qualifier": "created",
        }
        context = {
            "timeout": 10, "limit": 5,
            "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        }
        response = {"items": [{
            "id": 1, "full_name": "maker/new-hardware", "html_url": "https://github.com/maker/new-hardware",
            "description": "Open hardware robot", "owner": {"login": "maker"},
            "created_at": "2026-08-05T00:00:00Z", "updated_at": "2026-08-06T00:00:00Z",
            "pushed_at": "2026-08-06T00:00:00Z", "default_branch": "main",
            "stargazers_count": 1200, "forks_count": 10, "subscribers_count": 5,
            "open_issues_count": 1, "topics": ["open-hardware"],
        }]}
        completed = maker_weekly.subprocess.CompletedProcess(["gh", "auth", "token"], 0, stdout="local-token\n", stderr="")
        with mock.patch.dict(maker_weekly.os.environ, {}, clear=True), \
                mock.patch.object(maker_weekly.shutil, "which", return_value="/usr/bin/gh"), \
                mock.patch.object(maker_weekly.subprocess, "run", return_value=completed), \
                mock.patch.object(maker_weekly, "request_json", return_value=response) as request:
            items = maker_weekly.collect_github(source, context)
        self.assertEqual(len(items), 1)
        self.assertEqual(request.call_args.kwargs["headers"]["Authorization"], "Bearer local-token")

    def test_github_remains_anonymous_when_no_existing_login_exists(self):
        with mock.patch.dict(maker_weekly.os.environ, {}, clear=True), \
                mock.patch.object(maker_weekly.shutil, "which", return_value=None):
            self.assertIsNone(maker_weekly.discover_github_token({"id": "github"}))

    def test_raw_discovery_budget_caps_each_source_before_physical_fetches(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            discoveries = [
                {"title": f"Project {index}", "url": f"https://example.test/{index}", "source_score": (index + 1) * 10}
                for index in range(5)
            ]
            (root / "items.json").write_text(json.dumps(discoveries), encoding="utf-8")
            config = {
                "discovery_per_source": 2,
                "sources": [{"id": "manual", "type": "manual", "platform": "Example", "path": "items.json"}],
            }
            config_path = root / "config.json"
            config_path.write_text(json.dumps(config), encoding="utf-8")
            payload = maker_weekly.collect_raw_envelope(config_path, datetime(2026, 8, 9, tzinfo=timezone.utc))
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual([item["title"] for item in payload["items"]], ["Project 4", "Project 3"])

    def test_physical_gate_failures_do_not_occupy_global_top_fifteen(self):
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

    def test_editorial_research_pool_keeps_every_three_gate_pass(self):
        captured = "2026-08-12T00:00:00Z"
        items = []
        names = [
            "walking robot", "solar kiln", "wearable loom", "kinetic sculpture", "assistive gripper",
            "wooden telescope", "ceramic printer", "underwater rover", "mechanical clock", "smart beehive",
            "portable foundry", "adaptive bicycle", "paper automaton", "recycled kayak", "braille keyboard",
            "garden monitor", "camera slider", "wind turbine", "musical staircase", "folding wheelchair",
        ]
        for index in range(20):
            platform = "YouTube" if index < 16 else "Reddit"
            metrics = {"views": 1_000_000 - index * 10_000} if platform == "YouTube" else {"score": 5000, "comments": 500}
            items.append({
                "id": f"item-{index}", "source_id": platform.lower(), "platform": platform,
                "title": f"I built a {names[index]}", "url": f"https://example.test/{index}",
                "published_at": "2026-08-08T00:00:00Z", "metrics_captured_at": captured,
                "metrics": metrics, "physical_gate": {
                    "status": "pass", "checks": {
                        "creator_made_physical": True, "physical_is_core": True,
                        "built_result_visible": True, "human_process_visible": True,
                    },
                }, "evidence": [f"https://example.test/{index}/evidence"],
            })
        payload = {
            "window_start": "2026-08-03T00:00:00Z", "config_summary": {"final_top": 15},
            "source_status": [
                {"source_id": "youtube", "platform": "YouTube", "status": "ok"},
                {"source_id": "reddit", "platform": "Reddit", "status": "ok"},
            ], "items": items,
        }
        result = maker_weekly.editorial_candidates_envelope(payload, datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc))
        self.assertEqual(len(result["items"]), 20)
        self.assertEqual(sum(item["platform"] == "YouTube" for item in result["items"]), 16)
        self.assertEqual(result["selection_method"], "physical-time-heat-full-research-pool-v1")
        self.assertTrue(all("radar_score" in item for item in result["items"]))

    def test_candidate_mix_is_not_applied_before_strict_review(self):
        captured = "2026-08-12T00:00:00Z"
        specs = [
            ("YouTube", 8), ("Reddit", 6), ("Kickstarter", 1), ("Hackaday", 1),
            ("Instructables", 2), ("Hackster.io", 1), ("Make Magazine", 1),
        ]
        items = []
        index = 0
        names = [
            "walking robot", "solar kiln", "wearable loom", "kinetic sculpture", "assistive gripper",
            "wooden telescope", "ceramic printer", "underwater rover", "mechanical clock", "smart beehive",
            "portable foundry", "adaptive bicycle", "paper automaton", "recycled kayak", "braille keyboard",
            "garden monitor", "camera slider", "wind turbine", "musical staircase", "folding wheelchair",
        ]
        for platform, count in specs:
            for platform_index in range(count):
                metrics = {"views": 500_000 - index * 1000} if platform == "YouTube" else {}
                if platform == "Reddit":
                    metrics = {"score": 3000, "comments": 500}
                elif platform == "Kickstarter":
                    metrics = {"currency": "USD", "usd_pledged": 20_000, "backers": 100}
                elif platform in {"Instructables", "Hackster.io"}:
                    metrics = {"featured": True}
                items.append({
                    "id": f"mix-{index}", "source_id": platform.lower(), "platform": platform,
                    "title": f"I built a {names[index]}",
                    "url": f"https://example.test/mix/{index}", "published_at": "2026-08-08T00:00:00Z",
                    "metrics_captured_at": captured, "metrics": metrics,
                    "physical_gate": {"status": "pass", "checks": {
                        "creator_made_physical": True, "physical_is_core": True,
                        "built_result_visible": True, "human_process_visible": True,
                    }}, "evidence": [f"https://example.test/mix/{index}/build"],
                })
                index += 1
        mix = {"enabled": True, "initial_slots": {
            "youtube": 5, "reddit": 4, "crowdfunding": 1, "hackaday": 1, "other": 4,
        }}
        statuses = [{"source_id": name.lower(), "platform": name, "status": "ok"} for name, _ in specs]
        result = maker_weekly.editorial_candidates_envelope({
            "window_start": "2026-08-03T00:00:00Z",
            "config_summary": {"final_top": 15, "final_mix": mix},
            "source_status": statuses, "items": items,
        }, datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc))
        self.assertEqual(len(result["items"]), len(items))
        self.assertEqual(Counter(item["platform"] for item in result["items"]), Counter({
            "YouTube": 8, "Reddit": 6, "Kickstarter": 1, "Hackaday": 1,
            "Instructables": 2, "Hackster.io": 1, "Make Magazine": 1,
        }))
        self.assertEqual(result["selection_method"], "physical-time-heat-full-research-pool-v1")
        self.assertTrue(all("candidate_mix_slot" not in item for item in result["items"]))

    def test_candidate_mix_configuration_is_validated(self):
        source = {"id": "manual", "type": "manual", "platform": "Example", "path": "items.json"}
        with self.assertRaises(maker_weekly.ConfigError):
            maker_weekly.validate_config({
                "final_top": 15, "final_mix": {"enabled": True, "initial_slots": {"youtube": 20}},
                "sources": [source],
            })
        maker_weekly.validate_config({
            "final_top": 15, "final_mix": {"enabled": True, "initial_slots": {
                "youtube": 5, "reddit": 4, "crowdfunding": 1, "hackaday": 1, "other": 4,
            }}, "sources": [source],
        })

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

    def test_github_readme_connection_failure_does_not_multiply_timeouts(self):
        item = {
            "platform": "GitHub", "url": "https://github.com/maker/robot",
            "provider_data": {"default_branch": "main"},
        }
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=RuntimeError("TLS connection failed")) as request:
            with self.assertRaises(RuntimeError):
                maker_weekly.github_readme_page(item, 10)
        self.assertEqual(request.call_count, 1)

    def test_publication_window_rejects_old_project_updated_this_week(self):
        old = {"published_at": "2018-06-29T23:57:16Z", "metrics": {"pushed_at": "2026-08-06T15:43:16Z"}}
        new = {"published_at": "2026-08-06T12:00:00Z"}
        since = datetime(2026, 8, 3, tzinfo=timezone.utc)
        as_of = datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc)
        self.assertFalse(maker_weekly.publication_is_in_window(old, since, as_of))
        self.assertTrue(maker_weekly.publication_is_in_window(new, since, as_of))

    def test_verified_social_heat_gates(self):
        youtube_low = {"platform": "YouTube", "metrics": {"views": 24999, "channel_subscribers": 9999}, "metric_verification": {"status": "ok"}}
        youtube_channel = {"platform": "YouTube", "metrics": {"views": 10, "channel_subscribers": 10000}, "metric_verification": {"status": "ok"}}
        reddit_low = {"platform": "Reddit", "metrics": {"score": 400, "comments": 99}, "metric_verification": {"status": "ok"}}
        reddit_pass = {"platform": "Reddit", "metrics": {"score": 400, "comments": 100}, "metric_verification": {"status": "ok"}}
        self.assertFalse(maker_weekly.verified_platform_heat_passes(youtube_low))
        self.assertTrue(maker_weekly.verified_platform_heat_passes(youtube_channel))
        self.assertFalse(maker_weekly.verified_platform_heat_passes(reddit_low))
        self.assertTrue(maker_weekly.verified_platform_heat_passes(reddit_pass))

    def test_expanded_heat_profile_keeps_exact_verified_boundaries(self):
        captured = "2026-08-12T00:00:00Z"
        as_of = datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc)
        cases = [
            ({"platform": "Kickstarter", "metrics": {"backers": 39}, "metrics_captured_at": captured}, "fail"),
            ({"platform": "Kickstarter", "metrics": {"backers": 40}, "metrics_captured_at": captured}, "pass"),
            ({"platform": "Kickstarter", "metrics": {"currency": "CAD", "reported_usd_pledged": 8411, "backers": 47, "currency_conversion": {"status": "unverified", "admissible_for_heat_gate": False}}, "metrics_captured_at": captured}, "pass"),
            ({"platform": "Kickstarter", "metrics": {"currency": "HKD", "reported_usd_pledged": 460475, "backers": 107, "currency_conversion": {"status": "unverified", "admissible_for_heat_gate": False}}, "metrics_captured_at": captured}, "pass"),
            ({"platform": "Kickstarter", "metrics": {"currency": "USD", "usd_pledged": 5000, "backers": 1}, "metrics_captured_at": captured}, "pass"),
            ({"platform": "YouTube", "metrics": {"views": 24999}, "metrics_captured_at": captured}, "fail"),
            ({"platform": "YouTube", "metrics": {"views": 25000}, "metrics_captured_at": captured}, "pass"),
            ({"platform": "Reddit", "metrics": {"score": 400, "comments": 99}, "metrics_captured_at": captured}, "fail"),
            ({"platform": "Reddit", "metrics": {"score": 400, "comments": 100}, "metrics_captured_at": captured}, "pass"),
            ({"platform": "Indiegogo", "metrics": {"backers": 100}, "metrics_captured_at": captured}, "fail"),
        ]
        for item, expected in cases:
            with self.subTest(item=item):
                self.assertEqual(maker_weekly.evaluate_heat_gate(item, as_of)["status"], expected)

    def test_heat_thresholds_are_configurable_without_changing_evidence_rules(self):
        thresholds = maker_weekly.resolve_heat_thresholds({"reddit": {"score_plus_comments": 1500}})
        item = {
            "platform": "Reddit", "metrics": {"score": 1000, "comments": 200},
            "metrics_captured_at": "2026-08-12T00:00:00Z",
        }
        gate = maker_weekly.evaluate_heat_gate(item, datetime(2026, 8, 9, tzinfo=timezone.utc), thresholds)
        self.assertEqual(gate["status"], "fail")
        with self.assertRaises(maker_weekly.ConfigError):
            maker_weekly.resolve_heat_thresholds({"reddit": {"score_plus_comments": 0}})

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

    def test_partial_rss_bundle_is_error_and_preserves_successful_discoveries(self):
        feed = b"""<feed xmlns='http://www.w3.org/2005/Atom'><entry><title>Working robot</title><link href='https://youtube.test/watch?v=working1'/><published>2026-08-07T00:00:00Z</published></entry></feed>"""
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config = {"lookback_days": 7, "sources": [{
                "id": "youtube-rss", "type": "rss", "platform": "YouTube",
                "feed_urls": ["https://youtube.test/good", "https://youtube.test/stale"],
            }]}
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with mock.patch.object(maker_weekly, "request_bytes", side_effect=[feed, maker_weekly.ResourceNotFound("HTTP 404 from provider")]):
                payload = maker_weekly.collect_raw_envelope(path, datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc))
        status = payload["source_status"][0]
        self.assertEqual(status["status"], "error")
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(status["coverage"]["feed_coverage"]["successful_feeds"], 1)
        self.assertEqual(status["coverage"]["feed_coverage"]["total_feeds"], 2)
        self.assertEqual(status["coverage"]["feed_coverage"]["failures"][0]["http_status"], 404)

    def test_partial_rss_bundle_with_no_items_is_error_not_empty(self):
        empty_feed = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config = {"sources": [{
                "id": "youtube-rss", "type": "rss", "platform": "YouTube",
                "feed_urls": ["https://youtube.test/empty", "https://youtube.test/broken"],
            }]}
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with mock.patch.object(maker_weekly, "request_bytes", side_effect=[empty_feed, maker_weekly.ProviderServerError(500)]):
                payload = maker_weekly.collect_raw_envelope(path, datetime(2026, 8, 9, tzinfo=timezone.utc))
        self.assertEqual(payload["source_status"][0]["status"], "error")
        self.assertEqual(payload["source_status"][0]["raw_count"], 0)

    def test_complete_empty_rss_bundle_is_empty(self):
        empty_feed = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config = {"sources": [{
                "id": "youtube-rss", "type": "rss", "platform": "YouTube",
                "feed_urls": ["https://youtube.test/one", "https://youtube.test/two"],
            }]}
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with mock.patch.object(maker_weekly, "request_bytes", side_effect=[empty_feed, empty_feed]):
                payload = maker_weekly.collect_raw_envelope(path, datetime(2026, 8, 9, tzinfo=timezone.utc))
        status = payload["source_status"][0]
        self.assertEqual(status["status"], "empty")
        self.assertEqual(status["coverage"]["feed_coverage"]["success_ratio"], 1.0)

    def test_rss_recovery_retries_only_failed_feeds(self):
        feed = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
        source = {
            "id": "youtube-rss", "type": "rss", "platform": "YouTube",
            "feed_urls": ["https://youtube.test/good", "https://youtube.test/rate-limited"],
            "feed_recovery_rounds": 1, "feed_recovery_pause_seconds": 0,
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
            "lookback_days": 7, "keywords": [],
        }
        with mock.patch.object(
            maker_weekly, "request_bytes",
            side_effect=[feed, maker_weekly.RateLimited(0), feed],
        ) as request, mock.patch.object(maker_weekly.time, "sleep"):
            self.assertEqual(maker_weekly.collect_rss(source, context), [])
        self.assertEqual(
            [call.args[0] for call in request.call_args_list],
            ["https://youtube.test/good", "https://youtube.test/rate-limited", "https://youtube.test/rate-limited"],
        )
        coverage = context["_source_diagnostics"]["youtube-rss"]["feed_coverage"]
        self.assertEqual(coverage["successful_feeds"], 2)
        self.assertEqual(coverage["failed_feeds"], 0)
        self.assertEqual(coverage["recovery_rounds"], 1)
        self.assertEqual(coverage["recovered_feeds"], 1)

    def test_rss_recovery_keeps_persistent_partial_failure_visible(self):
        feed = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config = {"sources": [{
                "id": "reddit-rss", "type": "rss", "platform": "Reddit",
                "feed_urls": ["https://reddit.test/good", "https://reddit.test/rate-limited"],
                "feed_recovery_rounds": 2, "feed_recovery_pause_seconds": 0,
            }]}
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            with mock.patch.object(
                maker_weekly, "request_bytes",
                side_effect=[feed, maker_weekly.RateLimited(0), maker_weekly.RateLimited(0), maker_weekly.RateLimited(0)],
            ), mock.patch.object(maker_weekly.time, "sleep"):
                payload = maker_weekly.collect_raw_envelope(path, datetime(2026, 8, 9, tzinfo=timezone.utc))
        status = payload["source_status"][0]
        self.assertEqual(status["status"], "error")
        coverage = status["coverage"]["feed_coverage"]
        self.assertEqual(coverage["successful_feeds"], 1)
        self.assertEqual(coverage["failed_feeds"], 1)
        self.assertEqual(coverage["recovery_rounds"], 2)
        self.assertEqual(coverage["recovered_feeds"], 0)

    def test_all_blocked_rss_feeds_are_blocked_with_diagnostics(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config = {"sources": [{
                "id": "reddit-rss", "type": "rss", "platform": "Reddit",
                "feed_urls": ["https://reddit.test/one", "https://reddit.test/two"],
            }]}
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")
            blocked = maker_weekly.AccessBlocked("HTTP 403 from provider")
            with mock.patch.object(maker_weekly, "request_bytes", side_effect=[blocked, blocked]):
                payload = maker_weekly.collect_raw_envelope(path, datetime(2026, 8, 9, tzinfo=timezone.utc))
        status = payload["source_status"][0]
        self.assertEqual(status["status"], "blocked")
        self.assertEqual(status["coverage"]["feed_coverage"]["failed_feeds"], 2)

    def test_partial_metric_enrichment_is_error_not_ok(self):
        feed = b"""<feed xmlns='http://www.w3.org/2005/Atom'>
        <entry><title>First robot</title><link href='https://youtube.test/watch?v=first01'/><published>2026-08-08T00:00:00Z</published></entry>
        <entry><title>Second robot</title><link href='https://youtube.test/watch?v=second2'/><published>2026-08-07T00:00:00Z</published></entry>
        </feed>"""
        with tempfile.TemporaryDirectory() as raw_dir:
            root = Path(raw_dir)
            config = {"lookback_days": 7, "sources": [{
                "id": "youtube-rss", "type": "rss", "platform": "YouTube",
                "feed_url": "https://youtube.test/feed", "detail_enrichment": "youtube_public",
            }]}
            path = root / "config.json"
            path.write_text(json.dumps(config), encoding="utf-8")

            def fake_enrichment(_source, items, _context):
                items[0]["metric_verification"] = {"status": "ok"}
                items[1]["metric_verification"] = {"status": "error"}

            with mock.patch.object(maker_weekly, "request_bytes", return_value=feed), \
                    mock.patch.object(maker_weekly, "enrich_rss_details", side_effect=fake_enrichment):
                payload = maker_weekly.collect_raw_envelope(path, datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc))
        status = payload["source_status"][0]
        self.assertEqual(status["status"], "error")
        self.assertEqual(status["coverage"]["detail_coverage"]["successful_items"], 1)
        self.assertEqual(status["coverage"]["detail_coverage"]["error_items"], 1)

    def test_partial_platform_coverage_does_not_reject_individually_verified_youtube_item(self):
        captured = "2026-08-12T00:00:00Z"
        item = {
            "id": "youtube-project", "source_id": "youtube-rss", "platform": "YouTube",
            "title": "I built a working robot", "url": "https://youtube.com/watch?v=project1",
            "published_at": "2026-08-07T00:00:00Z", "metrics_captured_at": captured,
            "metrics": {"views": 50000}, "metric_verification": {"status": "ok"},
            "physical_gate": {"status": "pass"}, "_raw_score": 50000,
        }
        payload = {
            "window_start": "2026-08-03T00:00:00Z",
            "config_summary": {"top_per_source": 5, "heat_thresholds": maker_weekly.resolve_heat_thresholds()},
            "source_status": [{"source_id": "youtube-rss", "platform": "YouTube", "status": "error"}],
            "stage_counts": {}, "items": [item],
        }
        result = maker_weekly.editorial_candidates_envelope(
            payload, datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        )
        self.assertEqual([candidate["id"] for candidate in result["items"]], ["youtube-project"])
        coverage = result["items"][0]["source_coverage"]
        self.assertFalse(coverage["complete"])
        self.assertEqual(coverage["scope"], "partial_platform_coverage")
        self.assertEqual(result["source_status"][0]["status"], "error")

    def test_partial_platform_coverage_does_not_rescue_unverified_item(self):
        item = {
            "id": "youtube-unverified", "source_id": "youtube-rss", "platform": "YouTube",
            "title": "Robot", "url": "https://youtube.com/watch?v=project2",
            "published_at": "2026-08-07T00:00:00Z", "metrics_captured_at": "2026-08-12T00:00:00Z",
            "metrics": {}, "metric_verification": {"status": "error"},
            "physical_gate": {"status": "pass"}, "_raw_score": 0,
        }
        payload = {
            "window_start": "2026-08-03T00:00:00Z", "config_summary": {"top_per_source": 5},
            "source_status": [{"source_id": "youtube-rss", "platform": "YouTube", "status": "error"}],
            "items": [item],
        }
        result = maker_weekly.editorial_candidates_envelope(
            payload, datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        )
        self.assertEqual(result["items"], [])

    def test_request_bytes_retries_5xx_but_not_404(self):
        server_error = urllib.error.HTTPError("https://youtube.test/feed", 500, "server error", {}, None)
        with mock.patch.object(maker_weekly.urllib.request, "urlopen", side_effect=[server_error, server_error, server_error]) as urlopen, \
                mock.patch.object(maker_weekly.time, "sleep"):
            with self.assertRaises(maker_weekly.ProviderServerError):
                maker_weekly.request_bytes("https://youtube.test/feed", 10)
        self.assertEqual(urlopen.call_count, 3)

        not_found = urllib.error.HTTPError("https://youtube.test/stale", 404, "not found", {}, None)
        with mock.patch.object(maker_weekly.urllib.request, "urlopen", side_effect=not_found) as urlopen:
            with self.assertRaises(maker_weekly.ResourceNotFound):
                maker_weekly.request_bytes("https://youtube.test/stale", 10)
        self.assertEqual(urlopen.call_count, 1)

    def test_request_bytes_honors_retry_after_and_reports_final_429(self):
        rate_limit = urllib.error.HTTPError(
            "https://reddit.test/feed", 429, "too many requests", {"Retry-After": "7"}, None,
        )
        with mock.patch.object(maker_weekly.urllib.request, "urlopen", side_effect=[rate_limit, rate_limit, rate_limit]) as urlopen, \
                mock.patch.object(maker_weekly.time, "sleep") as sleep:
            with self.assertRaises(maker_weekly.RateLimited) as raised:
                maker_weekly.request_bytes("https://reddit.test/feed", 10)
        self.assertEqual(urlopen.call_count, 3)
        self.assertEqual(raised.exception.retry_after, 7)
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [7, 7])

    def test_youtube_feed_rechecks_one_transient_404(self):
        feed = b"<feed xmlns='http://www.w3.org/2005/Atom'></feed>"
        source = {
            "id": "youtube-rss", "type": "rss", "platform": "YouTube",
            "feed_url": "https://www.youtube.com/feeds/videos.xml?channel_id=valid-channel",
            "youtube_404_recheck_delay_seconds": 0,
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
            "lookback_days": 7, "keywords": [],
        }
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[maker_weekly.ResourceNotFound("HTTP 404"), feed]) as request, \
                mock.patch.object(maker_weekly.time, "sleep"):
            self.assertEqual(maker_weekly.collect_rss(source, context), [])
        self.assertEqual(request.call_count, 2)
        coverage = context["_source_diagnostics"]["youtube-rss"]["feed_coverage"]
        self.assertEqual(coverage["successful_feeds"], 1)
        self.assertEqual(coverage["failed_feeds"], 0)

    def test_youtube_channel_page_fallback_recovers_failed_feed_with_exact_watch_date(self):
        feed_url = "https://www.youtube.com/feeds/videos.xml?channel_id=UCabcdefghijklmnopqrstuv"
        channel_page = b'''<html><script>var ytInitialData = {"contentType":"LOCKUP_CONTENT_TYPE_VIDEO","contentId":"abc123_XYZ0","metadata":{"lockupMetadataViewModel":{"title":{"content":"I built a robot"}}}};</script></html>'''
        watch_page = b'''<html><head><title>I built a robot</title><meta name="description" content="Designed, assembled and tested robot"></head><body>
        <script>"publishDate":"2026-08-07T10:00:00Z","videoDetails":{"viewCount":"50000"},"subscriberCountText":{"simpleText":"20K subscribers"}</script></body></html>'''
        source = {
            "id": "youtube-rss", "type": "rss", "platform": "YouTube", "feed_url": feed_url,
            "detail_enrichment": "youtube_public", "detail_workers": 1,
            "feed_recovery_rounds": 0, "youtube_channel_page_fallback": True,
            "youtube_page_fallback_pause_seconds": 0,
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
            "lookback_days": 7, "keywords": [],
        }
        with mock.patch.object(
            maker_weekly, "request_bytes",
            side_effect=[maker_weekly.ResourceNotFound("404"), maker_weekly.ResourceNotFound("404"), channel_page, watch_page],
        ) as request, mock.patch.object(maker_weekly.time, "sleep"):
            items = maker_weekly.collect_rss(source, context)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["published_at"], "2026-08-07T10:00:00Z")
        self.assertEqual(items[0]["metrics"]["views"], 50000)
        self.assertEqual(items[0]["metric_verification"]["provenance"], "youtube_official_channel_page_fallback")
        self.assertEqual(request.call_count, 4)
        coverage = context["_source_diagnostics"]["youtube-rss"]["feed_coverage"]
        self.assertEqual(coverage["successful_feeds"], 1)
        self.assertEqual(coverage["rss_successful_feeds"], 0)
        self.assertEqual(coverage["page_fallback_succeeded"], 1)

        status, detail = maker_weekly.source_collection_outcome(items, context["_source_diagnostics"]["youtube-rss"])
        self.assertEqual(status, "ok")
        self.assertIn("discovery targets 1/1 succeeded", detail)
        self.assertIn("channel-page fallback 1/1 succeeded", detail)
        self.assertNotIn("RSS feeds 1/1 succeeded", detail)

    def test_youtube_channel_page_fallback_fails_closed_without_exact_date(self):
        feed_url = "https://www.youtube.com/feeds/videos.xml?channel_id=UCabcdefghijklmnopqrstuv"
        channel_page = b'''<script>var ytInitialData = {"contentType":"LOCKUP_CONTENT_TYPE_VIDEO","contentId":"abc123_XYZ0","metadata":{"lockupMetadataViewModel":{"title":{"content":"Robot"}}}};</script>'''
        watch_page = b'''<html><script>"videoDetails":{"viewCount":"50000"}</script></html>'''
        source = {
            "id": "youtube-rss", "type": "rss", "platform": "YouTube", "feed_url": feed_url,
            "feed_recovery_rounds": 0, "youtube_channel_page_fallback": True,
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
            "lookback_days": 7, "keywords": [],
        }
        with mock.patch.object(
            maker_weekly, "request_bytes",
            side_effect=[maker_weekly.ResourceNotFound("404"), maker_weekly.ResourceNotFound("404"), channel_page, watch_page],
        ), mock.patch.object(maker_weekly.time, "sleep"):
            with self.assertRaises(RuntimeError):
                maker_weekly.collect_rss(source, context)

    def test_request_bytes_retries_incomplete_response(self):
        partial = http.client.IncompleteRead(b"partial", 100)
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"complete"
        with mock.patch.object(maker_weekly.urllib.request, "urlopen", side_effect=[partial, response]) as urlopen:
            self.assertEqual(maker_weekly.request_bytes("https://youtube.test/watch", 10), b"complete")
        self.assertEqual(urlopen.call_count, 2)

    def test_request_bytes_retries_read_timeout(self):
        response = mock.MagicMock()
        response.__enter__.return_value.read.return_value = b"complete"
        with mock.patch.object(maker_weekly.urllib.request, "urlopen", side_effect=[TimeoutError("read timed out"), response]) as urlopen:
            self.assertEqual(maker_weekly.request_bytes("https://youtube.test/watch", 10), b"complete")
        self.assertEqual(urlopen.call_count, 2)

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
        self.assertEqual(item["metric_verification"]["ranking_basis"], "views/25000 + channel_subscribers/10000")
        self.assertAlmostEqual(item["_raw_score"], 15394 / 25000 + 701000 / 10000)

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

    def test_reddit_unicode_url_uses_ascii_safe_public_json_fallback(self):
        old_page = b"<html><head><title>post</title></head><body>No public score here</body></html>"
        public_json = json.dumps([{"data": {"children": [{"data": {
            "score": 4900, "num_comments": 100, "author": "maker_unicode",
            "selftext": "I designed and built a working robot device, assembled and tested the prototype.",
            "url_overridden_by_dest": "https://i.redd.it/robot.jpg",
        }}]}}]).encode()
        item = {"url": "https://www.reddit.com/r/maker/comments/post123/日本語项目/", "metrics": {}, "evidence": []}
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[old_page, public_json]) as request:
            maker_weekly.enrich_reddit_public(item, 10)
        requested = [call.args[0] for call in request.call_args_list]
        self.assertTrue(all(url.isascii() for url in requested))
        self.assertTrue(requested[1].endswith("/%E6%97%A5%E6%9C%AC%E8%AA%9E%E9%A1%B9%E7%9B%AE.json?raw_json=1"))
        self.assertEqual(item["metrics"], {"score": 4900, "comments": 100})
        self.assertEqual(item["metric_verification"]["status"], "ok")
        self.assertEqual(item["author"], "maker_unicode")

    def test_reddit_metrics_try_multiple_public_json_hosts_after_403(self):
        public_json = json.dumps([{"data": {"children": [{"data": {
            "score": 5100, "num_comments": 75, "author": "actual_maker",
            "selftext": "I designed, fabricated, assembled, and tested this physical machine.",
            "url_overridden_by_dest": "https://i.redd.it/machine.jpg",
        }}]}}]).encode()
        blocked = maker_weekly.AccessBlocked("HTTP 403")
        item = {"url": "https://www.reddit.com/r/maker/comments/post123/physical_machine/", "metrics": {}, "evidence": []}
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[blocked, blocked, blocked, public_json]) as request:
            maker_weekly.enrich_reddit_public(item, 10)
        requested = [call.args[0] for call in request.call_args_list]
        self.assertEqual(requested[-1], "https://www.reddit.com/comments/post123.json?raw_json=1")
        self.assertEqual(item["metrics"], {"score": 5100, "comments": 75})
        self.assertEqual(item["metric_verification"]["status"], "ok")

    def test_reddit_all_public_metric_paths_blocked_is_blocked(self):
        blocked = maker_weekly.AccessBlocked("HTTP 403")
        item = {"url": "https://www.reddit.com/r/maker/comments/post123/physical_machine/", "metrics": {}, "evidence": []}
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[blocked] * 5):
            with self.assertRaises(maker_weekly.AccessBlocked):
                maker_weekly.enrich_reddit_public(item, 10)

    def test_reddit_installed_app_oauth_uses_no_client_secret_and_batches_metrics(self):
        source = {
            "id": "reddit-rss", "type": "rss", "platform": "Reddit",
            "installed_client_id": "approved-public-client", "user_agent": "desktop:maker-weekly:v0.11 (by /u/testmaintainer)",
        }
        context = {"timeout": 10}
        items = [{
            "id": "candidate", "url": "https://www.reddit.com/r/maker/comments/post123/machine/",
            "metrics": {}, "evidence": [],
        }]
        token = {"access_token": "short-lived-token"}
        listing = {"data": {"children": [{"data": {
            "id": "post123", "score": 470, "num_comments": 45, "author": "actual_maker",
            "selftext": "I designed, fabricated, assembled and tested this working machine.",
            "url_overridden_by_dest": "https://i.redd.it/machine.jpg",
        }}]}}
        with mock.patch.object(maker_weekly, "request_json", side_effect=[token, listing]) as request:
            resolved = maker_weekly.enrich_reddit_installed_batch(source, items, context)
        token_call, listing_call = request.call_args_list
        self.assertEqual(token_call.args[0], "https://www.reddit.com/api/v1/access_token")
        self.assertIn(b"grants%2Finstalled_client", token_call.kwargs["data"])
        self.assertEqual(token_call.kwargs["headers"]["Authorization"], "Basic YXBwcm92ZWQtcHVibGljLWNsaWVudDo=")
        self.assertIn("id=t3_post123", listing_call.args[0])
        self.assertEqual(items[0]["metrics"], {"score": 470, "comments": 45})
        self.assertEqual(items[0]["metric_verification"]["provenance"], "reddit_oauth")
        self.assertEqual(resolved, {"candidate"})

    def test_reddit_fallback_accepts_audited_browser_evidence(self):
        with tempfile.TemporaryDirectory() as raw_dir:
            evidence_path = Path(raw_dir) / "social-evidence.json"
            evidence_path.write_text(json.dumps({"items": [{
                "platform": "Reddit", "title": "I built a machine",
                "url": "https://www.reddit.com/r/maker/comments/post123/machine/",
                "source_url": "https://www.reddit.com/r/maker/comments/post123/machine/",
                "provenance": "browser_visible", "captured_at": "2026-08-12T10:00:00Z",
                "metrics": {"score": 480, "comments": 30},
            }]}), encoding="utf-8")
            source = {"id": "reddit-rss", "platform": "Reddit", "browser_evidence_file": str(evidence_path)}
            context = {"timeout": 10, "config_dir": Path(raw_dir)}
            item = {"id": "candidate", "url": "https://www.reddit.com/r/maker/comments/post123/machine/", "metrics": {}, "evidence": []}
            maker_weekly.enrich_reddit_fallback(source, [item], context)
        self.assertEqual(item["metrics"], {"score": 480, "comments": 30})
        self.assertEqual(item["metric_verification"]["provenance"], "browser_visible")

    def test_reddit_anonymous_discovery_never_becomes_verified_heat(self):
        source = {"id": "reddit-rss", "platform": "Reddit"}
        context = {"timeout": 10, "config_dir": Path(".")}
        item = {"id": "candidate", "url": "https://www.reddit.com/r/maker/comments/post123/machine/", "metrics": {}, "evidence": []}
        with mock.patch.dict(maker_weekly.os.environ, {}, clear=True):
            maker_weekly.enrich_reddit_fallback(source, [item], context)
        self.assertEqual(item["metric_verification"]["status"], "blocked")
        self.assertEqual(item["metric_verification"]["provenance"], "anonymous_discovery")
        self.assertNotIn("score", item["metrics"])

    def test_reddit_official_weekly_rss_rank_is_labeled_proxy_heat(self):
        feed_url = "https://www.reddit.com/r/maker+robotics/top/.rss?t=week&limit=100"
        source = {
            "id": "reddit-rss", "platform": "Reddit", "feed_urls": [feed_url],
            "weekly_rss_rank_fallback": {"enabled": True},
        }
        context = {"timeout": 10, "config_dir": Path(".")}
        item = {
            "id": "candidate", "platform": "Reddit",
            "url": "https://www.reddit.com/r/maker/comments/post123/machine/",
            "metrics": {"weekly_rss_rank": 10, "rss_feed_url": feed_url},
            "metrics_captured_at": "2026-08-12T10:00:00Z", "evidence": [],
        }
        with mock.patch.dict(maker_weekly.os.environ, {}, clear=True):
            maker_weekly.enrich_reddit_fallback(source, [item], context)
        verification = item["metric_verification"]
        self.assertEqual(verification["status"], "ok")
        self.assertEqual(verification["provenance"], "reddit_weekly_rss_rank")
        self.assertFalse(verification["exact_score_available"])
        gate = maker_weekly.evaluate_heat_gate(item, datetime(2026, 8, 9, tzinfo=timezone.utc))
        self.assertEqual(gate["status"], "pass")
        self.assertEqual(gate["heat_method"], "reddit_weekly_rss_rank")

    def test_reddit_weekly_rss_rank_fifty_one_fails_and_exact_low_score_cannot_be_rescued(self):
        feed_url = "https://www.reddit.com/r/maker+robotics/top/.rss?t=week&limit=100"
        base = {
            "platform": "Reddit", "metrics_captured_at": "2026-08-12T10:00:00Z",
            "metric_verification": {
                "status": "ok", "provenance": "reddit_weekly_rss_rank",
                "source_url": feed_url, "exact_score_available": False,
            },
        }
        rank_fifty_one = {**base, "metrics": {"weekly_rss_rank": 51, "rss_feed_url": feed_url}}
        exact_low = {
            **base,
            "metrics": {"score": 400, "comments": 99, "weekly_rss_rank": 1, "rss_feed_url": feed_url},
        }
        as_of = datetime(2026, 8, 9, tzinfo=timezone.utc)
        self.assertEqual(maker_weekly.evaluate_heat_gate(rank_fifty_one, as_of)["status"], "fail")
        self.assertEqual(maker_weekly.evaluate_heat_gate(exact_low, as_of)["status"], "fail")

    def test_reddit_rank_proxy_rejects_non_combined_or_nonofficial_feed(self):
        as_of = datetime(2026, 8, 9, tzinfo=timezone.utc)
        for feed_url in (
            "https://www.reddit.com/r/maker/top/.rss?t=week",
            "https://example.com/r/maker+robotics/top/.rss?t=week",
            "https://www.reddit.com/r/maker+robotics/new/.rss?t=week",
        ):
            item = {
                "platform": "Reddit", "metrics_captured_at": "2026-08-12T10:00:00Z",
                "metrics": {"weekly_rss_rank": 1, "rss_feed_url": feed_url},
                "metric_verification": {
                    "status": "ok", "provenance": "reddit_weekly_rss_rank",
                    "source_url": feed_url, "exact_score_available": False,
                },
            }
            with self.subTest(feed_url=feed_url):
                self.assertEqual(maker_weekly.evaluate_heat_gate(item, as_of)["status"], "fail")

    def test_instagram_fallback_uses_graph_relay_evidence(self):
        source = {
            "id": "instagram-web", "type": "instagram_fallback", "platform": "Instagram",
            "relay_url": "https://relay.example.test/social", "hashtags": ["makerproject"],
        }
        context = {
            "timeout": 10, "limit": 10, "config_dir": Path("."),
            "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        }
        response = {"items": [{
            "platform": "Instagram", "title": "Printed kinetic sculpture",
            "url": "https://www.instagram.com/p/ABC123/", "source_url": "https://graph.facebook.com/v23.0/media123",
            "provenance": "instagram_graph", "published_at": "2026-08-07T10:00:00Z",
            "captured_at": "2026-08-12T10:00:00Z", "metrics": {"likes": 4900, "comments": 200},
            "author": "small_maker",
        }]}
        with mock.patch.dict(maker_weekly.os.environ, {}, clear=True), \
                mock.patch.object(maker_weekly, "request_json", return_value=response) as request:
            items = maker_weekly.collect_instagram_fallback(source, context)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["metrics"], {"likes": 4900, "comments": 200})
        self.assertEqual(items[0]["metric_verification"]["provenance"], "instagram_graph")
        self.assertEqual(request.call_args.kwargs["headers"]["Content-Type"], "application/json")

    def test_instagram_anonymous_html_is_discovery_only(self):
        source = {"id": "instagram-web", "type": "instagram_fallback", "platform": "Instagram"}
        context = {"timeout": 10, "config_dir": Path(".")}
        discovery = {
            "id": "candidate", "url": "https://www.instagram.com/p/ABC123/", "metrics": {"likes": 99999, "comments": 999},
            "metrics_captured_at": "2026-08-12T10:00:00Z", "evidence": [], "_raw_score": 100998,
        }
        with mock.patch.dict(maker_weekly.os.environ, {}, clear=True), \
                mock.patch.object(maker_weekly, "collect_web_html", return_value=[discovery]):
            items = maker_weekly.collect_instagram_fallback(source, context)
        self.assertEqual(items[0]["metrics"], {})
        self.assertIsNone(items[0]["metrics_captured_at"])
        self.assertEqual(items[0]["metric_verification"]["status"], "blocked")

    def test_instagram_empty_javascript_shell_is_blocked_not_empty(self):
        source = {"id": "instagram-web", "type": "instagram_fallback", "platform": "Instagram"}
        context = {"timeout": 10, "config_dir": Path(".")}
        with mock.patch.dict(maker_weekly.os.environ, {}, clear=True), \
                mock.patch.object(maker_weekly, "collect_web_html", side_effect=RuntimeError("listing returned no matching public project links; it may require JavaScript or login")):
            with self.assertRaises(maker_weekly.AccessBlocked):
                maker_weekly.collect_instagram_fallback(source, context)

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
        self.assertEqual(items[0]["physical_page"]["source_url"], "https://example.test/projects/maker/robot-arm")

    def test_web_html_reports_access_challenge(self):
        source = {
            "id": "blocked", "type": "web_html", "platform": "Blocked",
            "listing_url": "https://blocked.test/discover", "link_pattern": r"/projects/",
        }
        context = {"timeout": 10, "limit": 5}
        with mock.patch.object(maker_weekly, "request_bytes", return_value=b"<title>Just a moment...</title><p>Enable JavaScript and cookies to continue</p>"):
            with self.assertRaises(maker_weekly.AccessBlocked):
                maker_weekly.collect_web_html(source, context)

    def test_dated_archive_expands_every_target_week_day_and_filters_detail_dates(self):
        source = {
            "id": "archive", "type": "dated_archive", "platform": "Hackaday",
            "archive_url_template": "https://example.test/{year}/{month}/{day}/",
            "link_pattern": r"^https://example\.test/2026/08/[0-9]{2}/project$", "keywords": ["robot"],
        }
        context = {
            "timeout": 10, "limit": 20, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        }
        urls = maker_weekly.archive_urls(source, context)
        self.assertEqual(len(urls), 7)
        archives = [f'<a href="{url}project">Project</a>'.encode() for url in urls]
        detail = b'''<html><head><meta property="og:title" content="I built a robot"/>
        <meta property="article:published_time" content="2026-08-05T12:00:00Z"/>
        <meta property="og:image" content="https://example.test/robot.jpg"/></head>
        <body>I designed, fabricated, assembled and tested this working robot prototype.</body></html>'''
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=archives + [detail] * 7):
            items = maker_weekly.collect_dated_archive(source, context)
        self.assertGreaterEqual(len(items), 1)
        self.assertTrue(all(item["published_at"] == "2026-08-05T12:00:00Z" for item in items))

    def test_kickstarter_kicktraq_uses_official_widget_metrics(self):
        listing = b'''<html><a href="/projects/maker/robot-arm/">Robot Arm</a></html>'''
        payload = {
            "name": "Open Hardware Robot Arm", "blurb": "A DIY robot arm built and tested from scratch.",
            "goal": 10000, "pledged": 30000, "state": "live", "currency": "USD", "backers_count": 250,
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

    def test_kickstarter_same_issue_cache_recovers_failed_widget(self):
        listing = b'''<html><a href="/projects/maker/robot-arm/">Robot Arm</a></html>'''
        payload = {
            "name": "Open Hardware Robot Arm", "blurb": "A DIY robot arm built and tested from scratch.",
            "goal": 10000, "pledged": 30000, "state": "live", "currency": "USD", "backers_count": 250,
            "usd_pledged": "30000", "staff_pick": True, "launched_at": 1785859200,
            "deadline": 1788451200, "creator": {"name": "Small Maker Team"},
            "category": {"parent_name": "Technology", "name": "Robots"},
            "urls": {"web": {"project": "https://www.kickstarter.com/projects/maker/robot-arm"}},
        }
        source = {
            "id": "kickstarter", "type": "kickstarter_kicktraq", "platform": "Kickstarter",
            "listing_url": "https://www.kicktraq.com/categories/technology/robots/?sort=new",
            "keywords": ["robot"], "detail_workers": 1,
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
        }
        with tempfile.TemporaryDirectory() as raw_dir:
            source["evidence_cache_path"] = str(Path(raw_dir) / "kickstarter.json")
            widget = f'<script>window.current_project = "{maker_weekly.html.escape(json.dumps(payload))}";</script>'.encode()
            with mock.patch.object(maker_weekly, "request_bytes", side_effect=[listing, widget]):
                live = maker_weekly.collect_kickstarter_kicktraq(source, context)
            blocked = maker_weekly.AccessBlocked("temporary challenge")
            with mock.patch.object(maker_weekly, "request_bytes", side_effect=[listing, blocked]):
                cached = maker_weekly.collect_kickstarter_kicktraq(source, context)
        self.assertEqual(live[0]["metrics"]["backers"], 250)
        self.assertEqual(cached[0]["metrics"]["backers"], 250)
        self.assertEqual(cached[0]["metric_verification"]["provenance"], "kickstarter_official_widget_cache")

    def test_kickstarter_cache_rejects_different_issue(self):
        context = {
            "since": datetime(2026, 8, 10, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 16, tzinfo=timezone.utc),
        }
        entry = {
            "captured_at": "2026-08-12T00:00:00Z", "widget_url": "https://kickstarter.test/widget",
            "payload": {"launched_at": 1785859200},
        }
        self.assertIsNone(maker_weekly.cached_kickstarter_payload(entry, context))

    def test_kickstarter_non_usd_widget_amount_is_audit_only(self):
        listing = b'''<html><a href="/projects/maker/stepsafe-kids/">StepSafe Kids</a></html>'''
        payload = {
            "name": "StepSafe Kids", "blurb": "A physical prototype built and tested by a small team.",
            "goal": 10000, "pledged": 11500, "state": "live", "currency": "CAD", "backers_count": 47,
            "usd_pledged": "8411", "static_usd_rate": 0.7314, "fx_rate": 0.73,
            "usd_exchange_rate": 0.73, "current_currency": "USD", "usd_type": "international",
            "staff_pick": False, "launched_at": 1785859200,
            "deadline": 1788451200, "creator": {"name": "Small Maker Team"},
            "category": {"parent_name": "Technology", "name": "Hardware"},
            "urls": {"web": {"project": "https://www.kickstarter.com/projects/maker/stepsafe-kids"}},
        }
        widget = f'<html><script>window.current_project = "{maker_weekly.html.escape(json.dumps(payload))}";</script></html>'.encode()
        source = {
            "id": "kickstarter", "type": "kickstarter_kicktraq", "platform": "Kickstarter",
            "listing_url": "https://www.kicktraq.com/categories/technology/hardware/?sort=new",
            "keywords": ["hardware", "prototype"], "detail_workers": 1,
        }
        context = {
            "timeout": 10, "limit": 5, "since": datetime(2026, 8, 3, tzinfo=timezone.utc),
            "as_of": datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc),
            "heat_thresholds": maker_weekly.resolve_heat_thresholds(),
        }
        with mock.patch.object(maker_weekly, "request_bytes", side_effect=[listing, widget]):
            item = maker_weekly.collect_kickstarter_kicktraq(source, context)[0]
        self.assertNotIn("usd_pledged", item["metrics"])
        self.assertEqual(item["metrics"]["pledged"], 11500)
        self.assertEqual(item["metrics"]["reported_usd_pledged"], 8411)
        self.assertEqual(item["metrics"]["currency_conversion"]["status"], "unverified")
        self.assertFalse(item["metrics"]["currency_conversion"]["admissible_for_heat_gate"])
        self.assertEqual(item["metrics"]["currency_conversion"]["widget_static_usd_rate"], 0.7314)
        gate = maker_weekly.evaluate_heat_gate(item, context["as_of"])
        self.assertEqual(gate["status"], "pass")
        self.assertEqual(gate["amount_basis"], "non_usd_conversion_unverified")

    def test_kickstarter_verified_non_usd_conversion_requires_complete_audit_fields(self):
        captured = "2026-08-12T00:00:00Z"
        base = {
            "platform": "Kickstarter", "metrics_captured_at": captured,
            "metrics": {"currency": "CAD", "usd_pledged": 6000, "backers": 10},
        }
        incomplete = json.loads(json.dumps(base))
        incomplete["metrics"]["currency_conversion"] = {"status": "verified", "admissible_for_heat_gate": True}
        self.assertEqual(maker_weekly.evaluate_heat_gate(incomplete, datetime(2026, 8, 9, tzinfo=timezone.utc))["status"], "fail")
        complete = json.loads(json.dumps(base))
        complete["metrics"]["currency_conversion"] = {
            "status": "verified", "admissible_for_heat_gate": True,
            "source_currency": "CAD", "target_currency": "USD",
            "source_amount": 8000, "rate": 0.75, "converted_amount_usd": 6000,
            "source_url": "https://official.example.test/rates/cad-usd",
            "captured_at": captured,
        }
        gate = maker_weekly.evaluate_heat_gate(complete, datetime(2026, 8, 9, tzinfo=timezone.utc))
        self.assertEqual(gate["status"], "pass")
        self.assertEqual(gate["amount_basis"], "verified_conversion")

        inconsistent = json.loads(json.dumps(complete))
        inconsistent["metrics"]["currency_conversion"]["rate"] = 0.5
        self.assertEqual(maker_weekly.evaluate_heat_gate(inconsistent, datetime(2026, 8, 9, tzinfo=timezone.utc))["status"], "fail")

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

    def test_zero_gate_accepts_editorial_report_of_a_documented_physical_build(self):
        item = {
            "title": "Robotic Screw And Bolt Sorter Seeks A New Challenge",
            "summary": "A maker created an automatic robot machine with a camera to sort bolts and screws.",
            "platform": "Hackaday", "url": "https://hackaday.test/bolt-sorter",
        }
        page = {
            "source_url": item["url"],
            "text": (
                "Aad created a working automatic sorting machine. A camera and machine vision detect each screw. "
                "A conveyor feeds the parts onto an illuminated platform, then a robotic gripper picks them up. "
                "The mechanism was built, assembled, tested, and improved as a physical prototype. "
                "Site navigation: latest stories, food hacks, buying guide, recipes."
            ),
            "media_urls": ["https://hackaday.test/images/bolt-sorter.jpg"],
            "structured_steps": 4,
        }
        gate = maker_weekly.derive_physical_gate(item, page)
        self.assertEqual(gate["status"], "pass")
        self.assertTrue(all(gate["checks"].values()))

    def test_zero_gate_rejects_media_news_despite_unrelated_page_chrome(self):
        item = {
            "title": "A new AI moderator is coming",
            "summary": "A policy update about an LLM moderation service.",
            "platform": "The Verge", "url": "https://theverge.test/ai-news",
        }
        page = {
            "source_url": item["url"],
            "text": (
                "The article discusses a software policy update. Related stories and navigation mention a maker "
                "who built, assembled and tested a working robot machine with a camera, motor and circuit."
            ),
            "media_urls": ["https://theverge.test/images/site-card.jpg"],
            "structured_steps": 6,
        }
        gate = maker_weekly.derive_physical_gate(item, page)
        self.assertEqual(gate["status"], "fail")
        self.assertFalse(gate["checks"]["physical_is_core"])

    def test_instructables_steps_and_photo_prove_lia_built_result_without_result_words(self):
        item = {
            "title": "LIA — an Open-Source, Off-Grid LoRa Pet Tracker", "platform": "Instructables",
            "url": "https://www.instructables.com/LIA-an-Open-Source-Off-Grid-LoRa-Pet-Asset-Tracker/", "author": "Jon G Aguado",
        }
        page = {
            "source_url": item["url"],
            "text": "LoRa pet tracker device with sensor circuit, battery enclosure, PCB wiring and firmware configuration.",
            "media_urls": ["https://content.instructables.com/FQI/UT2J/MS6P5N4X/FQIUT2JMS6P5N4X.png"],
            "structured_steps": 9, "author": item["author"],
        }
        gate = maker_weekly.derive_physical_gate(item, page)
        self.assertEqual(gate["status"], "pass")
        self.assertTrue(gate["checks"]["built_result_visible"])

    def test_instructables_photo_and_clear_process_prove_steering_wheel_result(self):
        item = {
            "title": "Build Your Own Steering Wheel Gaming Setup", "platform": "Instructables",
            "url": "https://www.instructables.com/Build-Your-Own-Steering-Wheel-Gaming-Setup/", "author": "Upside Down Labs",
        }
        page = {
            "source_url": item["url"],
            "text": "DIY steering wheel device with a 3D printed enclosure, sensor circuit, wiring, CAD and drilled metal parts.",
            "media_urls": ["https://content.instructables.com/FXP/JKJZ/MS6P3XX7/FXPJKJZMS6P3XX7.jpg"],
            "structured_steps": 0, "author": item["author"],
        }
        gate = maker_weekly.derive_physical_gate(item, page)
        self.assertEqual(gate["status"], "pass")
        self.assertTrue(gate["checks"]["built_result_visible"])

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

    def test_raw_audit_renderer_lists_failed_feed_urls(self):
        payload = {
            "selection_method": "raw-discovery-audit-only", "as_of": "2026-08-09T23:59:59Z",
            "config_summary": {"final_top": 15}, "items": [],
            "source_status": [{
                "source_id": "youtube-rss", "platform": "YouTube", "status": "error", "count": 1,
                "detail": "RSS feeds 28/29 succeeded",
                "coverage": {"feed_coverage": {"failures": [{
                    "url": "https://www.youtube.com/feeds/videos.xml?channel_id=stale",
                    "category": "not_found", "http_status": 404, "error": "HTTP 404 from provider",
                }]}},
            }],
        }
        report = maker_weekly.render_markdown(payload)
        self.assertIn("Feed 失败明细", report)
        self.assertIn("channel_id=stale", report)
        self.assertIn("HTTP 404", report)

    def test_execution_time_heat_can_qualify_an_older_completed_week(self):
        item = {"platform": "YouTube", "url": "https://youtube.com/watch?v=abcdef1", "metrics": {"views": 999999}, "metrics_captured_at": "2026-08-12T00:00:00Z"}
        gate = maker_weekly.evaluate_heat_gate(item, datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc))
        self.assertEqual(gate["status"], "pass")
        self.assertEqual(gate["captured_at"], "2026-08-12T00:00:00Z")
        self.assertEqual(gate["observation_policy"], "execution_time")

    def test_dynamic_heat_without_real_capture_time_fails(self):
        item = {"platform": "Reddit", "url": "https://reddit.com/r/maker/comments/abc/post", "metrics": {"score": 5000, "comments": 1}}
        gate = maker_weekly.evaluate_heat_gate(item, datetime(2026, 8, 9, 23, 59, 59, tzinfo=timezone.utc))
        self.assertEqual(gate["status"], "fail")
        self.assertIn("真实指标采集时间", gate["observed"])

    def test_zero_gate_rejects_mailbag_even_when_products_and_build_words_appear(self):
        item = {
            "title": "What's in the Mail? EBIKE ESC, Spot Welder & More!", "platform": "YouTube",
            "url": "https://youtube.test/watch?v=mailbag", "author": "Electronics Channel",
        }
        page = {
            "source_url": item["url"], "author": item["author"],
            "text": "What's in the mail? Unboxing a motor controller, battery, welder and DIY hardware.",
            "media_urls": ["https://i.ytimg.com/vi/mailbag/maxresdefault.jpg"], "structured_steps": 3,
        }
        gate = maker_weekly.derive_physical_gate(item, page)
        self.assertEqual(gate["status"], "fail")
        self.assertTrue(gate.get("exclusion_matches"))

    def test_formal_default_has_all_13_platforms_and_broad_social_rss(self):
        config_path = Path(__file__).parents[1] / "assets" / "config.example.json"
        config = maker_weekly.load_config(config_path)
        self.assertEqual(len(config["sources"]), 13)
        by_id = {source["id"]: source for source in config["sources"]}
        self.assertTrue(by_id["kickstarter"]["enabled"])
        self.assertTrue(by_id["youtube-rss"]["enabled"])
        self.assertTrue(by_id["reddit-rss"]["enabled"])
        self.assertEqual(by_id["reddit-rss"]["detail_enrichment"], "reddit_fallback")
        self.assertTrue(by_id["reddit-rss"]["weekly_rss_rank_fallback"]["enabled"])
        self.assertEqual(config["heat_thresholds"]["reddit"]["weekly_rss_rank"], 50)
        self.assertEqual(by_id["instagram-web"]["type"], "instagram_fallback")
        self.assertNotIn("required_patterns", by_id["youtube-rss"])
        self.assertNotIn("required_patterns", by_id["reddit-rss"])
        self.assertGreaterEqual(len(by_id["youtube-rss"]["feed_urls"]), 80)
        self.assertGreater(by_id["youtube-rss"]["feed_pause_seconds"], 0)
        self.assertGreaterEqual(by_id["youtube-rss"]["feed_recovery_rounds"], 2)
        self.assertLessEqual(by_id["youtube-rss"]["detail_workers"], 2)
        self.assertTrue(by_id["youtube-rss"]["youtube_channel_page_fallback"])
        self.assertGreaterEqual(by_id["reddit-rss"]["feed_pause_seconds"], 2)
        self.assertGreaterEqual(by_id["reddit-rss"]["feed_recovery_rounds"], 2)
        self.assertLessEqual(by_id["reddit-rss"]["detail_workers"], 2)
        self.assertLessEqual(len(by_id["reddit-rss"]["feed_urls"]), 2)
        self.assertTrue(all("limit=100" in url for url in by_id["reddit-rss"]["feed_urls"]))
        reddit_communities = set()
        for url in by_id["reddit-rss"]["feed_urls"]:
            bundle = url.split("/r/", 1)[1].split("/top/", 1)[0]
            reddit_communities.update(bundle.split("+"))
        self.assertGreaterEqual(len(reddit_communities), 20)

    def test_social_evidence_rejects_search_snippet_or_third_party_metrics(self):
        record = {
            "platform": "Instagram", "title": "Maker project",
            "url": "https://www.instagram.com/p/ABC123/", "source_url": "https://search.example.test/result",
            "provenance": "browser_visible", "captured_at": "2026-08-12T10:00:00Z",
            "metrics": {"likes": 6000, "comments": 100},
        }
        with self.assertRaises(maker_weekly.ConfigError):
            maker_weekly.validate_social_evidence_record(record, "Instagram", require_title=True)

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
