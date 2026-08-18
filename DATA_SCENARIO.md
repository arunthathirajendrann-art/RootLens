# DATA_SCENARIO: Incident Scenario & Data Blueprint
**Project:** Converting Production Signals into an Incident Response Plan (RootLens)  
**Role:** Member A — Data & Ingestion Lead  
**Document Version:** 1.0.0  
**Status:** Approved Scenario Baseline  

---

## 1. Incident Overview

- **Incident ID:** `INC-2026-8821`
- **Incident Name:** Checkout Service Latency Spike & Order Submission Degradation
- **Target Service:** `checkout-service`
- **Severity Level:** `P1 - CRITICAL`
- **Impact Summary:** Checkout API p99 latency spikes from 120ms to >4,500ms, causing HTTP 504 Gateway Timeouts, dropped checkout sessions, order failure rates surging to 18.5%, and widespread customer checkout failure complaints.

### Detailed Incident Description
At approximately 14:15 UTC on 2026-08-18, the e-commerce platform's core `checkout-service` experienced sudden and severe p99 latency degradation. Upstream API gateways began timing out while waiting for responses from `checkout-service` worker threads. The root trigger was an dynamic configuration push (`CFG-8912`) applied at 14:08 UTC that increased in-memory cart cache limits by 10x without heap adjustments, resulting in catastrophic memory exhaustion and frequent Stop-the-World garbage collection pauses. Triage is initially complicated by a clean deployment (`v2.14.0`) that completed at 14:00 UTC, acting as a prominent red herring.

---

## 2. Ground-Truth Causal Chain

The verified physical and logical sequence of causation is:

```
[1. Dynamic Config Change (CFG-8912)]
      │
      ▼
[2. In-Memory Cache Limit Expanded (10x items, TTL 1hr)]
      │
      ▼
[3. Heap Saturation & Memory Utilization > 88%]
      │
      ▼
[4. Severe Garbage Collection Pressure (Major GC Pauses > 3.8s)]
      │
      ▼
[5. Worker Thread Pool Starvation & Connection Queueing]
      │
      ▼
[6. Checkout Latency Increases (p99 Spikes to > 4,500ms)]
      │
      ▼
[7. Request Timeouts & HTTP 504 / 500 Errors (18.5% error rate)]
      │
      ▼
[8. Monitoring Alerts (PagerDuty P1) & Influx of Customer Complaints]
```

---

## 3. Realistic Incident Timeline

All timestamps are standardized in ISO-8601 UTC format.

| Timestamp (UTC) | Signal Source | Service / Component | Event Type / Telemetry | Details & Payload |
| :--- | :--- | :--- | :--- | :--- |
| **13:50:00** | Metrics | `checkout-service` | Baseline Metrics | Latency p99: 118ms, Error Rate: 0.01%, Memory: 44%, GC Pause: 12ms. |
| **13:52:00** | Metrics | `inventory-service` | Baseline Metrics | Latency p99: 34ms, CPU: 21%, Error Rate: 0.00%. |
| **13:55:00** | Deploys | `checkout-service` | Deploy Started | CI/CD pipeline starts rolling deploy for version `v2.14.0`. |
| **14:00:00** | Deploys | `checkout-service` | Deploy Completed **(RED HERRING)** | `v2.14.0` successfully deployed across all 12 pods. Health checks 100% green. |
| **14:00:00 – 14:07:00** | Metrics / Logs | `checkout-service` | Post-Deploy Steady State | Traffic served normally. p99 latency steady at 115–122ms. Zero anomalies. |
| **14:05:00** | Logs | `inventory-service` | Routine Cron Job | Background catalog sync completed (`batch_size=1200`, status: OK). |
| **14:08:15** | Config Service | `checkout-service` | Dynamic Config Applied **(ACTUAL ROOT CAUSE)** | `CFG-8912`: `cart_cache_max_items` changed from `5000` to `50000`, `cache_ttl_seconds` changed from `300` to `3600`. Applied via dynamic config provider. |
| **14:09:30** | Logs | `checkout-service` | App Log | `[INFO] CacheManager: Dynamic configuration reloaded. Max capacity set to 50,000 items.` |
| **14:11:00** | Metrics | `checkout-service` | Metric Ingestion | Memory consumption climbs rapidly: 45% → 68% → 82%. |
| **14:13:00** | Metrics | `checkout-service` | Metric Ingestion | Memory hits 89%. Major GC activity spikes. GC pause duration: 2,400ms. |
| **14:15:00** | Logs | `checkout-service` | App Log | `[WARN] GC overhead high: Full GC took 3820ms. 4 threads stalled.` |
| **14:16:30** | Metrics | `checkout-service` | Latency & Error Spike | p99 latency spikes to 4,620ms. HTTP 504 Gateway Timeouts reach 14.2%. |
| **14:18:00** | Metrics | `payment-service` | Metric Ingestion | Inbound request rate dips slightly due to upstream checkout timeouts; service health remains 100% green (p99: 175ms). |
| **14:20:00** | Alerts | `checkout-service` | PagerDuty Alert (P1) | `[CRITICAL] CheckoutServiceHighLatency: p99 > 3000ms for 5m (current: 4580ms)`. |
| **14:21:30** | Alerts | `checkout-service` | PagerDuty Alert (P2) | `[HIGH] CheckoutServiceElevated5xx: 5xx error rate > 5% (current: 18.5%)`. |
| **14:23:00** | Complaints | Customer Support | Zendesk / Ticket Influx | Customer tickets surge: "Checkout button spinning forever", "Error 504 on payment step". |
| **14:26:00** | Complaints | Social / Escalations | CS Escalation | "VIP customer unable to complete purchase; cart checkout failing on web & mobile." |
| **14:30:00** | System / APM | Central Ingestion | **LATE-ARRIVING EVENT** (Injected during demo) | Centralized audit log and APM JVM GC trace flushed into ingestion pipeline. |
| **14:35:00** | Remediation | `checkout-service` | Config Rollback | Config reverted: `cart_cache_max_items` restored to `5000`, `cache_ttl_seconds` restored to `300`. |
| **14:38:00** | Metrics | `checkout-service` | Recovery Verified | Memory drops to 41%, GC pauses <18ms, p99 latency recovers to 114ms, error rate drops to 0.00%. |

