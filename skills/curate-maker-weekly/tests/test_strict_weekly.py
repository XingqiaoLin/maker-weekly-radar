import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


SCRIPTS = Path(__file__).parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))
import strict_weekly  # noqa: E402


class StrictWeeklyTests(unittest.TestCase):
    def test_last_complete_week(self):
        window = strict_weekly.last_complete_week(date(2026, 8, 12))
        self.assertEqual(window["week_start"], "2026-08-03")
        self.assertEqual(window["week_end"], "2026-08-09")
        self.assertEqual(window["previous_snapshot_date"], "2026-08-02")

    def test_heat_gates_are_hard_thresholds(self):
        github = strict_weekly.heat_gate({"platform": "GitHub", "metrics": {"stars": 999}, "url": "https://github.com/x/y"})
        kickstarter = strict_weekly.heat_gate({"platform": "Kickstarter", "metrics": {"backers": 200}, "url": "https://kickstarter.com/x"})
        youtube_rss = strict_weekly.heat_gate({"platform": "YouTube", "metrics": {"feed_host": "youtube.com"}, "url": "https://youtube.com/x"})
        self.assertEqual(github["status"], "fail")
        self.assertEqual(kickstarter["status"], "pass")
        self.assertEqual(youtube_rss["status"], "unknown")

    def test_baseline_allows_only_first_release_time_classification(self):
        payload = {
            "source_status": [{"status": "ok", "platform": "GitHub"}],
            "items": [
                {"id": "new", "platform": "GitHub", "title": "New", "url": "https://github.com/a/new", "published_at": "2026-08-05T10:00:00Z", "metrics": {"stars": 1000}},
                {"id": "old", "platform": "GitHub", "title": "Old", "url": "https://github.com/a/old", "published_at": "2026-07-01T10:00:00Z", "metrics": {"stars": 1000}},
            ],
        }
        start, end = strict_weekly.week_bounds("2026-08-03", "2026-08-09")
        prepared = strict_weekly.prepare_payload(payload, start, end, None)
        self.assertEqual(prepared["items"][0]["time_gate"]["entry_type"], "first_release")
        self.assertEqual(prepared["items"][1]["time_gate"]["status"], "fail")
        self.assertTrue(prepared["week"]["baseline"])

    def test_select_valid_strict_project(self):
        candidate = {
            "id": "project-1",
            "platform": "GitHub",
            "title": "Open hardware arm",
            "url": "https://github.com/maker/arm",
            "canonical_url": "https://github.com/maker/arm",
            "published_at": "2026-08-05T10:00:00Z",
            "metrics": {"stars": 1200},
            "evidence": ["https://github.com/maker/arm"],
            "time_gate": {"status": "pass", "entry_type": "first_release"},
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
                "project_gate_evidence": {"multi_stage": evidence, "significant_investment": evidence, "real_challenge": evidence, "real_motivation": "Built to make low-cost workshop automation accessible."},
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


if __name__ == "__main__":
    unittest.main()
