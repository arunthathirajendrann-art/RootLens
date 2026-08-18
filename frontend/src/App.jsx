import React, { useState } from 'react';
import axios from 'axios';

// SVG line graph component
function LineChart({ title, data, color }) {
  if (!data || data.length === 0) return <div>No data for {title}</div>;
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
  const [activePage, setActivePage] = useState('dashboard');
  const [files, setFiles] = useState({});
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  
  // State for data from API
  const [timeline, setTimeline] = useState([]);
  const [analysis, setAnalysis] = useState(null);
  const [repoPath, setRepoPath] = useState('');
  const [applyFixStatus, setApplyFixStatus] = useState(null);

  const handleFileChange = (e, key) => {
    setFiles({ ...files, [key]: e.target.files[0] });
  };

  const handleAnalyze = async () => {
    setIsAnalyzing(true);
    const formData = new FormData();
    if (files.alerts) formData.append('alerts', files.alerts);
    if (files.logs) formData.append('logs', files.logs);
    if (files.metrics) formData.append('metrics', files.metrics);
    if (files.deploys) formData.append('deploys', files.deploys);
    if (files.complaints) formData.append('complaints', files.complaints);
    if (files.source_zip) formData.append('source_zip', files.source_zip);

    try {
      const res = await axios.post('http://localhost:8000/api/analyze', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setTimeline(res.data.timeline);
      setAnalysis(res.data.analysis);
      setRepoPath(res.data.repo_path);
      setApplyFixStatus(null);
    } catch (err) {
      alert("Error analyzing incident: " + (err.response?.data?.detail || err.message));
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleApplyFix = async () => {
    const fix = analysis?.recommended_fix;
    if (!fix || !repoPath) return;
    
    try {
      const formData = new FormData();
      formData.append('repo_path', repoPath);
      formData.append('file_path', fix.file);
      formData.append('diff_before', fix.diff_before);
      formData.append('diff_after', fix.diff_after);
      
      const res = await axios.post('http://localhost:8000/api/apply-fix', formData);
      setApplyFixStatus('success');
    } catch (err) {
      setApplyFixStatus('error: ' + (err.response?.data?.detail || err.message));
    }
  };

  // Derive metrics from timeline (extract METRICS source events)
  const metricEvents = timeline.filter(t => String(t.source).toLowerCase() === 'metrics');
  const cpuData = metricEvents.map(m => m.metadata.cpu_utilization_pct || 0);
  const latencyData = metricEvents.map(m => m.metadata.p99_latency_ms || 0);
  const errorRateData = metricEvents.map(m => m.metadata.error_rate_pct || 0);

  return (
    <div className="app-layout">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <div className="sidebar-title">
          <span>🛡️ RootLens Copilot</span>
        </div>
        <ul className="sidebar-menu">
          <li 
            className={`sidebar-item ${activePage === 'dashboard' ? 'active' : ''}`}
            onClick={() => setActivePage('dashboard')}
          >
            📊 Dashboard
          </li>
          <li 
            className={`sidebar-item ${activePage === 'rca' ? 'active' : ''}`}
            onClick={() => setActivePage('rca')}
          >
            🧠 Root Cause Analysis
          </li>
        </ul>
      </aside>

      {/* Main Content Area */}
      <main className="main-content">
        <header className="app-header">
          <h2 className="app-title">
            {activePage === 'dashboard' ? 'Incident Dashboard' : 'Root Cause & Remediation'}
          </h2>
        </header>

        {activePage === 'dashboard' && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* File Upload Section */}
            <section className="card">
              <h3 className="section-title">Upload Signals & Source Code</h3>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600 }}>Alerts JSON</label>
                  <input type="file" onChange={(e) => handleFileChange(e, 'alerts')} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600 }}>Logs JSON</label>
                  <input type="file" onChange={(e) => handleFileChange(e, 'logs')} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600 }}>Metrics CSV</label>
                  <input type="file" onChange={(e) => handleFileChange(e, 'metrics')} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600 }}>Deploys JSON</label>
                  <input type="file" onChange={(e) => handleFileChange(e, 'deploys')} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600 }}>Complaints JSON</label>
                  <input type="file" onChange={(e) => handleFileChange(e, 'complaints')} />
                </div>
                <div>
                  <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600 }}>Source Code (ZIP)</label>
                  <input type="file" accept=".zip" onChange={(e) => handleFileChange(e, 'source_zip')} />
                </div>
              </div>
              <button 
                className="btn btn-primary" 
                onClick={handleAnalyze} 
                disabled={isAnalyzing}
                style={{ width: '200px' }}
              >
                {isAnalyzing ? 'Analyzing...' : 'Analyze Incident'}
              </button>
            </section>

            {/* Visuals: Timeline and Metrics */}
            {timeline.length > 0 && (
              <div className="dashboard-grid">
                <div className="dashboard-column">
                  <section className="card" style={{ maxHeight: '600px', overflowY: 'auto' }}>
                    <h3 className="section-title">📊 Signals Timeline</h3>
                    {timeline.map((evt, idx) => (
                      <div key={idx} className={`timeline-item ${evt.severity.toLowerCase()} ${evt.source}`}>
                        <div className="timeline-header">
                          <div>
                            <span className={`timeline-badge bg-${evt.source.toLowerCase()}`}>{evt.source}</span>
                            <span className="timeline-comp">{evt.component}</span>
                          </div>
                          <span className="timeline-time">{new Date(evt.timestamp).toLocaleTimeString()}</span>
                        </div>
                        <p className="timeline-msg">{evt.description}</p>
                      </div>
                    ))}
                  </section>
                </div>
                
                <div className="dashboard-column">
                  <section className="card">
                    <h3 className="section-title">📉 Telemetry Trends</h3>
                    {cpuData.length > 0 ? (
                      <>
                        <LineChart title="CPU Utilization %" data={cpuData} color="#2563eb" />
                        <LineChart title="p99 Latency (ms)" data={latencyData} color="#f59e0b" />
                        <LineChart title="Error Rate %" data={errorRateData} color="#d946ef" />
                      </>
                    ) : (
                      <p style={{ fontSize: '0.85rem', color: '#64748b' }}>No numeric metrics parsed in timeline.</p>
                    )}
                  </section>
                </div>
              </div>
            )}
          </div>
        )}

        {activePage === 'rca' && (
          <div>
            {!analysis ? (
              <div className="card">
                <p>No analysis available. Please upload files and run analysis on the Dashboard first.</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <section className="card">
                  <h3 className="section-title">🧠 AI Root-Cause Hypotheses</h3>
                  {analysis.hypotheses?.map((hyp, idx) => (
                    <div key={idx} style={{ marginBottom: '20px', borderBottom: '1px solid #e2e8f0', paddingBottom: '16px' }}>
                      <h4 style={{ color: '#0f172a', margin: '0 0 8px 0' }}>Rank {hyp.rank}: {hyp.root_cause}</h4>
                      <p style={{ fontSize: '0.9rem', color: '#475569', marginBottom: '8px' }}><strong>Summary:</strong> {hyp.reasoning_summary}</p>
                      <div style={{ fontSize: '0.85rem' }}>
                        <span style={{ fontWeight: 600, color: '#166534' }}>Confidence: {Math.round(hyp.confidence * 100)}%</span>
                      </div>
                      
                      {hyp.implicated_file && (
                        <div style={{ marginTop: '12px', background: '#f8fafc', padding: '12px', borderRadius: '6px' }}>
                          <div style={{ fontSize: '0.85rem', fontWeight: 600, marginBottom: '6px' }}>
                            Implicated Code: {hyp.implicated_file} (Line {hyp.implicated_line})
                          </div>
                          <pre style={{ margin: 0, fontSize: '0.8rem', color: '#b91c1c' }}>
                            <code>{hyp.source_snippet}</code>
                          </pre>
                        </div>
                      )}
                    </div>
                  ))}
                </section>

                <section className="card">
                  <h3 className="section-title">🛠️ Recommended Fix</h3>
                  {analysis.recommended_fix ? (
                    <div>
                      <p style={{ fontSize: '0.9rem', marginBottom: '12px' }}>
                        <strong>Target:</strong> {analysis.recommended_fix.file} <br/>
                        <strong>Explanation:</strong> {analysis.recommended_fix.explanation} <br/>
                        <strong style={{ color: '#d97706' }}>Risk: {analysis.recommended_fix.risk}</strong>
                      </p>
                      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px', marginBottom: '16px' }}>
                        <div style={{ background: '#fef2f2', border: '1px solid #fee2e2', padding: '12px', borderRadius: '6px' }}>
                          <strong style={{ fontSize: '0.85rem', color: '#991b1b' }}>🔴 Before</strong>
                          <pre style={{ fontSize: '0.8rem', marginTop: '8px' }}><code>{analysis.recommended_fix.diff_before}</code></pre>
                        </div>
                        <div style={{ background: '#f0fdf4', border: '1px solid #dcfce7', padding: '12px', borderRadius: '6px' }}>
                          <strong style={{ fontSize: '0.85rem', color: '#166534' }}>🟢 After</strong>
                          <pre style={{ fontSize: '0.8rem', marginTop: '8px' }}><code>{analysis.recommended_fix.diff_after}</code></pre>
                        </div>
                      </div>
                      
                      <button className="btn btn-primary" onClick={handleApplyFix}>
                        Approve & Apply Fix
                      </button>
                      
                      {applyFixStatus === 'success' && (
                        <div style={{ marginTop: '12px', color: '#166534', fontWeight: 600 }}>
                          ✅ Fix successfully applied to source code repository! (Auto-committed)
                        </div>
                      )}
                      {applyFixStatus && applyFixStatus.startsWith('error') && (
                        <div style={{ marginTop: '12px', color: '#b91c1c', fontWeight: 600 }}>
                          ❌ Failed to apply fix: {applyFixStatus}
                        </div>
                      )}
                    </div>
                  ) : (
                    <p style={{ fontSize: '0.9rem', color: '#64748b' }}>No automated code fix proposed.</p>
                  )}
                </section>
              </div>
            )}
          </div>
        )}
      </main>
    </div>
  );
}