---

## 4. Root Cause vs. Red Herring Analysis

### Actual Root Cause
- **Trigger:** Dynamic runtime configuration update `CFG-8912` deployed at 14:08:15 UTC.
- **Mechanism:** The update changed the local LRU/in-memory cart cache configuration:
  - `cart_cache_max_items`: `5,000` → `50,000` (10x increase)
  - `cache_ttl_seconds`: `300` → `3,600` (12x retention extension)
- **Technical Consequence:** Because JVM/container heap allocation was fixed at 2GB (`-Xmx2g`), retaining up to 50,000 hydrated user carts rapidly saturated the tenured memory space. The JVM entered continuous Stop-The-World (STW) Major GC cycles, pausing all request handling for 2–4 seconds at a time. This caused HTTP connection starvation and cascading 504 timeouts.

### Red Herring
- **Event:** Production code deployment `checkout-service:v2.14.0` at 14:00:00 UTC.
- **Why it is Misleading:** 
  - Deployments are traditionally the primary suspect in incident response.
  - The deployment occurred only 15 minutes before the latency alert fired.
  - Junior on-call engineers or naive correlation algorithms will correlate the deployment timestamp with the incident window.
- **Why it is Inoculated (False Cause):**
  - **8-Minute Stable Window:** Between 14:00:00 and 14:08:00 UTC, the newly deployed code served production traffic with zero latency spikes, zero memory growth, and 0.01% error rates.
  - **Benign Change Scope:** Git diff for `v2.14.0` consists solely of UI copy changes and updated receipt date-formatting utilities.
  - **Canary & Unit Verification:** Automated canary analysis at 14:00:00 UTC passed with 100% health score.

---

## 5. Background & Unrelated Signals (Noise Data)

To test signal filtering and prevent false-positive correlation, the following background signals are included in the scenario:

1. **`inventory-service` Activity:**
   - Routine catalog sync cron execution at 14:05:00 UTC.
   - Normal background log messages: `CatalogSyncWorker: 1200 items updated in 420ms`.
   - Latency remained healthy at p99 = 34ms throughout the entire incident.
2. **`payment-service` Telemetry:**
   - 3rd-party payment gateway ping checks reporting nominal response times (180ms).
   - Inbound throughput to `payment-service` dropped slightly starting at 14:18 UTC because users were getting timed out upstream on `checkout-service`, not because `payment-service` was malfunctioning.
3. **`auth-service` & `shipping-service`:**
   - Standard token validation logs and shipping rate queries operating with zero error anomalies.

---

## 6. Evidentiary Criteria

