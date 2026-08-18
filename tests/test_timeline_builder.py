"""Unit tests for RootLens Unified Incident Timeline Builder (Phase 3)."""

from datetime import datetime, timedelta, timezone
import unittest

from correlation.correlation_engine import CorrelationEngine
from correlation.timeline_builder import TimelineBuilder, build_timeline
from utils.schemas import IncidentCluster, NormalizedEvent, TimelineEntry, UnifiedTimeline


class TestTimelineBuilder(unittest.TestCase):
    """Comprehensive test suite for TimelineBuilder and UnifiedTimeline."""

    def setUp(self) -> None:
        """Set up standard timestamps and timeline builder instance."""
        self.base_time = datetime(2026, 8, 18, 10, 0, 0, tzinfo=timezone.utc)
        self.builder = TimelineBuilder()

    def _create_event(
        self,
        event_id: str,
        offset_minutes: float,
        component: str = "auth-service",
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

    def _create_cluster(
        self,
        incident_id: str,
        component: str,
        events: list,
    ) -> IncidentCluster:
        """Helper to create an IncidentCluster from a list of events."""
        if not events:
            return IncidentCluster(
                incident_id=incident_id,
                component=component,
                start_time=self.base_time,
                end_time=self.base_time,
                event_ids=[],
                events=[],
                event_count=0,
            )
        return IncidentCluster(
            incident_id=incident_id,
            component=component,
            start_time=events[0].timestamp,
            end_time=events[-1].timestamp,
            event_ids=[e.event_id for e in events],
            events=events,
            event_count=len(events),
        )

    def test_empty_input(self) -> None:
        """Verify empty input handling across None, empty list, and empty cluster."""
        t1 = self.builder.build(None)
        self.assertEqual(len(t1.entries), 0)
        self.assertIsNone(t1.start_time)
        self.assertIsNone(t1.end_time)
        self.assertEqual(t1.event_count, 0)
        self.assertEqual(t1.incident_ids, [])
        self.assertEqual(t1.components, [])

        t2 = self.builder.build([])
        self.assertEqual(len(t2.entries), 0)
        self.assertEqual(t2.event_count, 0)

        empty_cluster = self._create_cluster("inc-empty", "auth-service", [])
        t3 = self.builder.build([empty_cluster])
        self.assertEqual(len(t3.entries), 0)
        self.assertEqual(t3.event_count, 0)

        t4 = build_timeline([])
        self.assertEqual(len(t4.entries), 0)

    def test_single_incident_cluster(self) -> None:
        """Verify timeline construction from a single cluster."""
        e1 = self._create_event("evt-1", 0, component="order-service", severity="INFO")
        e2 = self._create_event("evt-2", 4, component="order-service", severity="CRITICAL")
        cluster = self._create_cluster("inc_order_01", "order-service", [e1, e2])

        # Test passing single cluster directly and inside a list
        for input_data in (cluster, [cluster]):
            timeline = self.builder.build(input_data)
            self.assertEqual(timeline.event_count, 2)
            self.assertEqual(len(timeline.entries), 2)
            self.assertEqual(timeline.incident_ids, ["inc_order_01"])
            self.assertEqual(timeline.components, ["order-service"])
            self.assertEqual(timeline.start_time, self.base_time)
            self.assertEqual(timeline.end_time, self.base_time + timedelta(minutes=4))

            self.assertEqual(timeline.entries[0].event_id, "evt-1")
            self.assertEqual(timeline.entries[0].incident_id, "inc_order_01")
            self.assertEqual(timeline.entries[1].event_id, "evt-2")
            self.assertEqual(timeline.entries[1].incident_id, "inc_order_01")

    def test_multiple_incident_clusters_chronological_ordering(self) -> None:
        """Verify multiple clusters from different components are merged and ordered chronologically."""
        e_auth1 = self._create_event("evt-auth-1", 0, component="auth-service")
        e_auth2 = self._create_event("evt-auth-2", 6, component="auth-service")
        cluster_auth = self._create_cluster("inc_auth_01", "auth-service", [e_auth1, e_auth2])

        e_pay1 = self._create_event("evt-pay-1", 2, component="payment-service")
        e_pay2 = self._create_event("evt-pay-2", 8, component="payment-service")
        cluster_pay = self._create_cluster("inc_pay_01", "payment-service", [e_pay1, e_pay2])

        e_db1 = self._create_event("evt-db-1", 1, component="database")
        e_db2 = self._create_event("evt-db-2", 10, component="database")
        cluster_db = self._create_cluster("inc_db_01", "database", [e_db1, e_db2])

        timeline = self.builder.build([cluster_auth, cluster_pay, cluster_db])

        self.assertEqual(timeline.event_count, 6)
        expected_event_order = [
            "evt-auth-1",  # 0m
            "evt-db-1",    # 1m
            "evt-pay-1",   # 2m
            "evt-auth-2",  # 6m
            "evt-pay-2",   # 8m
            "evt-db-2",    # 10m
        ]
        actual_event_order = [entry.event_id for entry in timeline.entries]
        self.assertEqual(actual_event_order, expected_event_order)

        self.assertEqual(timeline.start_time, self.base_time)
        self.assertEqual(timeline.end_time, self.base_time + timedelta(minutes=10))
        self.assertEqual(timeline.incident_ids, ["inc_auth_01", "inc_db_01", "inc_pay_01"])
        self.assertEqual(timeline.components, ["auth-service", "database", "payment-service"])

    def test_identical_timestamp_tie_breaker(self) -> None:
        """Verify that events with identical timestamps sort deterministically by event_id."""
        e_c = self._create_event("evt-c", 5, component="svc-a")
        e_a = self._create_event("evt-a", 5, component="svc-b")
        e_b = self._create_event("evt-b", 5, component="svc-c")

        c1 = self._create_cluster("inc-1", "svc-a", [e_c])
        c2 = self._create_cluster("inc-2", "svc-b", [e_a])
        c3 = self._create_cluster("inc-3", "svc-c", [e_b])

        timeline = self.builder.build([c1, c2, c3])

        self.assertEqual(timeline.event_count, 3)
        actual_ids = [entry.event_id for entry in timeline.entries]
        self.assertEqual(actual_ids, ["evt-a", "evt-b", "evt-c"])

    def test_preservation_of_all_event_fields(self) -> None:
        """Verify exact preservation of event_id, incident_id, timestamp, source, component, severity, description, metadata."""
        meta = {"region": "us-east-1", "http_status": 503, "nested": {"retry_count": 3}}
        event = self._create_event(
            event_id="evt-detailed-101",
            offset_minutes=3.5,
            component="checkout-api",
            source="logs",
            severity="CRITICAL",
            description="503 Service Unavailable downstream cascade",
            metadata=meta,
        )
        cluster = self._create_cluster("inc_checkout_99", "checkout-api", [event])

        timeline = self.builder.build(cluster)
        self.assertEqual(len(timeline.entries), 1)
        entry: TimelineEntry = timeline.entries[0]

        self.assertEqual(entry.event_id, "evt-detailed-101")
        self.assertEqual(entry.incident_id, "inc_checkout_99")
        self.assertEqual(entry.timestamp, self.base_time + timedelta(minutes=3.5))
        self.assertEqual(entry.source, "logs")
        self.assertEqual(entry.component, "checkout-api")
        self.assertEqual(entry.severity, "CRITICAL")
        self.assertEqual(entry.description, "503 Service Unavailable downstream cascade")
        self.assertEqual(entry.metadata, meta)
        self.assertEqual(entry.metadata["nested"]["retry_count"], 3)

    def test_every_event_preserved_exactly_once(self) -> None:
        """Verify that every unique event is present exactly once in the timeline."""
        events_1 = [self._create_event(f"evt-c1-{i}", i * 2, component="c1") for i in range(5)]
        events_2 = [self._create_event(f"evt-c2-{i}", i * 3, component="c2") for i in range(4)]
        cluster_1 = self._create_cluster("inc-1", "c1", events_1)
        cluster_2 = self._create_cluster("inc-2", "c2", events_2)

        timeline = self.builder.build([cluster_1, cluster_2])

        self.assertEqual(timeline.event_count, 9)
        all_ids = [e.event_id for e in timeline.entries]
        self.assertEqual(len(set(all_ids)), 9)

    def test_duplicate_event_prevention(self) -> None:
        """Verify that duplicate events across clusters are gracefully deduplicated."""
        e1 = self._create_event("evt-shared", 2, component="c1")
        e2 = self._create_event("evt-other", 4, component="c2")
        c1 = self._create_cluster("inc-1", "c1", [e1])
        c2 = self._create_cluster("inc-2", "c2", [e1, e2])  # e1 repeated in c2

        timeline = self.builder.build([c1, c2])

        self.assertEqual(timeline.event_count, 2)
        event_ids = [e.event_id for e in timeline.entries]
        self.assertEqual(event_ids, ["evt-shared", "evt-other"])

    def test_out_of_order_cluster_input(self) -> None:
        """Verify that passing clusters in reverse chronological order results in correctly sorted timeline."""
        e_late = self._create_event("evt-late", 30, component="c-late")
        e_mid = self._create_event("evt-mid", 15, component="c-mid")
        e_early = self._create_event("evt-early", 0, component="c-early")

        c_late = self._create_cluster("inc-late", "c-late", [e_late])
        c_mid = self._create_cluster("inc-mid", "c-mid", [e_mid])
        c_early = self._create_cluster("inc-early", "c-early", [e_early])

        # Reverse order
        timeline = self.builder.build([c_late, c_mid, c_early])

        self.assertEqual(timeline.event_count, 3)
        self.assertEqual(timeline.entries[0].event_id, "evt-early")
        self.assertEqual(timeline.entries[1].event_id, "evt-mid")
        self.assertEqual(timeline.entries[2].event_id, "evt-late")
        self.assertEqual(timeline.start_time, self.base_time)
        self.assertEqual(timeline.end_time, self.base_time + timedelta(minutes=30))

    def test_input_objects_not_mutated(self) -> None:
        """Verify that input NormalizedEvent and IncidentCluster objects are not mutated."""
        meta = {"key": "original_value"}
        event = self._create_event("evt-orig", 1, metadata=meta)
        cluster = self._create_cluster("inc-orig", "auth-service", [event])

        timeline = self.builder.build([cluster])

        # Mutate metadata in timeline entry
        timeline.entries[0].metadata["key"] = "modified_value"

        # Original event metadata must remain unchanged
        self.assertEqual(event.metadata["key"], "original_value")
        self.assertEqual(cluster.events[0].metadata["key"], "original_value")

    def test_end_to_end_correlation_to_timeline(self) -> None:
        """Integration test: Output of CorrelationEngine fed directly into TimelineBuilder."""
        events = [
            self._create_event("evt-auth-1", 0, component="auth-service", source="deploys"),
            self._create_event("evt-pay-1", 1, component="payment-gateway", source="alerts"),
            self._create_event("evt-auth-2", 4, component="auth-service", source="logs"),
            self._create_event("evt-pay-2", 5, component="payment-gateway", source="metrics"),
            self._create_event("evt-auth-3", 25, component="auth-service", source="complaints"),  # Separate incident
        ]

        engine = CorrelationEngine(time_window=timedelta(minutes=10))
        clusters = engine.correlate(events)

        # 2 auth clusters (0-4m and 25m) + 1 pay cluster (1-5m) = 3 clusters
        self.assertEqual(len(clusters), 3)

        timeline = build_timeline(clusters)

        self.assertEqual(timeline.event_count, 5)
        self.assertEqual(len(timeline.incident_ids), 3)
        self.assertEqual(
            [e.event_id for e in timeline.entries],
            ["evt-auth-1", "evt-pay-1", "evt-auth-2", "evt-pay-2", "evt-auth-3"],
        )
        self.assertEqual(timeline.start_time, self.base_time)
        self.assertEqual(timeline.end_time, self.base_time + timedelta(minutes=25))


if __name__ == "__main__":
    unittest.main()
