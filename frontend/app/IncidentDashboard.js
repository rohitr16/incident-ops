'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import IncidentCard from './IncidentCard';

const WS_URL = 'ws://localhost:8000/ws/incidents';
const API_URL = 'http://localhost:8000';

export default function IncidentDashboard() {
  const [incidents, setIncidents] = useState([]);
  const [activeIncidentId, setActiveIncidentId] = useState(null);
  const [connected, setConnected] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [debugLog, setDebugLog] = useState([]);
  const pollRef = useRef(null);

  const log = useCallback((msg) => {
    const time = new Date().toISOString().split('T')[1].slice(0, -1);
    setDebugLog((prev) => [...prev.slice(-30), `[${time}] ${msg}`]);
  }, []);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${API_URL}/incidents`);
      const data = await res.json();
      setIncidents(Array.isArray(data) ? data : []);
    } catch (e) {
      log(`/incidents ERROR: ${e?.message || e}`);
    }
  }, [log]);

  useEffect(() => {
    load();
    if (!connected) {
      log('WS disconnected; starting 2s HTTP polling loop fallback.');
      pollRef.current = setInterval(load, 2000);
    } else {
      log('WS connected; disabling HTTP polling loop.');
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [connected, load, log]);

  useEffect(() => {
    let ws;
    let reconnectTimeout;
    
    const connect = () => {
      try {
        ws = new WebSocket(WS_URL);
        ws.addEventListener('open', () => {
          setConnected(true);
          log('WS Connected');
        });
        ws.addEventListener('close', () => {
          setConnected(false);
          log('WS Disconnected, reconnecting in 3s...');
          reconnectTimeout = setTimeout(connect, 3000);
        });
        ws.addEventListener('error', () => {
          setConnected(false);
        });
        ws.addEventListener('message', (event) => {
          try {
            const parsed = JSON.parse(event.data || '{}');
            if (parsed && parsed.incident_id) {
              setIncidents((prev) => {
                const exists = prev.find((item) => item.incident_id === parsed.incident_id);
                if (exists) return prev.map((item) => (item.incident_id === parsed.incident_id ? { ...item, ...parsed } : item));
                return [...prev, parsed];
              });
            }
          } catch (e) {
            log('WS msg non-json');
          }
        });
      } catch (e) {
        log(`WS error: ${e?.message || e}`);
        reconnectTimeout = setTimeout(connect, 3000);
      }
    };
    
    connect();
    return () => {
      if (ws) ws.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [log]);

  const activeIncident = incidents.find(
    (inc) => (inc.incident_id ?? inc.id) === activeIncidentId
  );

  // Auto-select first incident on load
  useEffect(() => {
    if (incidents.length > 0 && activeIncidentId === null) {
      setActiveIncidentId(incidents[0].incident_id ?? incidents[0].id);
    }
  }, [incidents, activeIncidentId]);

  const toggleStep = async (step) => {
    if (!activeIncident || isUpdating) return;
    setIsUpdating(true);
    
    const currentSteps = activeIncident.resolution?.steps_executed || [];
    let updatedSteps;
    if (currentSteps.includes(step)) {
      updatedSteps = currentSteps.filter((s) => s !== step);
    } else {
      updatedSteps = [...currentSteps, step];
    }
    
    try {
      const res = await fetch(`${API_URL}/incidents/${activeIncidentId}/steps`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ steps_executed: updatedSteps }),
      });
      if (res.ok) {
        const data = await res.json();
        setIncidents((prev) =>
          prev.map((item) => ((item.incident_id ?? item.id) === activeIncidentId ? data : item))
        );
      }
    } catch (e) {
      log(`Update steps error: ${e?.message || e}`);
    } finally {
      setIsUpdating(false);
    }
  };

  const resolveIncident = async () => {
    if (!activeIncident || isUpdating) return;
    setIsUpdating(true);
    
    try {
      const res = await fetch(`${API_URL}/incidents/${activeIncidentId}/resolve`, {
        method: 'POST',
      });
      if (res.ok) {
        const data = await res.json();
        setIncidents((prev) =>
          prev.map((item) => ((item.incident_id ?? item.id) === activeIncidentId ? data : item))
        );
      }
    } catch (e) {
      log(`Resolve error: ${e?.message || e}`);
    } finally {
      setIsUpdating(false);
    }
  };

  return (
    <div className="feed-root">
      <div className="feed-header">
        <div className="feed-title">⚡ Ops-Center Dash</div>
        <div className="status">
          <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          <span>{connected ? 'WebSocket Live' : 'Disconnected (Polling)'}</span>
        </div>
      </div>

      <div className="main-layout">
        
        {/* Left Side: Incidents Feed */}
        <div className="feed-panel">
          {incidents.length === 0 && <div className="empty">No active incidents.</div>}
          {incidents.map((incident) => {
            const incId = incident.incident_id ?? incident.id;
            return (
              <IncidentCard
                key={incId}
                incident={incident}
                active={activeIncidentId === incId}
                onClick={() => setActiveIncidentId(incId)}
              />
            );
          })}
        </div>

        {/* Right Side: Inspector Panel */}
        <div className="inspector-panel">
          {activeIncident ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', borderBottom: '1px solid #d1d1d6', paddingBottom: '0.75rem' }}>
                <h2 style={{ margin: 0 }}>INC-{activeIncident.incident_id}: {activeIncident.structured_log?.message || 'Storage Overload'}</h2>
                <span style={{ fontSize: '0.8rem', color: '#86868b' }}>
                  {activeIncident.structured_log?.timestamp || activeIncident.timestamp || 'N/A'}
                </span>
              </div>

              <div className="meta-grid">
                <div className="meta-item">
                  <span className="meta-label">Severity</span>
                  <span className="meta-val" style={{ color: (activeIncident.structured_log?.severity === 'CRITICAL' || activeIncident.structured_log?.severity === 'FATAL') ? '#ff3b30' : '#ff9f0a' }}>
                    {activeIncident.structured_log?.severity}
                  </span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Priority</span>
                  <span className="meta-val">{activeIncident.triage?.priority}</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Category</span>
                  <span className="meta-val">{activeIncident.triage?.category}</span>
                </div>
                <div className="meta-item">
                  <span className="meta-label">Source Host</span>
                  <span className="meta-val"><code>{activeIncident.source}</code></span>
                </div>
              </div>

              {activeIncident.resolution?.playbook_used?.length > 0 ? (
                <div className="playbook-checklist-container">
                  <div style={{ fontWeight: 600, fontSize: '0.8rem', color: '#86868b', textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: '0.75rem' }}>
                    Playbook Steps
                  </div>
                  {activeIncident.resolution.playbook_used.map((step, idx) => {
                    const isChecked = activeIncident.resolution.steps_executed?.includes(step);
                    return (
                      <div 
                        key={idx} 
                        className={`playbook-step ${isChecked ? 'checked' : ''}`}
                        onClick={() => toggleStep(step)}
                      >
                        <input 
                          className="checklist-step-checkbox"
                          type="checkbox" 
                          checked={isChecked} 
                          onChange={() => {}} // handled by click
                        />
                        <span style={isChecked ? { textDecoration: 'line-through', color: '#86868b' } : {}}>
                          {step}
                        </span>
                      </div>
                    );
                  })}
                </div>
              ) : (
                <div style={{ color: '#86868b', fontStyle: 'italic', fontSize: '0.9rem' }}>
                  No registered playbook for this incident category/severity.
                </div>
              )}

              <div style={{ marginTop: 'auto', paddingTop: '1rem', borderTop: '1px solid #d1d1d6', display: 'flex', justifyContent: 'flex-end' }}>
                <button 
                  onClick={resolveIncident} 
                  disabled={activeIncident.resolution?.status === 'resolved' || isUpdating}
                  className="resolve-btn"
                >
                  {activeIncident.resolution?.status === 'resolved' ? '✓ Resolved' : 'Mark as Resolved'}
                </button>
              </div>
            </>
          ) : (
            <div className="empty">Select an incident from the feed to inspect.</div>
          )}
        </div>

      </div>

      <div className="debug">
        <div style={{ fontWeight: 'bold', marginBottom: '0.25rem' }}>SYSTEM EVENT LOG</div>
        {debugLog.map((line, i) => (
          <div key={i}>{line}</div>
        ))}
      </div>
    </div>
  );
}
