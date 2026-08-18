import React, { useState } from 'react';

// Unified Initial Telemetry & Incident Signals (chronological)
const INITIAL_TIMELINE = [
  { id: 'EVT-DEP-772', type: 'deploy', service: 'payment-service', severity: 'INFO', time: '10:00:00 UTC', msg: 'Version v1.4.2 deployed by john.doe@tcs.com. Change: Optimized transaction handling.' },
  { id: 'EVT-LOG-001', type: 'log', service: 'payment-service', severity: 'INFO', time: '10:01:15 UTC', msg: 'Service starting up on port 8080. Active profiles: prod.' },
  { id: 'EVT-LOG-002', type: 'log', service: 'payment-service', severity: 'INFO', time: '10:03:30 UTC', msg: 'Connection established to database host db-primary-01.internal.' },
  { id: 'EVT-LOG-003', type: 'log', service: 'payment-service', severity: 'WARNING', time: '10:05:00 UTC', msg: 'Database connection pool utilization at 85% (170/200 active connections).' },
  { id: 'EVT-LOG-004', type: 'log', service: 'payment-service', severity: 'WARNING', time: '10:07:45 UTC', msg: 'Database connection pool utilization at 95% (190/200 active connections).' },
  { id: 'EVT-LOG-005', type: 'log', service: 'database', severity: 'WARNING', time: '10:08:12 UTC', msg: 'PostgreSQL: Client connection limit reached. 200 clients already connected. Rejecting new connections.' },
  { id: 'EVT-LOG-006', type: 'log', service: 'payment-service', severity: 'ERROR', time: '10:09:00 UTC', msg: 'Error: Connection acquisition timeout after 5000ms. Request path: /checkout/pay' },
  { id: 'EVT-ALT-109', type: 'alert', service: 'payment-service', severity: 'CRITICAL', time: '10:10:00 UTC', msg: 'Alert [DBPoolExhausted]: Database connection pool utilization has reached 100%.' },
  { id: 'EVT-CMP-4001', type: 'complaint', service: 'checkout-service', severity: 'HIGH', time: '10:11:00 UTC', msg: 'Customer complaint: Spinner spins forever and shows "Payment failed: Server Timeout" during checkout.' },
  { id: 'EVT-LOG-007', type: 'log', service: 'payment-service', severity: 'ERROR', time: '10:11:30 UTC', msg: 'SQLException: Cannot get connection from pool. Timeout waiting for idle object.' },
  { id: 'EVT-ALT-110', type: 'alert', service: 'payment-service', severity: 'CRITICAL', time: '10:12:00 UTC', msg: 'Alert [Http5xxRateHigh]: HTTP 5xx responses exceeded 15% of total traffic in the last 2 minutes.' },
  { id: 'EVT-CMP-4002', type: 'complaint', service: 'checkout-service', severity: 'HIGH', time: '10:13:15 UTC', msg: 'Customer complaint: Getting 500 error page when submitting the payment form.' },
  { id: 'EVT-LOG-008', type: 'log', service: 'web-gateway', severity: 'ERROR', time: '10:14:10 UTC', msg: 'Upstream timeout: 504 Gateway Timeout on POST /api/v1/payment/checkout' },
  { id: 'EVT-ALT-111', type: 'alert', service: 'web-gateway', severity: 'WARNING', time: '10:15:00 UTC', msg: 'Alert [ServiceLatencySpike]: Upstream response time from payment-service averages > 5000ms.' }
];

// Metrics raw history
const METRIC_HISTORY = {
  'payment-service': {
    cpu: [12.5, 18.2, 22.0, 35.4, 40.1, 45.8, 48.2, 50.1],
    latency: [120, 135, 150, 320, 1250, 5000, 8500, 9200],
    errorRate: [0.0, 0.0, 0.1, 0.5, 1.2, 5.4, 15.6, 18.2]
  },
  'checkout-service': {
    cpu: [10.2, 12.1, 15.3, 16.0, 18.5, 20.4, 21.0, 22.5],
    latency: [45, 48, 52, 60, 120, 350, 4200, 4800],
    errorRate: [0.0, 0.0, 0.0, 0.1, 0.2, 0.4, 3.8, 4.2]
  }
};

