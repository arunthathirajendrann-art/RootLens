"""Final Member B Integration and Validation Tests (Phase 5).

Verifies the complete end-to-end integration of Member B's pipeline:
NormalizedEvent -> CorrelationEngine -> IncidentCluster -> TimelineBuilder -> UnifiedTimeline -> Re-correlation
"""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from correlation.correlation_engine import CorrelationEngine, correlate_events, re_correlate
from correlation.timeline_builder import TimelineBuilder, build_timeline
from utils.schemas import (
    IncidentCluster,
    NormalizedEvent,
    ReCorrelationResult,
    TimelineEntry,
    UnifiedTimeline,
)


class TestMemberBIntegration(unittest.TestCase):
    """End-to-end integration and public interface test suite for Member B."""

    def setUp(self) -> None:
        """Set up standard base timestamp and engine."""
        self.base_time = datetime(2026, 8, 18, 10, 0, 0, tzinfo=timezone.utc)
        self.engine = CorrelationEngine(time_window=timedelta(minutes=10))

    def _create_event(
        self,
        event_id: str,
        offset_minutes: float,
        component: str = "checkout-service",
        source: str = "alerts",
        severity: str = "HIGH",
        description: str = "Sample observability event",
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

    def test_01_normalized_events_enter_correlation_engine(self) -> None:
        """1. Verify NormalizedEvents can enter CorrelationEngine successfully."""
        events = [
            self._create_event("evt-1", 0),
            self._create_event("evt-2", 4),
        ]
        clusters = self.engine.correlate(events)
        self.assertIsInstance(clusters, list)
        self.assertEqual(len(clusters), 1)

    def test_02_correlation_engine_produces_valid_incident_clusters(self) -> None:
        """2. Verify CorrelationEngine produces valid IncidentClusters with complete metadata."""
        events = [
            self._create_event("evt-1", 0, component="auth-service"),
            self._create_event("evt-2", 5, component="auth-service"),
        ]
        clusters = self.engine.correlate(events)
        self.assertEqual(len(clusters), 1)
        cluster: IncidentCluster = clusters[0]

        self.assertTrue(cluster.incident_id.startswith("inc_auth_service_"))
        self.assertEqual(cluster.component, "auth-service")
        self.assertEqual(cluster.start_time, self.base_time)
        self.assertEqual(cluster.end_time, self.base_time + timedelta(minutes=5))
        self.assertEqual(cluster.event_count, 2)
        self.assertEqual(cluster.event_ids, ["evt-1", "evt-2"])
        self.assertEqual(len(cluster.events), 2)

    def test_03_timeline_builder_consumes_clusters(self) -> None:
        """3. Verify TimelineBuilder consumes IncidentClusters cleanly."""
        events = [self._create_event("evt-1", 0, component="order-api")]
        clusters = self.engine.correlate(events)

        timeline = TimelineBuilder().build(clusters)
        self.assertIsInstance(timeline, UnifiedTimeline)
        self.assertEqual(timeline.event_count, 1)

    def test_04_unified_timeline_contains_all_expected_events(self) -> None:
        """4. Verify UnifiedTimeline contains all expected events from all clusters."""
        e1 = self._create_event("evt-1", 0, component="svc-a")
        e2 = self._create_event("evt-2", 2, component="svc-b")
        e3 = self._create_event("evt-3", 4, component="svc-a")

        clusters = self.engine.correlate([e1, e2, e3])
        timeline = build_timeline(clusters)

        self.assertEqual(timeline.event_count, 3)
        self.assertEqual(
            set(entry.event_id for entry in timeline.entries),
            {"evt-1", "evt-2", "evt-3"},
        )

    def test_05_timeline_ordering_is_chronological(self) -> None:
        """5. Verify global timeline ordering is strictly chronological across services."""
        e_pay = self._create_event("evt-pay", 4, component="payment-service")
        e_auth = self._create_event("evt-auth", 1, component="auth-service")
        e_db = self._create_event("evt-db", 6, component="database")

        clusters = self.engine.correlate([e_pay, e_auth, e_db])
        timeline = build_timeline(clusters)

        self.assertEqual(
            [entry.event_id for entry in timeline.entries],
            ["evt-auth", "evt-pay", "evt-db"],
        )
        self.assertEqual(timeline.start_time, self.base_time + timedelta(minutes=1))
        self.assertEqual(timeline.end_time, self.base_time + timedelta(minutes=6))

    def test_06_new_normalized_event_can_be_re_correlated(self) -> None:
        """6. Verify a new normalized event can be dynamically re-correlated."""
        initial_events = [self._create_event("evt-1", 0)]
        initial_clusters = self.engine.correlate(initial_events)
        initial_timeline = build_timeline(initial_clusters)

        new_event = self._create_event("evt-new", 5)
        res = self.engine.re_correlate(initial_timeline, new_event)

        self.assertIsInstance(res, ReCorrelationResult)
        self.assertEqual(res.new_events_count, 1)
        self.assertEqual(res.total_events, 2)

    def test_07_existing_events_remain_preserved(self) -> None:
        """7. Verify existing events remain fully preserved in content and ID."""
        meta = {"trace_id": "tr-abc-123", "region": "us-east-1"}
        e1 = self._create_event("evt-1", 0, description="Critical crash", metadata=meta)
        initial_clusters = self.engine.correlate([e1])

        new_event = self._create_event("evt-2", 4)
        res = self.engine.re_correlate(initial_clusters, new_event)

        entry_1 = next(e for e in res.timeline.entries if e.event_id == "evt-1")
        self.assertEqual(entry_1.description, "Critical crash")
        self.assertEqual(entry_1.metadata, meta)
        self.assertEqual(entry_1.source, "alerts")
        self.assertEqual(entry_1.component, "checkout-service")

    def test_08_new_events_appear_exactly_once(self) -> None:
        """8. Verify newly added events appear exactly once in the updated timeline."""
        existing = [self._create_event("evt-e1", 0), self._create_event("evt-e2", 2)]
        new_events = [self._create_event("evt-n1", 4), self._create_event("evt-n2", 6)]

        res = self.engine.re_correlate(existing, new_events)
        event_ids = [e.event_id for e in res.timeline.entries]

        self.assertEqual(len(event_ids), 4)
        self.assertEqual(len(set(event_ids)), 4)
        self.assertEqual(sorted(event_ids), ["evt-e1", "evt-e2", "evt-n1", "evt-n2"])

    def test_09_updated_timeline_remains_chronological(self) -> None:
        """9. Verify updated timeline after re-correlation maintains strict chronological order."""
        existing = [self._create_event("evt-2", 5), self._create_event("evt-4", 15)]
        # Incoming out-of-order events
        new_events = [self._create_event("evt-1", 1), self._create_event("evt-3", 10)]

        res = self.engine.re_correlate(existing, new_events)

        ordered_ids = [e.event_id for e in res.timeline.entries]
        self.assertEqual(ordered_ids, ["evt-1", "evt-2", "evt-3", "evt-4"])

    def test_10_different_components_remain_separated(self) -> None:
        """10. Verify different components remain in separate clusters under Phase 2 correlation semantics."""
        events = [
            self._create_event("evt-auth", 2, component="auth-service"),
            self._create_event("evt-pay", 2, component="payment-gateway"),
            self._create_event("evt-db", 2, component="database"),
        ]

        clusters = self.engine.correlate(events)
        self.assertEqual(len(clusters), 3)
        components = [c.component for c in clusters]
        self.assertEqual(sorted(components), ["auth-service", "database", "payment-gateway"])

        # Re-correlate with an additional service
        e_msg = self._create_event("evt-msg", 3, component="message-broker")
        res = self.engine.re_correlate(clusters, e_msg)
        self.assertEqual(len(res.clusters), 4)

    def test_11_exact_time_window_boundary_remains_consistent(self) -> None:
        """11. Verify exact 10-minute window boundary rule (inclusive <=) remains consistent."""
        e1 = self._create_event("evt-1", 0)
        e_boundary = self._create_event("evt-boundary", 10.0)

        # Delta is exactly 10.0 minutes -> within window (1 cluster)
        res_boundary = self.engine.re_correlate([e1], e_boundary)
        self.assertEqual(len(res_boundary.clusters), 1)
        self.assertEqual(res_boundary.clusters[0].event_ids, ["evt-1", "evt-boundary"])

        # Delta is 10.01 minutes -> outside window (2 clusters)
        e_outside = self._create_event("evt-outside", 10.01)
        res_outside = self.engine.re_correlate([e1], e_outside)
        self.assertEqual(len(res_outside.clusters), 2)

    def test_12_out_of_order_new_signals_handled(self) -> None:
        """12. Verify out-of-order arriving signals are chronologically backfilled."""
        # Incident in progress at t=10m and t=14m
        existing = [self._create_event("evt-10", 10), self._create_event("evt-14", 14)]
        initial_timeline = build_timeline(self.engine.correlate(existing))

        # Root trigger deploy event arrived late, happened at t=0m
        e_deploy = self._create_event("evt-00", 0, source="deploys")
        res = self.engine.re_correlate(initial_timeline, e_deploy)

        self.assertEqual(res.timeline.entries[0].event_id, "evt-00")
        self.assertEqual(res.timeline.start_time, self.base_time)

    def test_13_duplicate_event_ids_remain_deterministic(self) -> None:
        """13. Verify duplicate event IDs are deterministically deduplicated."""
        e1 = self._create_event("evt-dup", 0, description="First known payload")
        existing = [e1]

        # Duplicate signal arriving with same ID
        e1_dup = self._create_event("evt-dup", 0, description="Duplicate incoming payload")
        e2_unique = self._create_event("evt-unique", 3)

        res = self.engine.re_correlate(existing, [e1_dup, e2_unique])

        self.assertEqual(res.total_events, 2)
        self.assertEqual(res.new_events_count, 1)
        self.assertEqual(res.timeline.entries[0].description, "First known payload")

    def test_14_no_input_objects_are_mutated(self) -> None:
        """14. Verify input event and cluster objects are strictly not mutated."""
        meta = {"original_param": "safe"}
        e1 = self._create_event("evt-1", 0, metadata=meta)
        e2 = self._create_event("evt-2", 4)
        input_list = [e1, e2]

        clusters = self.engine.correlate(input_list)
        timeline = build_timeline(clusters)
        res = self.engine.re_correlate(timeline, self._create_event("evt-3", 8))

        # Mutate resulting entry metadata
        res.timeline.entries[0].metadata["original_param"] = "tampered"

        # Verify source metadata was protected
        self.assertEqual(e1.metadata["original_param"], "safe")
        self.assertEqual(len(input_list), 2)

    def test_15_full_member_b_pipeline_works_end_to_end(self) -> None:
        """15. Verify complete Member B end-to-end pipeline:

        Raw event dictionaries -> CorrelationEngine -> IncidentClusters -> TimelineBuilder -> UnifiedTimeline -> Re-correlation -> Updated Timeline
        """
        # Step A: Ingested events (as dictionaries or NormalizedEvent objects)
        raw_events = [
            {
                "event_id": "alert-101",
                "timestamp": "2026-08-18T10:00:00Z",
                "source": "alerts",
                "component": "order-service",
                "severity": "HIGH",
                "description": "500 Error rate spike above 5%",
                "metadata": {"error_rate": 0.075},
            },
            {
                "event_id": "log-102",
                "timestamp": "2026-08-18T10:03:30Z",
                "source": "logs",
                "component": "order-service",
                "severity": "CRITICAL",
                "description": "Connection pool exhausted on database",
                "metadata": {"pool_size": 20},
            },
            {
                "event_id": "metric-201",
                "timestamp": "2026-08-18T10:02:00Z",
                "source": "metrics",
                "component": "inventory-db",
                "severity": "HIGH",
                "description": "CPU utilization 98%",
                "metadata": {"cpu_pct": 98.4},
            },
        ]

        # Step B: Initial correlation
        initial_clusters = correlate_events(raw_events, time_window=timedelta(minutes=10))
        self.assertEqual(len(initial_clusters), 2)  # order-service and inventory-db

        # Step C: Initial unified timeline
        initial_timeline = build_timeline(initial_clusters)
        self.assertEqual(initial_timeline.event_count, 3)
        self.assertEqual(
            [e.event_id for e in initial_timeline.entries],
            ["alert-101", "metric-201", "log-102"],
        )
        self.assertEqual(len(initial_timeline.incident_ids), 2)

        # Step D: Mid-incident signal arrives (customer complaint for order-service)
        complaint_signal = {
            "event_id": "comp-301",
            "timestamp": "2026-08-18T10:06:00Z",
            "source": "complaints",
            "component": "order-service",
            "severity": "CRITICAL",
            "description": "Checkout button non-responsive for user",
            "metadata": {"user_id": "usr-8821"},
        }

        # Step E: Trigger dynamic re-correlation
        updated_clusters, updated_timeline = re_correlate(
            existing_events=initial_timeline,
            new_events=complaint_signal,
        )

        self.assertEqual(len(updated_clusters), 2)
        self.assertEqual(updated_timeline.event_count, 4)
        self.assertEqual(
            [e.event_id for e in updated_timeline.entries],
            ["alert-101", "metric-201", "log-102", "comp-301"],
        )
        self.assertEqual(updated_timeline.start_time, self.base_time)
        self.assertEqual(
            updated_timeline.end_time, self.base_time + timedelta(minutes=6)
        )


if __name__ == "__main__":
    unittest.main()