### A. Evidence Supporting the Genuine Cause (Config Change)
1. **Direct Temporal Precedence:** Memory slope increases immediately following 14:08:15 UTC (config reload event).
2. **Log Correlation:** `checkout-service` logs at 14:09:30 UTC explicitly confirm `CacheManager: Dynamic configuration reloaded. Max capacity set to 50,000 items`.
3. **Resource Metrics Correlation:** GC pause time metric directly mirrors the p99 latency curve with a Pearson correlation $> 0.95$.
4. **Diagnostic Proof:** Heap telemetry indicates `OldGen` memory allocation reached 98% occupancy, triggering `ConcurrentMarkSweep / G1GC Full GC` stalls.

### B. Evidence Refuting the Red Herring (Deployment)
1. **Steady-State Counter-Evidence:** Production metrics from 14:00:00 to 14:08:00 UTC show 8 uninterrupted minutes of p99 latency $< 125\text{ms}$.
2. **Absence of Code Regressions:** Deploy logs for `v2.14.0` record successful container startup and healthy readiness probes across all replica pods.
3. **Scope Non-Overlap:** The deployment did not alter memory allocation flags, caching algorithms, or database connection pools.

---

## 7. Late-Arriving Evidence Event (Demo Injection Blueprint)

During the interactive demonstration of the RootLens system, a key capability is demonstrating how the system updates its hypotheses dynamically when new evidence surfaces.

### Injection Plan
1. **Initial State (Triage Phase 1):**
   - The user/agent initially only has access to:
     - The deploy event (`v2.14.0` at 14:00 UTC)
     - High-level P1 latency alerts (14:20 UTC)
     - Customer complaints (14:23 UTC)
   - *Initial AI reasoning state:* The system considers the deployment a high-probability suspect due to temporal proximity.

2. **Late-Arriving Injected Events (Triage Phase 2 - Injected at 14:30:00 UTC simulated time):**
   - **Signal 1 (Audit Log):** Centralized configuration repository audit log (`audit_config_changes.log`):
     ```json
     {
       "timestamp": "2026-08-18T14:08:15Z",
       "service": "checkout-service",
       "event_type": "CONFIG_UPDATE",
       "change_id": "CFG-8912",
       "author": "growth-platform-team@company.internal",
       "parameters_changed": {
         "cart_cache_max_items": { "previous": 5000, "new": 50000 },
         "cache_ttl_seconds": { "previous": 300, "new": 3600 }
       },
       "restart_required": false
     }
     ```
   - **Signal 2 (Runtime GC Profiling Trace):** Deep telemetry exporter log (`gc_profiler.log`):
     ```json
     {
       "timestamp": "2026-08-18T14:14:55Z",
       "service": "checkout-service",
       "event_type": "GC_MAJOR_PAUSE",
       "duration_ms": 3820,
       "gc_cause": "Allocation Failure in Old Gen",
       "heap_used_mb": 1940,
       "heap_max_mb": 2048
     }
     ```

3. **Expected Cognitive Shift:**
   - The correlation and hypothesis generation engine absorbs the late-arriving signals.
   - Confidence in the "Deployment Bug" hypothesis drops significantly (e.g., from 85% to 15%).
   - Confidence in the "Memory Leak / Cache Config Heap Exhaustion" hypothesis rises to primary position (>90%).
   - The recovery planner switches recommendations from "Rollback Deployment v2.14.0" to "Revert Config Change CFG-8912".

---

## 8. Data Source Blueprint for Phase 2 Implementation

When datasets are generated in Phase 2, they will populate the `data/` directory according to the following file mapping:

| File Path | Format | Planned Contents |
| :--- | :--- | :--- |
| `data/alerts.json` | JSON | P1 and P2 PagerDuty alerts for latency, error rates, and healthy threshold pings. |
| `data/deploys.json` | JSON | Deployment records for `checkout-service:v2.14.0` (Red Herring) and historical deploys. |
| `data/logs.json` | JSON | Application logs from `checkout-service`, `inventory-service`, and `payment-service`. |
| `data/metrics.csv` | CSV | Time-series metrics (p50/p90/p99 latency, error rates, CPU, memory, GC pause time) sampled at 1-minute intervals from 13:50 to 14:45 UTC. |
| `data/complaints.json` | JSON | Customer support tickets and user feedback reports detailing failure symptoms. |
| `data/past_incidents.json`| JSON | Historical incident memory records (including past config-induced memory incidents) for learning retrieval. |