const INITIAL_HYPOTHESES = [
  {
    title: "Database connection pool leak in payment-service v1.4.2",
    description: "The deployment DEP-772 at 10:00:00 UTC introduced payment-service v1.4.2. A suspected connection leak exists where database connections are not properly released back to the pool, saturating the PostgreSQL maximum connection limit (200) by 10:08:00 UTC.",
    confidence: 0.92,
    evidence_for: [
      "payment-service v1.4.2 deployed at 10:00:00 UTC",
      "db_connections metric starts rising immediately after, peaking at 200 at 10:08:00 UTC",
      "Log messages warn of connection pool utilization at 85% and 95% shortly after deploy",
      "SQLExceptions show cannot acquire connection from pool"
    ],
    evidence_against: [
      "Other database services (e.g. auth-service) are not throwing connection pool warnings, suggesting PostgreSQL itself is healthy."
    ]
  },
  {
    title: "Sudden checkout traffic spike flooding payment service",
    description: "A high volume of concurrent checkout requests overwhelmed the payment-service, exhausting all available database connection pool slots.",
    confidence: 0.35,
    evidence_for: [
      "High HTTP 5xx rates and user complaints about slow payments started around 10:11:00 UTC",
      "Database CPU utilization reached high levels (50.1%) under load"
    ],
    evidence_against: [
      "Metrics do not show a corresponding spike in request throughput; rather, latency rose first, which is indicative of blocking behavior."
    ]
  }
];

const DIAGNOSTICS = [
  { step: 1, action: "kubectl logs -l app=payment-service --tail=200 | grep -iE 'conn|pool|leak|sql'", purpose: "Check logs specifically for stack traces showing where db connection acquisition is blocking.", priority: "HIGH" },
  { step: 2, action: "SELECT pid, age(query_start), query, state FROM pg_stat_activity WHERE state != 'idle';", purpose: "Identify any active queries running for an unusually long time that are locking database connections.", priority: "HIGH" },
  { step: 3, action: "git diff v1.4.1..v1.4.2 -- ingestion/ db/ connection/", purpose: "Review code changes in deployment DEP-772 to find unclosed database session contexts.", priority: "MEDIUM" }
];

const RECOVERY_PLANS = [
  { action: "Roll back payment-service deployment to v1.4.1", reason: "Since the connection leak was introduced in deployment DEP-772 (v1.4.2), reverting to the previous stable release will restore connection stability.", risk: "LOW", instructions: "kubectl set image deployment/payment-service payment-service=registry.tcs.internal/payment-service:v1.4.1" },
  { action: "Restart the payment-service application pods", reason: "This will close all active network sockets, temporarily clearing the leaked connections. However, the leak will recur if the underlying code is still running.", risk: "MEDIUM", instructions: "kubectl rollout restart deployment/payment-service" },
  { action: "Temporarily increase PostgreSQL max_connections", reason: "Allows more active connections, but is highly risky as it can crash the database instance due to RAM/CPU exhaustion.", risk: "HIGH", instructions: "psql -c 'ALTER SYSTEM SET max_connections = 300;' && psql -c 'SELECT pg_reload_conf();'" }
];

const INITIAL_PAST_INCIDENTS = [
  { id: "INC-001", component: "auth-service", status: "SUCCESSFUL", symptoms: "Auth validation latency spike, 504 Gateway Timeouts, Redis pool exhaustion warnings.", root_cause: "auth-service redis connection leak due to unreleased client sockets in cache middleware.", recovery_action: "Restart auth-service deployment to free connections.", operator_notes: "Always release redis connections in a finally block." },
  { id: "INC-002", component: "database", status: "SUCCESSFUL", symptoms: "High CPU utilization (98%), disk I/O saturated.", root_cause: "Missing database index on user_sessions.token field leading to full table scans.", recovery_action: "Run database migration to add btree index.", operator_notes: "Added index check to pre-deployment checklist." }
];

