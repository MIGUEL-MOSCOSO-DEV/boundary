import json
import tempfile
import unittest
from pathlib import Path

from desktop.reporting import read_report, render, write_html


class ReportTests(unittest.TestCase):
    def report(self):
        return {
            "schema": 1,
            "tool": "Boundary",
            "created_at": "2026-10-28T00:00:00Z",
            "complete": True,
            "summary": {"pass": 1},
            "cases": [
                {
                    "name": "<script>alert(1)</script>",
                    "method": "GET",
                    "url": "https://owned.test/",
                    "results": [
                        {
                            "identity": "owner",
                            "expected": "allow",
                            "response": {"status": 200},
                            "verdict": "pass",
                            "findings": [],
                            "request": {"headers": {"Authorization": "<set from ENV>"}},
                        }
                    ],
                }
            ],
        }

    def test_html_escapes_untrusted_evidence(self):
        text = render(self.report())
        self.assertNotIn("<script>alert(1)</script>", text)
        self.assertIn("&lt;script&gt;", text)
        self.assertIn("Content-Security-Policy", text)

    def test_report_contains_no_remote_assets(self):
        text = render(self.report())
        self.assertNotIn("<script", text)
        self.assertNotIn("<link", text)
        self.assertNotIn("<iframe", text)

    def test_atomic_html_export_and_json_import(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "report.html"
            write_html(self.report(), path)
            self.assertIn("<!doctype html>", path.read_text(encoding="utf-8"))
            source = Path(folder) / "report.json"
            source.write_text(json.dumps(self.report()), encoding="utf-8")
            self.assertEqual(read_report(source)["tool"], "Boundary")
            self.assertEqual(list(Path(folder).glob("*.tmp")), [])

    def test_unknown_tool_is_rejected(self):
        report = self.report()
        report["tool"] = "unknown"
        with self.assertRaises(ValueError):
            render(report)
