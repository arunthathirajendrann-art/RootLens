"""Unit tests for RootLens Ingestion Loaders (Member A).

Compatible with both standard library `unittest` and `pytest`.
"""

import json
import tempfile
import unittest
from pathlib import Path

from ingestion.loaders import (
    load_alerts,
    load_logs,
    load_metrics,
    load_complaints,
    load_deployments,
    load_past_incidents,
    load_audit_config_changes,
    load_gc_profiler,
    load_initial_incident_signals,
    load_late_evidence,
)


class TestIngestionLoaders(unittest.TestCase):
    """Test suite for raw data file ingestion and basic schema validation."""

    def test_load_alerts_success(self):
        """Test loading alerts from default data file."""
        alerts = load_alerts()
        self.assertIsInstance(alerts, list)
        self.assertEqual(len(alerts), 5)
        first = alerts[0]
        for field in ["alert_id", "timestamp", "service", "severity", "status"]:
            self.assertIn(field, first)

    def test_load_logs_success(self):
        """Test loading logs from default data file."""
        logs = load_logs()
        self.assertIsInstance(logs, list)
        self.assertEqual(len(logs), 17)
        first = logs[0]
        for field in ["log_id", "timestamp", "service", "level", "message"]:
            self.assertIn(field, first)

    def test_load_metrics_success(self):
        """Test loading metrics CSV with all required columns."""
        metrics = load_metrics()
        self.assertIsInstance(metrics, list)
        self.assertEqual(len(metrics), 42)
        first = metrics[0]
        expected_cols = [
            "timestamp",
            "service",
            "p50_latency_ms",
            "p95_latency_ms",
            "p99_latency_ms",
            "error_rate_pct",
            "cpu_utilization_pct",
            "memory_utilization_pct",
            "gc_pause_ms",
        ]
        for col in expected_cols:
            self.assertIn(col, first)

    def test_load_complaints_success(self):
        """Test loading customer complaints."""
        complaints = load_complaints()
        self.assertIsInstance(complaints, list)
        self.assertEqual(len(complaints), 5)
        first = complaints[0]
        for field in ["ticket_id", "timestamp", "channel", "description"]:
            self.assertIn(field, first)

    def test_load_deployments_success(self):
        """Test loading deployment history including red herring."""
        deploys = load_deployments()
        self.assertIsInstance(deploys, list)
        self.assertEqual(len(deploys), 3)
        versions = [d["version"] for d in deploys]
        self.assertIn("v2.14.0", versions)
        red_herring = next(d for d in deploys if d["version"] == "v2.14.0")
        self.assertEqual(red_herring["service"], "checkout-service")
        self.assertEqual(red_herring["status"], "SUCCESS")

    def test_load_past_incidents_success(self):
        """Test loading historical incident memory."""
        past_incidents = load_past_incidents()
        self.assertIsInstance(past_incidents, list)
        self.assertEqual(len(past_incidents), 3)
        ids = [inc["incident_id"] for inc in past_incidents]
        self.assertIn("INC-2025-1044", ids)

    def test_load_audit_config_changes_success(self):
        """Test loading late-arriving config audit changes."""
        configs = load_audit_config_changes()
        self.assertIsInstance(configs, list)
        self.assertEqual(len(configs), 2)
        root_cause = next(c for c in configs if c["change_id"] == "CFG-8912")
        self.assertEqual(root_cause["service"], "checkout-service")
        self.assertEqual(root_cause["timestamp"], "2026-08-18T14:08:15Z")

    def test_load_gc_profiler_success(self):
        """Test loading late-arriving GC profiler traces."""
        gc_traces = load_gc_profiler()
        self.assertIsInstance(gc_traces, list)
        self.assertEqual(len(gc_traces), 5)
        self.assertTrue(any(t["gc_pause_ms"] > 3000 for t in gc_traces))

    def test_missing_file_raises_error(self):
        """Test that missing files raise a clear FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            missing_path = Path(tmpdir) / "non_existent.json"
            with self.assertRaises(FileNotFoundError):
                load_alerts(missing_path)

            with self.assertRaises(FileNotFoundError):
                load_metrics(Path(tmpdir) / "non_existent.csv")

    def test_malformed_json_raises_error(self):
        """Test that malformed JSON raises a ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            bad_json = Path(tmpdir) / "bad.json"
            bad_json.write_text("{ unquoted_key: 123", encoding="utf-8")
            with self.assertRaises(ValueError):
                load_logs(bad_json)

    def test_invalid_json_structure_raises_error(self):
        """Test that non-list JSON top-level structure raises ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            obj_json = Path(tmpdir) / "object.json"
            obj_json.write_text('{"status": "ok"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                load_alerts(obj_json)

    def test_missing_required_fields_raises_error(self):
        """Test that records missing mandatory raw fields raise ValueError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            incomplete_json = Path(tmpdir) / "incomplete.json"
            incomplete_json.write_text(
                json.dumps([{"alert_id": "ALT-1"}]),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError):
                load_alerts(incomplete_json)

    def test_initial_incident_signals_isolation(self):
        """Verify load_initial_incident_signals does NOT contain late evidence or past incidents."""
        initial_signals = load_initial_incident_signals()
        self.assertIsInstance(initial_signals, dict)

        # Must contain only initial operational signal keys
        expected_keys = {"alerts", "logs", "metrics", "complaints", "deployments"}
        self.assertEqual(set(initial_signals.keys()), expected_keys)

        # Must NOT contain late evidence keys
        self.assertNotIn("audit_config_changes", initial_signals)
        self.assertNotIn("gc_profiler", initial_signals)
        self.assertNotIn("past_incidents", initial_signals)

        # Verify counts of loaded signals
        self.assertEqual(len(initial_signals["alerts"]), 5)
        self.assertEqual(len(initial_signals["logs"]), 17)
        self.assertEqual(len(initial_signals["metrics"]), 42)
        self.assertEqual(len(initial_signals["complaints"]), 5)
        self.assertEqual(len(initial_signals["deployments"]), 3)

    def test_load_late_evidence_isolation(self):
        """Verify load_late_evidence contains ONLY late-arriving evidence."""
        late_evidence = load_late_evidence()
        self.assertIsInstance(late_evidence, dict)

        expected_keys = {"audit_config_changes", "gc_profiler"}
        self.assertEqual(set(late_evidence.keys()), expected_keys)

        # Must NOT contain initial signal keys
        self.assertNotIn("alerts", late_evidence)
        self.assertNotIn("logs", late_evidence)
        self.assertNotIn("metrics", late_evidence)
        self.assertNotIn("complaints", late_evidence)
        self.assertNotIn("deployments", late_evidence)

        self.assertEqual(len(late_evidence["audit_config_changes"]), 2)
        self.assertEqual(len(late_evidence["gc_profiler"]), 5)


if __name__ == "__main__":
    unittest.main()
