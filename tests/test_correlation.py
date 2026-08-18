"""Unit tests for RootLens Correlation Engine (Phase 2)."""

from datetime import datetime, timedelta, timezone
import random
import unittest

from correlation.correlation_engine import (
    CorrelationEngine,
    correlate_events,
    extract_normalized_event,
)
from utils.schemas import IncidentCluster, NormalizedEvent


class TestCorrelationEngine(unittest.TestCase):
    """Test suite for the temporal and component-based correlation engine."""

    def setUp(self) -> None:
        """Set up test timestamps and default engine."""
        self.base_time = datetime(2026, 8, 18, 10, 0, 0, tzinfo=timezone.utc)
        self.engine = CorrelationEngine(time_window=timedelta(minutes=10))

    def _create_event(
        self,
        event_id: str,
        offset_minutes: float,
        component: str = "auth-service",
        source: str = "alerts",
        severity: str = "HIGH",
        description: str = "Test event description",
    ) -> NormalizedEvent:
        """Helper to create a NormalizedEvent with a relative timestamp offset."""
        ts = self.base_time + timedelta(minutes=offset_minutes)
        return NormalizedEvent(
            event_id=event_id,
            timestamp=ts,
            source=source,
            component=component,
            severity=severity,
            description=description,
        )

    def test_empty_input(self) -> None:
        """Verify empty event lists return empty cluster lists."""
        self.assertEqual(self.engine.correlate([]), [])
        self.assertEqual(self.engine.correlate(None), [])
        self.assertEqual(correlate_events([]), [])

    def test_single_event(self) -> None:
        """Verify single event produces exactly one cluster with matching metadata."""
        event = self._create_event("evt-1", 0, component="payment-gateway")
        clusters = self.engine.correlate([event])

        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster.component, "payment-gateway")
        self.assertEqual(cluster.event_count, 1)
        self.assertEqual(cluster.event_ids, ["evt-1"])
        self.assertEqual(cluster.start_time, self.base_time)
        self.assertEqual(cluster.end_time, self.base_time)
        self.assertEqual(len(cluster.events), 1)
        self.assertEqual(cluster.events[0].event_id, "evt-1")

    def test_same_component_close_timestamps(self) -> None:
        """Verify events on the same component within the 10-min window merge into one cluster."""
        e1 = self._create_event("evt-1", 0, component="auth-service")
        e2 = self._create_event("evt-2", 3, component="auth-service")
        e3 = self._create_event("evt-3", 7, component="auth-service")

        clusters = self.engine.correlate([e1, e2, e3])

        self.assertEqual(len(clusters), 1)
        cluster = clusters[0]
        self.assertEqual(cluster.component, "auth-service")
        self.assertEqual(cluster.event_count, 3)
        self.assertEqual(cluster.event_ids, ["evt-1", "evt-2", "evt-3"])
        self.assertEqual(cluster.start_time, self.base_time)
        self.assertEqual(cluster.end_time, self.base_time + timedelta(minutes=7))

    def test_same_component_outside_window(self) -> None:
        """Verify events on the same component separated by > window split into separate clusters."""
        e1 = self._create_event("evt-1", 0, component="auth-service")
        e2 = self._create_event("evt-2", 5, component="auth-service")
        # Gap between e2 (5m) and e3 (20m) is 15m > 10m window
        e3 = self._create_event("evt-3", 20, component="auth-service")
        e4 = self._create_event("evt-4", 25, component="auth-service")

        clusters = self.engine.correlate([e1, e2, e3, e4])

        self.assertEqual(len(clusters), 2)
        self.assertEqual(clusters[0].event_ids, ["evt-1", "evt-2"])
        self.assertEqual(clusters[0].start_time, self.base_time)
        self.assertEqual(clusters[0].end_time, self.base_time + timedelta(minutes=5))

        self.assertEqual(clusters[1].event_ids, ["evt-3", "evt-4"])
        self.assertEqual(clusters[1].start_time, self.base_time + timedelta(minutes=20))
        self.assertEqual(clusters[1].end_time, self.base_time + timedelta(minutes=25))

    def test_different_components_close_timestamps(self) -> None:
        """Verify events from different components at identical/close times remain separate."""
        e1 = self._create_event("evt-auth", 0, component="auth-service")
        e2 = self._create_event("evt-pay", 1, component="payment-gateway")
        e3 = self._create_event("evt-db", 2, component="database-cluster")

        clusters = self.engine.correlate([e1, e2, e3])

        self.assertEqual(len(clusters), 3)
        components = [c.component for c in clusters]
        self.assertIn("auth-service", components)
        self.assertIn("payment-gateway", components)
        self.assertIn("database-cluster", components)

        for c in clusters:
            self.assertEqual(c.event_count, 1)

    def test_multiple_sources_same_component(self) -> None:
        """Verify signals from different sources (alert, log, deploy, metric) for same component correlate."""
        e1 = self._create_event("evt-deploy", 0, component="checkout-api", source="deploys", severity="INFO")
        e2 = self._create_event("evt-metric", 2, component="checkout-api", source="metrics", severity="HIGH")
        e3 = self._create_event("evt-alert", 4, component="checkout-api", source="alerts", severity="CRITICAL")
        e4 = self._create_event("evt-log", 5, component="checkout-api", source="logs", severity="CRITICAL")
        e5 = self._create_event("evt-complaint", 8, component="checkout-api", source="complaints", severity="HIGH")

        clusters = self.engine.correlate([e1, e2, e3, e4, e5])

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].component, "checkout-api")
        self.assertEqual(clusters[0].event_count, 5)
        self.assertEqual(
            clusters[0].event_ids,
            ["evt-deploy", "evt-metric", "evt-alert", "evt-log", "evt-complaint"],
        )

    def test_out_of_order_input_sorting(self) -> None:
        """Verify that shuffled input events are sorted chronologically before correlation."""
        e1 = self._create_event("evt-1", 0)
        e2 = self._create_event("evt-2", 2)
        e3 = self._create_event("evt-3", 5)
        e4 = self._create_event("evt-4", 8)

        shuffled = [e3, e1, e4, e2]
        clusters = self.engine.correlate(shuffled)

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].event_ids, ["evt-1", "evt-2", "evt-3", "evt-4"])
        self.assertEqual(clusters[0].start_time, self.base_time)
        self.assertEqual(clusters[0].end_time, self.base_time + timedelta(minutes=8))

    def test_exact_window_boundary_behavior(self) -> None:
        """Verify documented inclusive boundary behavior (delta == window belongs to same cluster)."""
        # Exactly 10 minutes delta: inclusive => 1 cluster
        e1 = self._create_event("evt-1", 0)
        e2 = self._create_event("evt-2", 10.0)  # delta is exactly 10 min

        clusters_boundary = self.engine.correlate([e1, e2])
        self.assertEqual(len(clusters_boundary), 1)
        self.assertEqual(clusters_boundary[0].event_ids, ["evt-1", "evt-2"])

        # 10 minutes and 1 millisecond: outside => 2 clusters
        e3 = self._create_event("evt-3", 10.0001)
        clusters_outside = self.engine.correlate([e1, e3])
        self.assertEqual(len(clusters_outside), 2)

    def test_identical_timestamps(self) -> None:
        """Verify events with identical timestamps are handled deterministically."""
        e1 = self._create_event("evt-b", 0, component="search-service")
        e2 = self._create_event("evt-a", 0, component="search-service")
        e3 = self._create_event("evt-c", 0, component="search-service")

        clusters = self.engine.correlate([e1, e2, e3])

        self.assertEqual(len(clusters), 1)
        # Secondary sort key is event_id
        self.assertEqual(clusters[0].event_ids, ["evt-a", "evt-b", "evt-c"])
        self.assertEqual(clusters[0].start_time, self.base_time)
        self.assertEqual(clusters[0].end_time, self.base_time)

    def test_all_events_preserved_exactly_once(self) -> None:
        """Verify that every input event appears exactly once in the resulting clusters."""
        events = [
            self._create_event(f"evt-auth-{i}", i * 3, component="auth-service")
            for i in range(10)
        ] + [
            self._create_event(f"evt-pay-{i}", i * 15, component="payment-gateway")
            for i in range(5)
        ] + [
            self._create_event(f"evt-db-{i}", i * 2, component="database")
            for i in range(4)
        ]

        # Randomize input order
        random.seed(42)
        shuffled = list(events)
        random.shuffle(shuffled)

        clusters = self.engine.correlate(shuffled)

        clustered_event_ids = []
        for cluster in clusters:
            clustered_event_ids.extend(cluster.event_ids)

        expected_event_ids = sorted([e.event_id for e in events])
        actual_event_ids = sorted(clustered_event_ids)

        self.assertEqual(len(clustered_event_ids), len(events))
        self.assertEqual(actual_event_ids, expected_event_ids)
        self.assertEqual(len(set(clustered_event_ids)), len(events))

    def test_sliding_window_chaining(self) -> None:
        """Verify sliding window chaining: consecutive events <= 10m apart extend active cluster."""
        # e1: 0m, e2: 8m (gap 8m <= 10m), e3: 16m (gap from e2 is 8m <= 10m)
        # Total span 16m, but no consecutive gap > 10m => 1 cluster
        e1 = self._create_event("evt-1", 0)
        e2 = self._create_event("evt-2", 8)
        e3 = self._create_event("evt-3", 16)

        clusters = self.engine.correlate([e1, e2, e3])

        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].event_ids, ["evt-1", "evt-2", "evt-3"])
        self.assertEqual(clusters[0].start_time, self.base_time)
        self.assertEqual(clusters[0].end_time, self.base_time + timedelta(minutes=16))

    def test_configurable_time_window(self) -> None:
        """Verify configurable time window with timedelta and numeric values."""
        e1 = self._create_event("evt-1", 0)
        e2 = self._create_event("evt-2", 4)

        # 3-minute window => splits into 2 clusters
        engine_3m = CorrelationEngine(time_window=timedelta(minutes=3))
        self.assertEqual(len(engine_3m.correlate([e1, e2])), 2)

        # 5-minute window via seconds => 1 cluster
        engine_5m = CorrelationEngine(time_window_seconds=300)
        self.assertEqual(len(engine_5m.correlate([e1, e2])), 1)

        # 5-minute window via numeric seconds => 1 cluster
        engine_num = CorrelationEngine(time_window=300)
        self.assertEqual(len(engine_num.correlate([e1, e2])), 1)

    def test_dictionary_input_handling(self) -> None:
        """Verify correlation engine cleanly accepts raw dictionary event objects."""
        dict_events = [
            {
                "event_id": "dict-1",
                "timestamp": "2026-08-18T10:00:00Z",
                "source": "alerts",
                "component": "order-service",
                "severity": "HIGH",
                "description": "Order processing delayed",
                "metadata": {"queue_depth": 450},
            },
            {
                "event_id": "dict-2",
                "timestamp": "2026-08-18T10:04:30+00:00",
                "source": "logs",
                "component": "order-service",
                "severity": "CRITICAL",
                "description": "Timeout connecting to inventory",
            },
        ]

        clusters = correlate_events(dict_events)
        self.assertEqual(len(clusters), 1)
        self.assertEqual(clusters[0].component, "order-service")
        self.assertEqual(clusters[0].event_ids, ["dict-1", "dict-2"])
        self.assertEqual(clusters[0].event_count, 2)
        self.assertIsInstance(clusters[0].start_time, datetime)
        self.assertEqual(clusters[0].start_time.tzinfo, timezone.utc)

    def test_missing_required_fields_raises_error(self) -> None:
        """Verify that malformed events without required fields raise clear ValueError."""
        with self.assertRaises(ValueError):
            extract_normalized_event({"timestamp": "2026-08-18T10:00:00Z", "component": "svc"})

        with self.assertRaises(ValueError):
            extract_normalized_event({"event_id": "e1", "timestamp": None, "component": "svc"})

        with self.assertRaises(ValueError):
            extract_normalized_event({"event_id": "e1", "timestamp": "invalid-time", "component": "svc"})

        with self.assertRaises(TypeError):
            extract_normalized_event(12345)

    def test_invalid_time_window_initialization(self) -> None:
        """Verify invalid time windows raise appropriate errors."""
        with self.assertRaises(ValueError):
            CorrelationEngine(time_window=timedelta(seconds=0))

        with self.assertRaises(ValueError):
            CorrelationEngine(time_window=-10)

        with self.assertRaises(ValueError):
            CorrelationEngine(time_window_seconds=-5)

        with self.assertRaises(TypeError):
            CorrelationEngine(time_window="invalid")  # type: ignore


if __name__ == "__main__":
    unittest.main()
