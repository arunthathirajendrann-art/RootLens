"""Unit tests for RootLens Re-Correlation Engine (Phase 4).

Tests dynamic re-correlation when new observability signals arrive mid-incident.
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import random
import unittest

from correlation.correlation_engine import CorrelationEngine, correlate_events, re_correlate
from correlation.timeline_builder import build_timeline
from utils.schemas import IncidentCluster, NormalizedEvent, ReCorrelationResult, UnifiedTimeline


class TestReCorrelation(unittest.TestCase):
    """Test suite covering dynamic signal arrival and re-correlation logic."""

    def setUp(self) -> None:
        """Set up standard base timestamp and correlation engine."""
        self.base_time = datetime(2026, 8, 18, 10, 0, 0, tzinfo=timezone.utc)
        self.engine = CorrelationEngine(time_window=timedelta(minutes=10))

    def _create_event(
        self,
        event_id: str,
        offset_minutes: float,
        component: str = "checkout-service",
        source: str = "alerts",
        severity: str = "HIGH",
        description: str = "Sample event description",
        metadata: dict = None,
    ) -> NormalizedEvent:
        """Helper to create a NormalizedEvent."""
        ts = self.base_time + timedelta(minutes=offset_minutes)
        return NormalizedEvent(
            event_id=event_id,
            timestamp=ts,
            source=source,
            component=component,
            severity=severity,
            description=description,
            metadata=metadata or {},
        )

    def test_no_new_events_remains_equivalent(self) -> None:
        """Verify re-correlating with empty/None new events produces identical clusters and timeline."""
        e1 = self._create_event("evt-1", 0)
        e2 = self._create_event("evt-2", 4)
        existing = [e1, e2]

        initial_clusters = self.engine.correlate(existing)
        initial_timeline = build_timeline(initial_clusters)

        # Re-correlate with empty list and None
        for empty_new in ([], None):
            res: ReCorrelationResult = self.engine.re_correlate(existing, empty_new)
            self.assertEqual(len(res.clusters), len(initial_clusters))
            self.assertEqual(res.clusters[0].event_ids, initial_clusters[0].event_ids)
            self.assertEqual(res.timeline.event_count, initial_timeline.event_count)
            self.assertEqual(
                [e.event_id for e in res.timeline.entries],
                [e.event_id for e in initial_timeline.entries],
            )
            self.assertEqual(res.new_events_count, 0)
            self.assertEqual(res.total_events, 2)

    def test_one_new_event_joins_existing_cluster(self) -> None:
        """Verify a new event within the 10-minute window extends an existing cluster."""
        e1 = self._create_event("evt-alert-1", 0, source="alerts")
        e2 = self._create_event("evt-log-1", 4, source="logs")
        existing = [e1, e2]

        # New deploy signal arrives at t=8m (gap 4m from e2 <= 10m)
        new_event = self._create_event("evt-deploy-1", 8, source="deploys", severity="INFO")

        res = self.engine.re_correlate(existing, [new_event])

        self.assertEqual(len(res.clusters), 1)
        cluster = res.clusters[0]
        self.assertEqual(cluster.event_count, 3)
        self.assertEqual(cluster.event_ids, ["evt-alert-1", "evt-log-1", "evt-deploy-1"])
        self.assertEqual(cluster.start_time, self.base_time)
        self.assertEqual(cluster.end_time, self.base_time + timedelta(minutes=8))

        self.assertEqual(res.timeline.event_count, 3)
        self.assertEqual(
            [e.event_id for e in res.timeline.entries],
            ["evt-alert-1", "evt-log-1", "evt-deploy-1"],
        )
        self.assertEqual(res.new_events_count, 1)

    def test_one_new_event_creates_new_cluster(self) -> None:
        """Verify a new event with timestamp gap > 10m creates a separate cluster."""
        e1 = self._create_event("evt-1", 0)
        existing = [e1]

        # New signal at t=30m (> 10m window)
        new_event = self._create_event("evt-late", 30, source="logs")

        res = self.engine.re_correlate(existing, new_event)

        self.assertEqual(len(res.clusters), 2)
        self.assertEqual(res.clusters[0].event_ids, ["evt-1"])
        self.assertEqual(res.clusters[1].event_ids, ["evt-late"])
        self.assertEqual(res.timeline.event_count, 2)
        self.assertEqual(res.new_events_count, 1)

    def test_multiple_new_events_incorporated(self) -> None:
        """Verify multiple new signals from different sources are smoothly integrated."""
        e1 = self._create_event("evt-init", 0)
        existing = [e1]

        new_events = [
            self._create_event("evt-metric", 3, source="metrics"),
            self._create_event("evt-log", 6, source="logs"),
            self._create_event("evt-complaint", 9, source="complaints"),
        ]

        res = self.engine.re_correlate(existing, new_events)

        self.assertEqual(len(res.clusters), 1)
        self.assertEqual(res.clusters[0].event_count, 4)
        self.assertEqual(
            res.clusters[0].event_ids,
            ["evt-init", "evt-metric", "evt-log", "evt-complaint"],
        )
        self.assertEqual(res.new_events_count, 3)
        self.assertEqual(res.total_events, 4)

    def test_new_event_arrives_out_of_chronological_order(self) -> None:
        """Verify an out-of-order/backfilled new event is placed correctly in chronological order."""
        # Existing events at t=5m and t=9m
        e2 = self._create_event("evt-2", 5)
        e3 = self._create_event("evt-3", 9)
        existing = [e2, e3]

        # New signal arrived late, but happened earlier at t=1m
        earlier_event = self._create_event("evt-early", 1, source="deploys")

        res = self.engine.re_correlate(existing, earlier_event)

        self.assertEqual(len(res.clusters), 1)
        self.assertEqual(res.clusters[0].event_ids, ["evt-early", "evt-2", "evt-3"])
        self.assertEqual(res.timeline.entries[0].event_id, "evt-early")
        self.assertEqual(res.timeline.start_time, self.base_time + timedelta(minutes=1))
        self.assertEqual(res.timeline.end_time, self.base_time + timedelta(minutes=9))

    def test_exact_window_boundary_behavior(self) -> None:
        """Verify boundary rules: exact delta == 10m merges; delta > 10m splits."""
        e1 = self._create_event("evt-1", 0)

        # Exactly 10 minutes: delta == 10m => same cluster
        new_boundary = self._create_event("evt-boundary", 10.0)
        res_boundary = self.engine.re_correlate([e1], new_boundary)
        self.assertEqual(len(res_boundary.clusters), 1)
        self.assertEqual(res_boundary.clusters[0].event_ids, ["evt-1", "evt-boundary"])

        # 10 minutes + 1 second: delta > 10m => separate clusters
        new_outside = self._create_event("evt-outside", 10.02)
        res_outside = self.engine.re_correlate([e1], new_outside)
        self.assertEqual(len(res_outside.clusters), 2)

    def test_different_component_does_not_merge(self) -> None:
        """Verify new signal on a different component does not merge with existing component."""
        e_auth = self._create_event("evt-auth", 0, component="auth-service")
        existing = [e_auth]

        # New signal at close time (t=2m) but for payment-gateway
        new_pay = self._create_event("evt-pay", 2, component="payment-gateway")

        res = self.engine.re_correlate(existing, new_pay)

        self.assertEqual(len(res.clusters), 2)
        self.assertEqual(res.clusters[0].component, "auth-service")
        self.assertEqual(res.clusters[1].component, "payment-gateway")
        self.assertEqual(res.timeline.event_count, 2)
        self.assertEqual(res.timeline.components, ["auth-service", "payment-gateway"])

    def test_all_original_and_new_events_preserved_exactly_once(self) -> None:
        """Verify that every event from existing and new inputs is preserved exactly once."""
        existing = [self._create_event(f"evt-exist-{i}", i * 3, component="svc-a") for i in range(5)]
        new_events = [self._create_event(f"evt-new-{i}", i * 4 + 1, component="svc-b") for i in range(4)]

        res = self.engine.re_correlate(existing, new_events)

        self.assertEqual(res.total_events, 9)
        self.assertEqual(res.new_events_count, 4)

        all_timeline_ids = [entry.event_id for entry in res.timeline.entries]
        expected_ids = sorted([e.event_id for e in existing] + [e.event_id for e in new_events])
        self.assertEqual(sorted(all_timeline_ids), expected_ids)
        self.assertEqual(len(set(all_timeline_ids)), 9)

    def test_event_ids_and_metadata_unchanged(self) -> None:
        """Verify existing event IDs and metadata remain completely unchanged."""
        meta = {"trace_id": "tr-12345", "error_code": "ERR_500"}
        e1 = self._create_event("evt-id-1", 0, metadata=meta)
        e_new = self._create_event("evt-id-2", 4, metadata={"status": "resolved"})

        res = self.engine.re_correlate([e1], [e_new])

        e1_entry = res.timeline.entries[0]
        self.assertEqual(e1_entry.event_id, "evt-id-1")
        self.assertEqual(e1_entry.metadata["trace_id"], "tr-12345")
        self.assertEqual(e1_entry.metadata["error_code"], "ERR_500")

    def test_input_objects_not_mutated(self) -> None:
        """Verify that neither existing nor new input objects are mutated."""
        meta_exist = {"key": "val1"}
        meta_new = {"key": "val2"}
        e_exist = self._create_event("evt-e", 0, metadata=meta_exist)
        e_new = self._create_event("evt-n", 3, metadata=meta_new)

        existing_list = [e_exist]
        new_list = [e_new]

        res = self.engine.re_correlate(existing_list, new_list)

        # Mutate timeline entry metadata
        res.timeline.entries[0].metadata["key"] = "mutated"

        # Verify original objects remain untouched
        self.assertEqual(e_exist.metadata["key"], "val1")
        self.assertEqual(e_new.metadata["key"], "val2")
        self.assertEqual(len(existing_list), 1)
        self.assertEqual(len(new_list), 1)

    def test_recorrelation_determinism(self) -> None:
        """Verify re-correlation is completely deterministic across repeated executions."""
        existing = [self._create_event(f"evt-e-{i}", i * 5) for i in range(6)]
        new_events = [self._create_event(f"evt-n-{i}", i * 3 + 2) for i in range(4)]

        res1 = self.engine.re_correlate(existing, new_events)
        res2 = self.engine.re_correlate(existing, new_events)

        self.assertEqual(
            [c.incident_id for c in res1.clusters],
            [c.incident_id for c in res2.clusters],
        )
        self.assertEqual(
            [e.event_id for e in res1.timeline.entries],
            [e.event_id for e in res2.timeline.entries],
        )

    def test_empty_existing_events(self) -> None:
        """Verify re-correlating with empty existing events correctly correlates new events."""
        new_event = self._create_event("evt-solo", 0)
        res = self.engine.re_correlate([], [new_event])

        self.assertEqual(len(res.clusters), 1)
        self.assertEqual(res.timeline.event_count, 1)
        self.assertEqual(res.new_events_count, 1)
        self.assertEqual(res.total_events, 1)

    def test_empty_existing_and_empty_new_events(self) -> None:
        """Verify re-correlating with both empty produces an empty result cleanly."""
        res = self.engine.re_correlate([], [])
        self.assertEqual(len(res.clusters), 0)
        self.assertEqual(res.timeline.event_count, 0)
        self.assertEqual(res.total_events, 0)
        self.assertEqual(res.new_events_count, 0)

    def test_duplicate_new_event_id_handling(self) -> None:
        """Verify that duplicate event IDs between existing and new events are deterministically deduplicated."""
        e1 = self._create_event("evt-dup", 0, description="Original existing event")
        existing = [e1]

        # New event with identical event_id
        e_dup = self._create_event("evt-dup", 0, description="Duplicate incoming event")
        e_unique = self._create_event("evt-uniq", 4)

        res = self.engine.re_correlate(existing, [e_dup, e_unique])

        # Total unique events is 2 (existing preserved, duplicate ignored)
        self.assertEqual(res.total_events, 2)
        self.assertEqual(res.new_events_count, 1)  # Only evt-uniq is newly accepted
        self.assertEqual(res.timeline.entries[0].description, "Original existing event")

    def test_accepts_existing_clusters_or_timeline(self) -> None:
        """Verify re_correlate accepts prior IncidentClusters or UnifiedTimeline as existing input."""
        e1 = self._create_event("evt-1", 0)
        e2 = self._create_event("evt-2", 4)
        initial_clusters = self.engine.correlate([e1, e2])
        initial_timeline = build_timeline(initial_clusters)

        new_event = self._create_event("evt-3", 7)

        # 1. Passing IncidentCluster list as existing
        res_from_clusters = self.engine.re_correlate(initial_clusters, [new_event])
        self.assertEqual(res_from_clusters.timeline.event_count, 3)

        # 2. Passing UnifiedTimeline as existing
        res_from_timeline = self.engine.re_correlate(initial_timeline, [new_event])
        self.assertEqual(res_from_timeline.timeline.event_count, 3)

    def test_tuple_unpacking_support(self) -> None:
        """Verify ReCorrelationResult supports `clusters, timeline = re_correlate(...)`."""
        e1 = self._create_event("evt-1", 0)
        e2 = self._create_event("evt-2", 3)

        clusters, timeline = re_correlate([e1], [e2])

        self.assertIsInstance(clusters, list)
        self.assertIsInstance(timeline, UnifiedTimeline)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(timeline.event_count, 2)

    def test_end_to_end_recorrelation_lifecycle(self) -> None:
        """Comprehensive end-to-end test of the incident lifecycle:

        1. Initial alert + log arrive -> Initial cluster & timeline created.
        2. Customer complaint arrives 5m later -> Re-correlates and extends cluster.
        3. Database spike alert arrives on another service -> Re-correlates and creates 2nd cluster.
        4. Late deploy event arrives (occurred prior to incident) -> Re-correlates and backfills timeline start.
        """
        # Step 1: Initial events
        e_alert = self._create_event("evt-01", 10, component="auth-service", source="alerts", severity="HIGH")
        e_log = self._create_event("evt-02", 12, component="auth-service", source="logs", severity="CRITICAL")

        initial_clusters = correlate_events([e_alert, e_log])
        initial_timeline = build_timeline(initial_clusters)

        self.assertEqual(len(initial_clusters), 1)
        self.assertEqual(initial_timeline.event_count, 2)

        # Step 2: Customer complaint arrives at t=15m
        e_complaint = self._create_event("evt-03", 15, component="auth-service", source="complaints", severity="HIGH")
        res_step2 = re_correlate(initial_timeline, e_complaint)

        self.assertEqual(len(res_step2.clusters), 1)
        self.assertEqual(res_step2.timeline.event_count, 3)
        self.assertEqual(res_step2.clusters[0].event_ids, ["evt-01", "evt-02", "evt-03"])

        # Step 3: Database alert arrives at t=16m
        e_db = self._create_event("evt-04", 16, component="database", source="alerts", severity="CRITICAL")
        res_step3 = re_correlate(res_step2.timeline, e_db)

        self.assertEqual(len(res_step3.clusters), 2)  # auth-service + database
        self.assertEqual(res_step3.timeline.event_count, 4)
        self.assertEqual(res_step3.timeline.components, ["auth-service", "database"])

        # Step 4: Late deploy discovery at t=2m (preceded the incident)
        e_deploy = self._create_event("evt-00", 2, component="auth-service", source="deploys", severity="INFO")
        res_step4 = re_correlate(res_step3.timeline, e_deploy)

        self.assertEqual(res_step4.timeline.event_count, 5)
        # Verify evt-00 is placed at index 0 of the timeline
        self.assertEqual(res_step4.timeline.entries[0].event_id, "evt-00")
        self.assertEqual(res_step4.timeline.start_time, self.base_time + timedelta(minutes=2))
        self.assertEqual(res_step4.timeline.end_time, self.base_time + timedelta(minutes=16))


if __name__ == "__main__":
    unittest.main()
