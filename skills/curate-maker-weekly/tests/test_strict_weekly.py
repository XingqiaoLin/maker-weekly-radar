import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import strict_weekly  # noqa: E402


class StrictWeeklyTests(unittest.TestCase):
    def strict_candidate_and_decision(self, index, platform, score):
        candidate_id = f"project-{index}"
        url = f"https://example.test/{platform.lower().replace(' ', '-')}/{index}"
        candidate = {
            "id": candidate_id, "platform": platform, "title": f"Physical maker project {index}",
            "url": url, "canonical_url": url, "published_at": "2026-08-05T10:00:00Z",
            "evidence": [url], "time_gate": {"status": "pass", "entry_type": "first_release"},
            "heat_gate": {"status": "pass", "observed": "verified platform threshold", "threshold": "threshold", "captured_at": "2026-08-12T00:00:00Z", "evidence_url": url},
            "physical_gate": {"status": "pass", "checks": {"creator_made_physical": True, "physical_is_core": True, "built_result_visible": True, "human_process_visible": True}, "evidence": [{"type": "video", "url": url}]},
        }
        evidence = "The original creator documents design, fabrication, assembly, testing, and iteration."
        decision = {
            "id": candidate_id, "category": "极客硬核", "entry_type": "first_release", "first_seen_date": "2026-08-05",
            "heat_gate": candidate["heat_gate"],
            "creator": {"name": f"Maker {index}", "background": "Independent maker documented on the original page.", "evidence_urls": [url]},
            "project_description": "A completed physical machine with a documented real-world purpose.",
            "build_path": "CAD, fabrication, electronics assembly, testing, and iterative revisions.",
            "category_gate": {"passed": True, "evidence": evidence, "evidence_url": url},
            "project_gate_evidence": {
                key: {"passed": True, "evidence": evidence, "evidence_url": url, "evidence_locator": f"Build section {key}"}
                for key in strict_weekly.PROJECT_GATE_KEYS
            },
            "necessary_conditions": {key: {"passed": True, "evidence": evidence} for key in strict_weekly.NECESSARY_KEYS},
            "excellence": {"direction": "technical_engineering", "benchmark_statement": "Comparable builds use kits, but this one documents a self-designed physical mechanism.", "evidence_url": url},
            "red_lines": {key: {"passed": True, "evidence": evidence} for key in strict_weekly.RED_LINE_KEYS},
            "scores": {
                "creation_investment": score, "process_visibility": score, "impact_resonance": score,
                "completion": score, "cross_platform_continuity": score, "diversity_breakout": score,
            },
            "selection_reason": "It passes every mandatory gate with original evidence and a concrete physical result.",
        }
        return candidate, decision

    def test_duplicate_platform_status_failure_cannot_be_hidden_by_success(self):
        statuses = [
            {"platform": "YouTube", "status": "error"},
            {"platform": "YouTube", "status": "ok"},
            {"platform": "Reddit", "status": "empty"},
        ]
        aggregated = strict_weekly.aggregate_platform_statuses(statuses)
        self.assertEqual(aggregated["youtube"], "error")
        self.assertEqual(aggregated["reddit"], "empty")

    def test_last_complete_week(self):
        window = strict_weekly.last_complete_week(date(2026, 8, 12))
        self.assertEqual(window["week_start"], "2026-08-03")
        self.assertEqual(window["week_end"], "2026-08-09")
        self.assertNotIn("previous_snapshot_date", window)

    def test_partial_social_coverage_warning_does_not_remove_existing_candidates(self):
        payload = {
            "source_status": [
                {"source_id": "youtube-rss", "platform": "YouTube", "status": "error"},
                {"source_id": "reddit-rss", "platform": "Reddit", "status": "ok"},
            ],
            "stage_counts": {"editorial_candidates": 1},
            "items": [{
                "id": "youtube-project", "platform": "YouTube", "title": "Built robot",
                "url": "https://youtube.com/watch?v=project1", "published_at": "2026-08-07T00:00:00Z",
                "metrics": {"views": 50000}, "metrics_captured_at": "2026-08-12T00:00:00Z",
                "physical_gate": {"status": "pass"},
            }],
        }
        start, end = strict_weekly.week_bounds("2026-08-03", "2026-08-09")
        prepared = strict_weekly.prepare_payload(payload, start, end)
        self.assertEqual(len(prepared["items"]), 1)
        self.assertEqual(prepared["items"][0]["heat_gate"]["status"], "pass")
        self.assertEqual(prepared["issue_stats"]["platforms_searched"], 1)
        self.assertIn("未完成完整检索", prepared["issue_stats"]["coverage_warning"])
        self.assertIn("仍可参与严格评审", prepared["issue_stats"]["coverage_warning"])

    def test_heat_gates_are_hard_thresholds(self):
        github = strict_weekly.heat_gate({"platform": "GitHub", "metrics": {"stars": 999}, "url": "https://github.com/x/y"})
        kickstarter_low = strict_weekly.heat_gate({"platform": "Kickstarter", "metrics": {"backers": 39}, "url": "https://kickstarter.com/x"})
        kickstarter = strict_weekly.heat_gate({"platform": "Kickstarter", "metrics": {"backers": 40}, "url": "https://kickstarter.com/x"})
        youtube_rss = strict_weekly.heat_gate({"platform": "YouTube", "metrics": {"feed_host": "youtube.com"}, "url": "https://youtube.com/x"})
        self.assertEqual(github["status"], "fail")
        self.assertEqual(kickstarter_low["status"], "fail")
        self.assertEqual(kickstarter["status"], "pass")
        self.assertEqual(youtube_rss["status"], "unknown")

    def test_strict_reddit_gate_accepts_labeled_official_weekly_rank_proxy(self):
        feed_url = "https://www.reddit.com/r/maker+robotics/top/.rss?t=week&limit=100"
        item = {
            "platform": "Reddit", "url": "https://www.reddit.com/r/maker/comments/post123/machine/",
            "metrics": {"weekly_rss_rank": 10, "rss_feed_url": feed_url},
            "metric_verification": {
                "status": "ok", "provenance": "reddit_weekly_rss_rank",
                "source_url": feed_url, "exact_score_available": False,
            },
        }
        gate = strict_weekly.heat_gate(item)
        self.assertEqual(gate["status"], "pass")
        self.assertEqual(gate["heat_method"], "reddit_weekly_rss_rank")

    def test_strict_heat_gate_rejects_unverified_non_usd_kickstarter_amount(self):
        step_safe = {
            "platform": "Kickstarter", "url": "https://kickstarter.com/stepsafe",
            "metrics": {
                "currency": "CAD", "reported_usd_pledged": 8411, "backers": 47,
                "currency_conversion": {"status": "unverified", "admissible_for_heat_gate": False},
            },
        }
        xtra_maker = {
            "platform": "Kickstarter", "url": "https://kickstarter.com/xtramaker",
            "metrics": {
                "currency": "HKD", "reported_usd_pledged": 460475, "backers": 107,
                "currency_conversion": {"status": "unverified", "admissible_for_heat_gate": False},
            },
        }
        self.assertEqual(strict_weekly.heat_gate(step_safe)["status"], "pass")
        self.assertEqual(strict_weekly.heat_gate(xtra_maker)["status"], "pass")

    def test_time_gate_allows_only_current_week_first_release(self):
        payload = {
            "source_status": [{"status": "ok", "platform": "GitHub"}],
            "items": [
                {"id": "new", "platform": "GitHub", "title": "New", "url": "https://github.com/a/new", "published_at": "2026-08-05T10:00:00Z", "metrics": {"stars": 1000}},
                {"id": "old", "platform": "GitHub", "title": "Old", "url": "https://github.com/a/old", "published_at": "2026-07-01T10:00:00Z", "metrics": {"stars": 1000}},
            ],
        }
        start, end = strict_weekly.week_bounds("2026-08-03", "2026-08-09")
        prepared = strict_weekly.prepare_payload(payload, start, end)
        self.assertEqual(prepared["items"][0]["time_gate"]["entry_type"], "first_release")
        self.assertEqual(prepared["items"][1]["time_gate"]["status"], "fail")
        self.assertIn("旧项目本周更新或重新传播也不接受", prepared["items"][1]["time_gate"]["reason"])
        self.assertTrue(prepared["week"]["strict_current_week_only"])

    def test_breakout_decision_is_rejected(self):
        candidate = {
            "id": "old", "platform": "GitHub", "title": "Old project",
            "url": "https://github.com/a/old", "published_at": "2020-01-01T00:00:00Z",
        }
        start, end = strict_weekly.week_bounds("2026-08-03", "2026-08-09")
        errors = strict_weekly.validate_decision({"entry_type": "breakout"}, candidate, start, end)
        self.assertIn("entry_type must be first_release", errors)

    def test_select_valid_strict_project(self):
        candidate = {
            "id": "project-1",
            "platform": "GitHub",
            "title": "Open hardware arm",
            "url": "https://github.com/maker/arm",
            "canonical_url": "https://github.com/maker/arm",
            "published_at": "2026-08-05T10:00:00Z",
            "metrics": {"stars": 1200},
            "metrics_captured_at": "2026-08-09T23:00:00Z",
            "evidence": ["https://github.com/maker/arm"],
            "time_gate": {"status": "pass", "entry_type": "first_release"},
            "heat_gate": {"status": "pass", "observed": "stars=1200", "threshold": "1,000 Stars", "captured_at": "2026-08-09T23:00:00Z", "evidence_url": "https://github.com/maker/arm"},
            "physical_gate": {"status": "pass", "checks": {"creator_made_physical": True, "physical_is_core": True, "built_result_visible": True, "human_process_visible": True}, "evidence": [{"type": "video", "url": "https://github.com/maker/arm"}]},
        }
        researched = {
            "week": {"start": "2026-08-03T00:00:00Z", "end": "2026-08-09T23:59:59Z", "timezone": "UTC"},
            "issue_stats": {"platforms_searched": 1, "initial_candidates": 1},
            "items": [candidate],
        }
        evidence = "Creator documents CAD, fabrication, assembly, testing, and iteration on the original repository."
        decisions = {
            "items": [{
                "id": "project-1",
                "category": "极客硬核",
                "entry_type": "first_release",
                "first_seen_date": "2026-08-05",
                "heat_gate": {"status": "pass", "observed": "1,200 Stars", "threshold": "1,000 Stars", "captured_at": "2026-08-09T23:00:00Z", "evidence_url": "https://github.com/maker/arm"},
                "creator": {"name": "Maker Team", "background": "Small open-hardware team documented in repository profiles.", "evidence_urls": ["https://github.com/maker"]},
                "project_description": "A fabricated robotic arm for workshop automation.",
                "build_path": "CAD design, machined and printed parts, electronics integration, load tests, and revisions.",
                "category_gate": {"passed": True, "evidence": "Photographs and test video show the physical arm.", "evidence_url": "https://github.com/maker/arm"},
                "project_gate_evidence": {
                    "multi_stage": {"passed": True, "evidence": evidence, "evidence_url": "https://github.com/maker/arm", "evidence_locator": "README: Build and test sections"},
                    "significant_investment": {"passed": True, "evidence": evidence, "evidence_url": "https://github.com/maker/arm", "evidence_locator": "README: Iteration history"},
                    "real_challenge": {"passed": True, "evidence": evidence, "evidence_url": "https://github.com/maker/arm", "evidence_locator": "README: Load testing"},
                    "real_motivation": {"passed": True, "evidence": "Built to make low-cost workshop automation accessible.", "evidence_url": "https://github.com/maker/arm", "evidence_locator": "README: Project goal"},
                },
                "necessary_conditions": {
                    "small_team_led": {"passed": True, "evidence": evidence},
                    "what_and_why": {"passed": True, "evidence": evidence},
                    "built_or_substantive_progress": {"passed": True, "evidence": evidence},
                },
                "excellence": {"direction": "technical_engineering", "benchmark_statement": "Comparable hobby arms use kit joints, but this project documents a self-designed load-bearing transmission.", "evidence_url": "https://github.com/maker/arm"},
                "red_lines": {
                    "original_creation": {"passed": True, "evidence": evidence},
                    "actually_built": {"passed": True, "evidence": evidence},
                    "not_mature_mass_product": {"passed": True, "evidence": "The repository identifies a small independent team."},
                },
                "scores": {"creation_investment": 5, "process_visibility": 5, "impact_resonance": 4, "completion": 4, "cross_platform_continuity": 3, "diversity_breakout": 3},
                "selection_reason": "The physical result, documented engineering path, and unusually complete transmission work all clear the strict bar.",
                "auxiliary_evidence": ["https://github.com/maker/arm/issues"],
            }]
        }
        final = strict_weekly.select_payload(researched, decisions)
        self.assertEqual(final["items"][0]["total_score"], 24)
        self.assertEqual(final["issue_stats"]["first_release_count"], 1)
        self.assertEqual(strict_weekly.validate_final(final), [])
        self.assertIn("Open hardware arm", strict_weekly.render(final))

    def test_final_source_minimums_apply_after_all_strict_decisions(self):
        specs = [("YouTube", 7), ("Reddit", 5), ("Kickstarter", 2), ("Hackaday", 2), ("Instructables", 4)]
        candidates, decisions = [], []
        index = 0
        for platform, count in specs:
            for _ in range(count):
                # Give other-platform items the highest scores so this test
                # proves source targets are applied after, not instead of,
                # strict editorial validation and scoring.
                score = 5 if platform == "Instructables" else 4
                candidate, decision = self.strict_candidate_and_decision(index, platform, score)
                candidates.append(candidate); decisions.append(decision); index += 1
        researched = {
            "week": {"start": "2026-08-03T00:00:00Z", "end": "2026-08-09T23:59:59Z", "timezone": "UTC"},
            "config_summary": {
                "final_top": 15,
                "final_mix": {"enabled": True, "initial_slots": {
                    "youtube": 5, "reddit": 4, "crowdfunding": 1, "hackaday": 1, "other": 4,
                }},
            },
            "issue_stats": {"platforms_searched": 5, "initial_candidates": len(candidates)},
            "items": candidates,
        }
        final = strict_weekly.select_payload(researched, {"items": decisions})
        counts = {bucket: sum(strict_weekly.maker_weekly.candidate_mix_bucket(item) == bucket for item in final["items"])
                  for bucket in ("youtube", "reddit", "crowdfunding", "hackaday", "other")}
        self.assertEqual(len(final["items"]), 15)
        self.assertGreaterEqual(counts["youtube"], 5)
        self.assertGreaterEqual(counts["reddit"], 4)
        self.assertGreaterEqual(counts["crowdfunding"], 1)
        self.assertGreaterEqual(counts["hackaday"], 1)
        self.assertEqual(final["issue_stats"]["strict_review_passed"], 20)
        self.assertTrue(final["issue_stats"]["final_mix"]["applied_after_strict_review"])
        self.assertEqual(strict_weekly.validate_final(final), [])

    def test_final_source_shortfall_is_recorded_and_refilled(self):
        specs = [("YouTube", 8), ("Reddit", 6), ("Instructables", 4)]
        candidates, decisions = [], []
        index = 0
        for platform, count in specs:
            for _ in range(count):
                candidate, decision = self.strict_candidate_and_decision(index, platform, 4)
                candidates.append(candidate); decisions.append(decision); index += 1
        researched = {
            "week": {"start": "2026-08-03T00:00:00Z", "end": "2026-08-09T23:59:59Z", "timezone": "UTC"},
            "config_summary": {"final_top": 15, "final_mix": {"enabled": True, "initial_slots": {
                "youtube": 5, "reddit": 4, "crowdfunding": 1, "hackaday": 1, "other": 4,
            }}},
            "issue_stats": {}, "items": candidates,
        }
        final = strict_weekly.select_payload(researched, {"items": decisions})
        self.assertEqual(len(final["items"]), 15)
        shortfalls = final["issue_stats"]["final_mix"]["shortfalls"]
        self.assertEqual(shortfalls["crowdfunding"]["eligible"], 0)
        self.assertEqual(shortfalls["hackaday"]["eligible"], 0)
        self.assertEqual(strict_weekly.validate_final(final), [])

    def test_source_shortfall_still_enforces_instructables_default_maximum(self):
        specs = [("YouTube", 2), ("Reddit", 2), ("Hackaday", 1), ("Instructables", 6)]
        candidates, decisions = [], []
        index = 0
        for platform, count in specs:
            for _ in range(count):
                candidate, decision = self.strict_candidate_and_decision(index, platform, 4)
                candidates.append(candidate); decisions.append(decision); index += 1
        researched = {
            "week": {"start": "2026-08-03T00:00:00Z", "end": "2026-08-09T23:59:59Z", "timezone": "UTC"},
            "config_summary": {"final_top": 15, "final_mix": {"enabled": True, "initial_slots": {
                "youtube": 5, "reddit": 4, "crowdfunding": 1, "hackaday": 1, "other": 4,
            }}},
            "issue_stats": {}, "items": candidates,
        }
        final = strict_weekly.select_payload(researched, {"items": decisions})
        self.assertEqual(len(final["items"]), 8)
        self.assertEqual(sum(item["platform"] == "Instructables" for item in final["items"]), 3)
        self.assertIn("youtube", final["issue_stats"]["final_mix"]["shortfalls"])
        self.assertIn("reddit", final["issue_stats"]["final_mix"]["shortfalls"])
        self.assertEqual(strict_weekly.validate_final(final), [])

    def test_instructables_hard_maximum_refills_from_other_platforms(self):
        specs = [("Instructables", 8), ("YouTube", 8), ("Reddit", 5)]
        candidates, decisions = [], []
        index = 0
        for platform, count in specs:
            for _ in range(count):
                # Instructables deliberately has the highest editorial score;
                # the explicit cap must still hold and refill must preserve 15.
                score = 5 if platform == "Instructables" else 4
                candidate, decision = self.strict_candidate_and_decision(index, platform, score)
                candidates.append(candidate); decisions.append(decision); index += 1
        researched = {
            "week": {"start": "2026-08-03T00:00:00Z", "end": "2026-08-09T23:59:59Z", "timezone": "UTC"},
            "config_summary": {"final_top": 15, "final_mix": {"enabled": True, "initial_slots": {
                "youtube": 5, "reddit": 4, "crowdfunding": 1, "hackaday": 1, "other": 4,
            }, "platform_maximums": {"instructables": 3}}},
            "issue_stats": {}, "items": candidates,
        }
        final = strict_weekly.select_payload(researched, {"items": decisions})
        self.assertEqual(len(final["items"]), 15)
        self.assertEqual(sum(item["platform"] == "Instructables" for item in final["items"]), 3)
        self.assertEqual(strict_weekly.validate_final(final), [])

    def test_final_selection_rejects_incomplete_strict_review(self):
        first_candidate, first_decision = self.strict_candidate_and_decision(1, "YouTube", 4)
        second_candidate, _ = self.strict_candidate_and_decision(2, "Reddit", 4)
        researched = {
            "week": {"start": "2026-08-03T00:00:00Z", "end": "2026-08-09T23:59:59Z", "timezone": "UTC"},
            "config_summary": {"final_top": 15}, "issue_stats": {},
            "items": [first_candidate, second_candidate],
        }
        with self.assertRaisesRegex(strict_weekly.StrictError, "strict review is incomplete"):
            strict_weekly.select_payload(researched, {"items": [first_decision], "rejections": []})
        final = strict_weekly.select_payload(researched, {
            "items": [first_decision],
            "rejections": [{
                "id": second_candidate["id"], "failed_stage": "project_gate",
                "rejection_reason": "Only one project-gate dimension had direct evidence.",
                "evidence_url": second_candidate["url"],
            }],
        })
        self.assertEqual(final["issue_stats"]["strict_reviewed"], 2)
        self.assertEqual(final["issue_stats"]["strict_review_rejected"], 1)

    def test_raw_or_failed_gate_items_cannot_enter_final_report(self):
        payload = {
            "schema_version": 1, "selection_method": "maker-weekly-strict-v1",
            "week": {"start": "2026-08-03T00:00:00Z", "end": "2026-08-09T23:59:59Z", "timezone": "UTC"},
            "issue_stats": {"selected_projects": 1},
            "items": [{"rank": 1, "title": "Raw software discovery", "total_score": 30, "physical_gate": {"status": "fail"}, "time_gate": {"status": "pass"}, "heat_gate": {"status": "pass"}}],
        }
        errors = strict_weekly.validate_final(payload)
        self.assertTrue(any("physical, time, and heat" in error for error in errors))
        with self.assertRaises(strict_weekly.StrictError):
            strict_weekly.render(payload)

    def test_strict_decision_accepts_execution_time_heat_after_week_end(self):
        candidate = {
            "id": "late-observation", "platform": "YouTube", "title": "Physical build",
            "url": "https://youtube.com/watch?v=abcdef1", "published_at": "2026-08-07T00:00:00Z",
            "physical_gate": {"status": "pass"}, "time_gate": {"status": "pass"}, "heat_gate": {"status": "pass"},
        }
        decision = {
            "entry_type": "first_release", "heat_gate": {
                "status": "pass", "observed": "views=250000", "threshold": "200,000 views",
                "captured_at": "2026-08-12T00:00:00Z", "evidence_url": candidate["url"],
            }
        }
        start, end = strict_weekly.week_bounds("2026-08-03", "2026-08-09")
        errors = strict_weekly.validate_decision(decision, candidate, start, end)
        self.assertNotIn("heat_gate capture time must be on or before the issue cutoff", errors)
        self.assertFalse(any("capture time" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
