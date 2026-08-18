"""Unit tests for RootLens Normalization Layer (Member A).

Validates canonical event schema, deterministic IDs, severity mapping,
source taxonomy, evidence neutrality, and chronological ordering.
"""

import unittest
from datetime import datetime

from ingestion.normalizer import (
    normalize_alerts,
    normalize_audit_config_changes,
    normalize_complaints,
    normalize_deployments,
    normalize_gc_profiler,
    normalize_initial_incident_signals,
    normalize_late_evidence,
    normalize_logs,
    normalize_metrics,
)
from utils.schemas import CanonicalSeverity, CanonicalSource
from utils.timestamp import parse_iso_utc

MANDATORY_FIELDS = {
    "event_id",
    "timestamp",
    "source",
    "service",
    "severity",
    "event_type",
    "description",
    "metadata",
}

VALID_SEVERITIES = {
    CanonicalSeverity.CRITICAL.value,
    CanonicalSeverity.HIGH.value,
    CanonicalSeverity.MEDIUM.value,
    CanonicalSeverity.LOW.value,
    CanonicalSeverity.INFO.value,
}

VALID_SOURCES = {
    CanonicalSource.ALERTS.value,
    CanonicalSource.LOGS.value,
    CanonicalSource.METRICS.value,
    CanonicalSource.COMPLAINTS.value,
    CanonicalSource.DEPLOYS.value,
    CanonicalSource.CONFIG.value,
    CanonicalSource.GC_PROFILER.value,
}


class TestEventNormalizer(unittest.TestCase):
    """Test suite for event normalization layer."""

    def test_canonical_fields_present_in_all_sources(self):
        """Test that every normalized event contains all 8 required canonical fields."""
        all_events = normalize_initial_incident_signals() + normalize_late_evidence()
        self.assertGreater(len(all_events), 0)
        for idx, evt in enumerate(all_events):
            self.assertEqual(
                set(evt.keys()),
                MANDATORY_FIELDS,
                f"Event #{idx} (id={evt.get('event_id')}) keys mismatch: {set(evt.keys())}",
            )
            self.assertIsInstance(evt["metadata"], dict)
            self.assertTrue(bool(evt["description"].strip()))

    def test_timestamps_are_valid_iso_utc(self):
        """Test that all normalized timestamps are valid ISO-8601 UTC strings."""
        all_events = normalize_initial_incident_signals() + normalize_late_evidence()
        for evt in all_events:
            ts_str = evt["timestamp"]
            self.assertTrue(ts_str.endswith("Z"), f"Timestamp {ts_str} missing Z suffix")
            dt = parse_iso_utc(ts_str)
            self.assertIsNotNone(dt.tzinfo)

    def test_severities_are_canonical(self):
        """Test that all severities map strictly to canonical severity values."""
        all_events = normalize_initial_incident_signals() + normalize_late_evidence()
        for evt in all_events:
            self.assertIn(
                evt["severity"],
                VALID_SEVERITIES,
                f"Invalid severity {evt['severity']} in event {evt['event_id']}",
            )

    def test_sources_are_canonical(self):
        """Test that all source values match canonical source taxonomy."""
        all_events = normalize_initial_incident_signals() + normalize_late_evidence()
        for evt in all_events:
            self.assertIn(
                evt["source"],
                VALID_SOURCES,
                f"Invalid source {evt['source']} in event {evt['event_id']}",
            )

    def test_event_ids_are_deterministic(self):
        """Test that repeated normalizations produce identical deterministic event IDs."""
        run1 = normalize_initial_incident_signals()
        run2 = normalize_initial_incident_signals()
        ids1 = [e["event_id"] for e in run1]
        ids2 = [e["event_id"] for e in run2]
        self.assertEqual(ids1, ids2)

    def test_event_ids_are_unique(self):
        """Test that all normalized event IDs within initial and late sets are unique."""
        initial = normalize_initial_incident_signals()
        initial_ids = [e["event_id"] for e in initial]
        self.assertEqual(len(initial_ids), len(set(initial_ids)))

        late = normalize_late_evidence()
        late_ids = [e["event_id"] for e in late]
        self.assertEqual(len(late_ids), len(set(late_ids)))

    def test_initial_normalization_contains_only_initial_sources(self):
        """Test that initial signals contain only alerts, logs, metrics, complaints, and deploys."""
        initial = normalize_initial_incident_signals()
        sources = {e["source"] for e in initial}
        expected_initial_sources = {"alerts", "logs", "metrics", "complaints", "deploys"}
        self.assertEqual(sources, expected_initial_sources)

        # Must not contain late-evidence sources
        self.assertNotIn("config", sources)
        self.assertNotIn("gc_profiler", sources)

    def test_late_normalization_contains_only_late_evidence(self):
        """Test that late normalization contains only config and gc_profiler."""
        late = normalize_late_evidence()
        sources = {e["source"] for e in late}
        expected_late_sources = {"config", "gc_profiler"}
        self.assertEqual(sources, expected_late_sources)

    def test_historical_incidents_not_included(self):
        """Verify that past_incidents are not converted into live normalized events."""
        all_events = normalize_initial_incident_signals() + normalize_late_evidence()
        sources = {e["source"] for e in all_events}
        self.assertNotIn("past_incidents", sources)
        for e in all_events:
            self.assertFalse(e["event_id"].startswith("EVT-INC"))

    def test_metadata_preserves_source_values(self):
        """Test that source-specific metrics and attributes are preserved in metadata."""
        metrics = normalize_metrics()
        sample = metrics[0]
        self.assertIn("p99_latency_ms", sample["metadata"])
        self.assertIn("memory_utilization_pct", sample["metadata"])
        self.assertIn("gc_pause_ms", sample["metadata"])

        deploys = normalize_deployments()
        dep_sample = next(d for d in deploys if d["metadata"]["version"] == "v2.14.0")
        self.assertEqual(dep_sample["metadata"]["status"], "SUCCESS")

        configs = normalize_audit_config_changes()
        cfg_sample = next(c for c in configs if c["metadata"]["change_id"] == "CFG-8912")
        self.assertEqual(cfg_sample["metadata"]["parameter"], "cart_cache_configuration")

    def test_evidence_neutrality(self):
        """Verify no normalized event contains conclusionary labels like ROOT_CAUSE or RED_HERRING."""
        all_events = normalize_initial_incident_signals() + normalize_late_evidence()
        forbidden_terms = ["ROOT_CAUSE", "RED_HERRING", "ACTUAL_CAUSE", "FALSE_ALARM", "CAUSED_BY"]
        for evt in all_events:
            for term in forbidden_terms:
                self.assertNotIn(term, evt["event_type"].upper())
                self.assertNotIn(term, evt["description"].upper())
            for k, v in evt["metadata"].items():
                if isinstance(v, str):
                    for term in forbidden_terms:
                        self.assertNotIn(term, v.upper())

    def test_chronological_ordering(self):
        """Test that normalize_initial_incident_signals returns events in strict chronological order."""
        initial = normalize_initial_incident_signals()
        timestamps = [parse_iso_utc(e["timestamp"]) for e in initial]
        self.assertEqual(timestamps, sorted(timestamps))

        late = normalize_late_evidence()
        late_timestamps = [parse_iso_utc(e["timestamp"]) for e in late]
        self.assertEqual(late_timestamps, sorted(late_timestamps))


if __name__ == "__main__":
    unittest.main()