// SVG line graph component
function LineChart({ title, data, color }) {
  const max = Math.max(...data, 1);
  const min = Math.min(...data, 0);
  const range = max - min || 1;
  const height = 45;
  const width = 280;
  const points = data.map((val, idx) => {
    const x = (idx / (data.length - 1)) * width;
    const y = height - ((val - min) / range) * height;
    return `${x},${y}`;
  }).join(' ');

  return (
    <div style={{ marginBottom: '16px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', color: '#475569', marginBottom: '4px', fontWeight: '500' }}>
        <span>{title}</span>
        <span style={{ fontWeight: '600', color: color }}>Current: {data[data.length - 1]}</span>
      </div>
      <svg height={height} width="100%" viewBox={`0 0 ${width} ${height}`} style={{ overflow: 'visible' }}>
        <line x1="0" y1={height} x2={width} y2={height} stroke="#e2e8f0" strokeWidth="1" />
        <polyline fill="none" stroke={color} strokeWidth="1.5" points={points} />
      </svg>
    </div>
  );
}

export default function App() {
  const [selectedService, setSelectedService] = useState('payment-service');
  const [selectedPlaybookIndex, setSelectedPlaybookIndex] = useState(0);
  const [operator, setOperator] = useState('site-reliability-lead@tcs.com');
  const [comments, setComments] = useState('');
  const [gateLog, setGateLog] = useState(null);
  const [pastIncidents, setPastIncidents] = useState(INITIAL_PAST_INCIDENTS);
  const [showHistory, setShowHistory] = useState(false);

  const selectedPlaybook = RECOVERY_PLANS[selectedPlaybookIndex];
  const serviceMetrics = METRIC_HISTORY[selectedService] || METRIC_HISTORY['payment-service'];

  const handleAction = (status) => {
    const logEntry = {
      action: selectedPlaybook.action,
      status: status,
      operator: operator,
      timestamp: new Date().toLocaleTimeString(),
      comments: comments
    };
    setGateLog(logEntry);

    if (status === 'APPROVED') {
      const newIncident = {
        id: `INC-00${pastIncidents.length + 1}`,
        component: selectedService,
        status: "SUCCESSFUL",
        symptoms: "Checkout Failure, DB pool exhaustion",
        root_cause: INITIAL_HYPOTHESES[0].title,
        recovery_action: selectedPlaybook.action,
        operator_notes: `Approved by ${operator}. Comments: ${comments}`
      };
      setPastIncidents([newIncident, ...pastIncidents]);
    }
  };

  return (
    <div className="app-container">
      {/* Top Header */}
      <header className="app-header">
        <div className="app-title-group">
          <h2 className="app-title">RootLens Incident Control</h2>
          <span className="status-badge">Active Outage</span>
        </div>
        <div className="meta-info">
          Active ID: <strong>ACT-0921</strong> | Target: <strong>payment-service</strong>
        </div>
      </header>

      {/* Main Grid */}
      <main className="dashboard-grid">
        
        {/* Left Column: Actions, Reasoning, Gate */}
        <div className="dashboard-column">
          
          {/* Section 1: Human Approval Gate */}
          <section className="card">
            <h3 className="section-title">🛡️ Operational Gate</h3>
            
            <div className="form-group">
              <label className="form-label">Select Recovery Playbook</label>
              <select 
                className="form-select"
                value={selectedPlaybookIndex}
                onChange={(e) => setSelectedPlaybookIndex(Number(e.target.value))}
              >
                {RECOVERY_PLANS.map((p, idx) => (
                  <option key={idx} value={idx}>{p.action} (Risk: {p.risk})</option>
                ))}
              </select>
            </div>

            <div style={{ marginBottom: '16px', fontSize: '0.85rem' }}>
              <p style={{ color: '#475569', marginBottom: '6px' }}><strong>Reasoning:</strong> {selectedPlaybook.reason}</p>
              <p>
                <strong>Risk Profile:</strong>{' '}
                <span style={{ 
                  color: selectedPlaybook.risk === 'HIGH' ? '#ef4444' : selectedPlaybook.risk === 'MEDIUM' ? '#f59e0b' : '#10b981',
                  fontWeight: '600'
                }}>
                  {selectedPlaybook.risk}
                </span>
              </p>
            </div>

            <div className="form-group">
              <label className="form-label">Execution Instructions (Dry-run preview)</label>
              <div className="terminal-block">$ {selectedPlaybook.instructions}</div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 2fr', gap: '12px' }}>
              <div className="form-group">
                <label className="form-label">Operator credentials</label>
                <input 
                  type="text" 
                  className="form-input" 
                  value={operator}
                  onChange={(e) => setOperator(e.target.value)}
                />
              </div>
              <div className="form-group">
                <label className="form-label">Approval justification / comments</label>
                <input 
                  type="text" 
                  className="form-input" 
                  placeholder="Reason for decision..."
                  value={comments}
                  onChange={(e) => setComments(e.target.value)}
                />
              </div>
            </div>

            <div className="btn-group">
              <button className="btn btn-primary" onClick={() => handleAction('APPROVED')}>✅ APPROVE & EXECUTE</button>
              <button className="btn btn-danger" onClick={() => handleAction('REJECTED')}>❌ REJECT & ABORT</button>
              <button className="btn btn-secondary" onClick={() => handleAction('MORE_DIAGNOSTICS')}>🔍 REQUEST EVIDENCE</button>
            </div>

            {gateLog && (
              <div className="logs-block">
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', fontWeight: 600, marginBottom: '4px' }}>
                  <span>Execution Status Logs</span>
                  <span style={{ 
                    color: gateLog.status === 'APPROVED' ? '#10b981' : gateLog.status === 'REJECTED' ? '#ef4444' : '#f59e0b' 
                  }}>
                    {gateLog.status}
                  </span>
                </div>
                <p style={{ fontSize: '0.8rem', color: '#475569' }}>
                  {gateLog.status === 'APPROVED' ? `[SUCCESS] ${gateLog.action} successfully dispatched at ${gateLog.timestamp}. Memory database updated.` : 
                   gateLog.status === 'REJECTED' ? `[ABORTED] Action rejected by operator.` : 
                   `[HOLD] Operator requesting more diagnostic evidence.`}
                </p>
              </div>
            )}
          </section>

          {/* Section 2: AI Hypotheses */}
          <section className="card">
            <h3 className="section-title">🧠 AI Root-Cause Analysis</h3>
            {INITIAL_HYPOTHESES.map((hyp, idx) => (
              <div key={idx} className="hypothesis-card">
                <div className="hypothesis-header">
                  <span className="hypothesis-title">{hyp.title}</span>
                  <span className="confidence-badge">Confidence: {intPercent(hyp.confidence)}%</span>
                </div>
                <p className="hypothesis-desc">{hyp.description}</p>
                <div className="evidence-columns">
                  <div>
                    <div className="evidence-header">✔️ Evidence FOR</div>
                    <ul className="evidence-list">
                      {hyp.evidence_for.map((ev, i) => (
                        <li key={i} className="evidence-item evidence-pro">- {ev}</li>
                      ))}
                    </ul>
                  </div>
                  <div>
                    <div className="evidence-header">❌ Evidence AGAINST</div>
                    <ul className="evidence-list">
                      {hyp.evidence_against.map((ev, i) => (
                        <li key={i} className="evidence-item evidence-con">- {ev}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              </div>
            ))}
          </section>

          {/* Section 3: Diagnostics */}
          <section className="card">
            <h3 className="section-title">🔍 Verification Diagnostics</h3>
            {DIAGNOSTICS.map((d, idx) => (
              <div key={idx} style={{ marginBottom: '12px' }}>
                <div style={{ display: 'flex', justifySelf: 'space-between', fontSize: '0.85rem', fontWeight: 600 }}>
                  <span>Step {d.step}: {d.purpose}</span>
                  <span style={{ 
                    fontSize: '0.7rem', 
                    marginLeft: '8px',
                    color: d.priority === 'HIGH' ? '#b91c1c' : '#92400e',
                    backgroundColor: d.priority === 'HIGH' ? '#fef2f2' : '#fffbeb',
                    padding: '1px 6px',
                    borderRadius: '4px'
                  }}>{d.priority}</span>
                </div>
                <div className="terminal-block">$ {d.action}</div>
              </div>
            ))}
          </section>
        </div>

        {/* Right Column: Timeline & Metrics */}
        <div className="dashboard-column">
          
          {/* Section 1: Timeline */}
          <section className="card" style={{ maxHeight: '580px', overflowY: 'auto' }}>
            <h3 className="section-title">📊 Correlated Event Log</h3>
            {INITIAL_TIMELINE.map((evt, idx) => (
              <div key={idx} className={`timeline-item ${evt.severity.toLowerCase()} ${evt.type}`}>
                <div className="timeline-header">
                  <div>
                    <span className={`timeline-badge bg-${evt.type}`}>{evt.type}</span>
                    <span className="timeline-comp">{evt.service}</span>
                  </div>
                  <span className="timeline-time">{evt.time}</span>
                </div>
                <p className="timeline-msg">{evt.msg}</p>
              </div>
            ))}
          </section>

          {/* Section 2: Metrics */}
          <section className="card">
            <h3 className="section-title">📉 Telemetry Metrics</h3>
            
            <div className="form-group" style={{ marginBottom: '20px' }}>
              <label className="form-label">Service Focus Filter</label>
              <select 
                className="form-select"
                value={selectedService}
                onChange={(e) => setSelectedService(e.target.value)}
              >
                <option value="payment-service">payment-service (Active Outage)</option>
                <option value="checkout-service">checkout-service (Impacted)</option>
              </select>
            </div>

            <LineChart title="CPU Utilization %" data={serviceMetrics.cpu} color="#2563eb" />
            <LineChart title="p99 Response Latency (ms)" data={serviceMetrics.latency} color="#f59e0b" />
            <LineChart title="Error Rate %" data={serviceMetrics.errorRate} color="#d946ef" />
          </section>
        </div>
      </main>

      {/* RAG Memory section */}
      <footer className="memory-section">
        <div className="memory-toggle" onClick={() => setShowHistory(!showHistory)}>
          <span>📚 RAG Operational Memory Log Reference</span>
          <span>{showHistory ? '▼' : '▶'}</span>
        </div>
        
        {showHistory && (
          <div className="memory-grid">
            {pastIncidents.map((inc, idx) => (
              <div key={idx} className="memory-card">
                <div className="memory-card-header">
                  <span>Incident {inc.id} ({inc.component})</span>
                  <span style={{ color: '#166534', fontSize: '0.75rem', fontWeight: 600 }}>{inc.status}</span>
                </div>
                <div className="memory-body">
                  <p><strong>Symptoms:</strong> {inc.symptoms}</p>
                  <p><strong>Root Cause:</strong> {inc.root_cause}</p>
                  <p><strong>Resolution Action:</strong> {inc.recovery_action}</p>
                  <p style={{ color: '#64748b', fontStyle: 'italic', marginTop: '4px' }}><strong>Operator Notes:</strong> {inc.operator_notes}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </footer>
    </div>
  );
}

function intPercent(val) {
  return Math.round(val * 100);
}
