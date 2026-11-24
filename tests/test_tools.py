from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

SRC = Path(__file__).resolve().parents[1] / "src"
sys.path.insert(0, str(SRC))

from client import SonarClient  # noqa: E402
from tools import set_client  # noqa: E402
from tools.hotspots import sonar_update_hotspot_status  # noqa: E402
from tools.issues import (  # noqa: E402
    sonar_get_issue_detail,
    sonar_get_issue_summary,
    sonar_list_issues,
    sonar_update_issue_status,
)


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.client = SonarClient("https://sonar.example.test", token="t")
        set_client(self.client)
        self.addCleanup(set_client, None)
        patcher = patch.object(SonarClient, "request", autospec=True)
        self.mock_request = patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []

    def use_fixtures(self, fixtures):
        def fake(instance, method, path, *, params=None, data=None):
            self.calls.append((method, path, params, data))
            if (method, path) not in fixtures:
                raise AssertionError(f"unexpected request: {method} {path}")
            value = fixtures[(method, path)]
            return value(params) if callable(value) else value

        self.mock_request.side_effect = fake

    def test_get_issue_detail_assembles_location_why_and_fix(self):
        self.use_fixtures(
            {
                ("GET", "/api/issues/search"): {
                    "issues": [
                        {
                            "key": "AX-1",
                            "rule": "squid:S1172",
                            "project": "p1",
                            "component": "p1:src/A.java",
                            "message": "Remove unused parameter",
                            "severity": "MAJOR",
                            "type": "CODE_SMELL",
                            "status": "OPEN",
                            "textRange": {
                                "startLine": 12,
                                "endLine": 12,
                                "startOffset": 2,
                                "endOffset": 5,
                            },
                            "effort": "5min",
                            "flows": [
                                {
                                    "locations": [
                                        {
                                            "component": "p1:src/A.java",
                                            "msg": "value used here",
                                            "textRange": {"startLine": 20},
                                        }
                                    ]
                                }
                            ],
                            "transitions": ["falsepositive", "confirm"],
                        }
                    ],
                    "components": [{"key": "p1:src/A.java", "path": "src/A.java"}],
                    "rules": [],
                },
                ("GET", "/api/rules/show"): {
                    "rule": {
                        "key": "squid:S1172",
                        "name": "Unused parameters should be removed",
                        "htmlDesc": "<p>Why <b>unused</b> param</p>",
                        "htmlExample": "<pre>Do this</pre>",
                        "descriptionSections": [
                            {"key": "introduction", "content": "<p>Intro from section</p>"},
                            {"key": "how_to_fix", "content": "<p>Fix from section</p>"},
                        ],
                    }
                },
            }
        )

        detail = sonar_get_issue_detail("AX-1")

        self.assertEqual(detail["location"]["path"], "src/A.java")
        self.assertEqual(detail["location"]["textRange"]["startLine"], 12)
        self.assertEqual(detail["rule_name"], "Unused parameters should be removed")
        self.assertEqual(detail["rule_key"], "squid:S1172")
        self.assertIn("Why unused param", detail["why"])
        self.assertNotIn("<p>", detail["why"])
        self.assertIn("Do this", detail["how_to_fix"])
        self.assertIn("Intro from section", detail["why"])
        self.assertIn("Fix from section", detail["how_to_fix"])
        self.assertIn("p1:src/A.java:20", detail["how_to_fix"])
        self.assertIsNone(detail["resolution"])
        self.assertEqual(detail["transitions"], ["falsepositive", "confirm"])

    def test_update_issue_status_requires_confirm_and_posts_transition_and_comment(self):
        self.use_fixtures(
            {
                ("GET", "/api/issues/search"): {
                    "issues": [{"key": "AX-1", "transitions": ["falsepositive", "confirm"]}]
                },
                ("POST", "/api/issues/do_transition"): {},
                ("POST", "/api/issues/add_comment"): {},
            }
        )

        with self.assertRaises(ValueError):
            sonar_update_issue_status("AX-1", "false_positive")
        self.assertEqual(self.mock_request.call_count, 0)

        result = sonar_update_issue_status(
            "AX-1", "false_positive", comment="not a bug", confirm=True
        )
        self.assertTrue(result["changed"])
        self.assertEqual(result["transition"], "falsepositive")
        self.assertTrue(result["comment_posted"])
        transition_call = next(c for c in self.calls if c[1] == "/api/issues/do_transition")
        self.assertEqual(transition_call[3], {"issue": "AX-1", "transition": "falsepositive"})
        comment_call = next(c for c in self.calls if c[1] == "/api/issues/add_comment")
        self.assertEqual(comment_call[3], {"issue": "AX-1", "text": "not a bug"})

    def test_issue_summary_reads_facets_and_hotspot_totals(self):
        self.use_fixtures(
            {
                ("GET", "/api/issues/search"): {
                    "paging": {"total": 7},
                    "facets": [
                        {
                            "property": "statuses",
                            "values": [
                                {"val": "OPEN", "count": 5},
                                {"val": "CLOSED", "count": 2},
                            ],
                        },
                        {
                            "property": "severities",
                            "values": [{"val": "MAJOR", "count": 7}],
                        },
                    ],
                },
                ("GET", "/api/hotspots/search"): lambda params: {
                    "paging": {"total": 3 if params.get("status") == "TO_REVIEW" else 4}
                },
            }
        )

        summary = sonar_get_issue_summary(project="p1")

        self.assertEqual(summary["total"], 7)
        self.assertEqual(summary["statuses"], {"OPEN": 5, "CLOSED": 2})
        self.assertEqual(summary["severities"], {"MAJOR": 7})
        self.assertEqual(summary["projects"], {})
        self.assertEqual(summary["hotspots"], {"to_review": 3, "reviewed": 4})
        self.assertEqual(self.mock_request.call_count, 3)

    def test_list_issues_sends_project_and_new_code_period(self):
        self.use_fixtures(
            {
                ("GET", "/api/issues/search"): {
                    "paging": {"total": 1},
                    "issues": [
                        {
                            "key": "AX-2",
                            "ruleKey": "squid:S1",
                            "project": "p1",
                            "component": "p1:src/B.java",
                            "message": "msg",
                            "textRange": {"startLine": 9},
                        }
                    ],
                }
            }
        )

        result = sonar_list_issues(
            project="p1", statuses=["OPEN", "CONFIRMED"], in_new_code_period=True
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["issues"][0]["line"], 9)
        self.assertIsNone(result["issues"][0]["severity"])
        call = next(c for c in self.calls if c[1] == "/api/issues/search")
        self.assertEqual(call[2]["projects"], "p1")
        self.assertEqual(call[2]["statuses"], "OPEN,CONFIRMED")
        self.assertEqual(call[2]["inNewCodePeriod"], "true")

    def test_update_hotspot_status_requires_confirm_and_resolution(self):
        self.use_fixtures({("POST", "/api/hotspots/change_status"): {}})

        with self.assertRaises(ValueError):
            sonar_update_hotspot_status("H-1", "REVIEWED", resolution="SAFE")
        self.assertEqual(self.mock_request.call_count, 0)

        with self.assertRaises(ValueError):
            sonar_update_hotspot_status("H-1", "REVIEWED", confirm=True)
        self.assertEqual(self.mock_request.call_count, 0)

        result = sonar_update_hotspot_status(
            "H-1", "REVIEWED", resolution="SAFE", comment="checked", confirm=True
        )
        self.assertEqual(result["status"], "REVIEWED")
        self.assertEqual(result["resolution"], "SAFE")
        call = next(c for c in self.calls if c[1] == "/api/hotspots/change_status")
        self.assertEqual(
            call[3],
            {"hotspot": "H-1", "status": "REVIEWED", "resolution": "SAFE", "comment": "checked"},
        )

    def test_client_rejects_ssrf_paths(self):
        for path in ("https://evil.test/api/issues/search", "/api/../api/issues/search"):
            with self.assertRaises(ValueError):
                SonarClient._validate_path(path)
        self.assertEqual(self.mock_request.call_count, 0)


if __name__ == "__main__":
    unittest.main()
