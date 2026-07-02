'use client';

import { useState, useEffect, useRef, useCallback } from 'react';
import IncidentCard from './IncidentCard';

const WS_URL = 'ws://localhost:8000/ws/incidents';
const INGEST_URL = 'http://localhost:8000/ingest';

export default function IncidentDashboard() {
  const [incidents, setIncidents] = useState([]);
  const [connected, setConnected] = useState(false);
  const [resolvingIds, setResolvingIds] = useState(new Set());
  const bottomRef = useRef(null);
  const pollRef = useRef(null);
  const [debugLog, setDebugLog] = useState([]);

  const log = useCallback((msg) => {
    const time = new Date().toISOString().split('T')[1].slice(0, -1);
    setDebugLog((prev) => [...prev.slice(-30), `[${time}] ${msg}`]);
  }, []);

  const scrollToBottom = useCallback(() => {
    if (bottomRef.current) {
      bottomRef.current.scrollIntoView({ behavior: 'smooth' });
    }
  }, []);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch('http://localhost:8000/incidents');
        const data = await res.json();
        log(`/incidents -> ${Array.isArray(data) ? data.length : 'err'}`);
        setIncidents(Array.isArray(data) ? data : []);
      } catch (e) {
        log(`/incidents ERROR: ${e?.message || e}`);
      }
    };
    load();
    pollRef.current = setInterval(load, 2000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [log, scrollToBottom]);

  useEffect(() => {
    let ws;
    try {
      ws = new WebSocket(WS_URL);
      log('WS opening...');
      ws.addEventListener('open', () => {
        log('WS open');
        setConnected(true);
      });
      ws.addEventListener('close', (e) => {
        log(`WS close code=${e.code} reason=${e.reason || ''}`);
        setConnected(false);
      });
      ws.addEventListener('error', (e) => {
        log(`WS error type=${e.type || 'unknown'}`);
        setConnected(false);
      });
      ws.addEventListener('message', (event) => {
        try {
          const parsed = JSON.parse(event.data || '{}');
          log(`WS msg id=${parsed.incident_id ?? '?'} severity=${parsed?.structured_log?.severity ?? ''}`);
        } catch {
          log('WS msg non-json');
        }
        let incident;
        try {
          incident = JSON.parse(event.data || '{}');
        } catch {
          return;
        }
        if (incident && incident.incident_id) {
          setIncidents((prev) => {
            const exists = prev.find((item) => item.incident_id === incident.incident_id);
            if (exists) return prev.map((item) => (item.incident_id === incident.incident_id ? { ...item, ...incident } : item));
            return [...prev, incident];
          });
        }
      });
    } catch (e) {
      log(`WS ctor ERROR: ${e?.message || e}`);
      setConnected(false);
    }
    return () => {
      try { if (ws) ws.close(); } catch {}
    };
  }, [log]);

  useEffect(() => {
    scrollToBottom();
  }, [incidents, scrollToBottom]);

  const resolveIncident = async (incident) => {
    const incidentId = incident.incident_id ?? incident.id;
    if (!incidentId || resolvingIds.has(incidentId)) return;

    setResolvingIds((prev) => new Set(prev).add(incidentId));

    try {
      await fetch(INGEST_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source: 'resolved', incident_id: incidentId }),
      });
    } catch {}

    setTimeout(() => {
      setIncidents((prev) => prev.filter((item) => (item.incident_id ?? item.id) !== incidentId));
      setResolvingIds((prev) => {
        const next = new Set(prev);
        next.delete(incidentId);
        return next;
      });
    }, 2000);
  };

  return (
    <div className="feed-root">
      <div className="feed-header">
        <div className="feed-title">Incident Feed</div>
        <div className="status">
          <span className={`status-dot ${connected ? 'connected' : 'disconnected'}`} />
          <span>{connected ? 'Connected' : 'Disconnected'}</span>
        </div>
      </div>

      {incidents.length === 0 && <div className="empty">No active incidents.</div>}

      {incidents.map((incident) => {
        const incidentId = incident.incident_id ?? incident.id;
        return (
          <div key={incidentId}>
            <IncidentCard
              incident={incident}
              onResolve={(item) => resolveIncident(item)}
              resolving={resolvingIds.has(incidentId)}
            />
          </div>
        );
      })}

      <div className="debug">
        <div className="debug-title">DEBUG</div>
        {debugLog.map((line, i) => (
          <div key={i} className="debug-line">{line}</div>
        ))}
      </div>

      <div ref={bottomRef} />
    </div>
  );
}
