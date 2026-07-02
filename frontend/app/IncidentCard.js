import { useMemo } from 'react';

function normalizeIncident(incident) {
  if (!incident || typeof incident !== 'object') return {};
  const structured = incident.structured_log || incident.structuredLog || {};
  const detection = incident.detection || {};
  const triage = incident.triage || {};
  const resolution = incident.resolution || {};
  return {
    id: incident.incident_id ?? incident.id ?? '#',
    severity: structured.severity ?? incident.severity ?? 'info',
    timestamp: incident.timestamp || structured.timestamp || detection.timestamp || triage.timestamp || '',
    priority: triage.priority || incident.priority || 'minor',
    category: triage.category || detection.category || incident.category || '',
    message: structured.message || incident.message || detection.summary || '',
    playbook_steps: resolution.playbook_used || [],
    steps_executed: resolution.steps_executed || [],
    status: resolution.status || 'pending',
  };
}

export default function IncidentCard({ incident, active, onClick }) {
  const data = normalizeIncident(incident);
  const severityClass = data.severity ? `severity-${data.severity.toLowerCase()}` : '';

  const pct = useMemo(() => {
    if (!data.playbook_steps.length) return 0;
    return Math.round((data.steps_executed.length / data.playbook_steps.length) * 100);
  }, [data.playbook_steps, data.steps_executed]);

  const barColor = useMemo(() => {
    if (data.status === 'resolved') return '#34c759';
    if (data.severity === 'CRITICAL' || data.severity === 'FATAL') return '#ff3b30';
    return '#ff9f0a';
  }, [data.status, data.severity]);

  return (
    <div 
      className={`card ${active ? 'active' : ''}`} 
      onClick={onClick}
    >
      <div className="card-header">
        <div className="card-title">INC-{data.id}</div>
        <div className={`badge ${severityClass}`}>{data.severity}</div>
      </div>
      <div className="card-meta">
        <span>{data.timestamp.split(' ')[1] || data.timestamp}</span>
        <span>{data.priority}</span>
        <span>{data.category}</span>
      </div>
      <div className="card-body" style={{ fontSize: '0.85rem', color: '#1d1d1f' }}>
        {data.message}
      </div>
      
      {data.playbook_steps.length > 0 && (
        <div className="progress-container">
          <div className="progress-header">
            <span>Playbook Checklist</span>
            <span>{pct}%</span>
          </div>
          <div className="progress-bar-bg">
            <div 
              className="progress-bar-fill" 
              style={{ width: `${pct}%`, backgroundColor: barColor }}
            />
          </div>
        </div>
      )}
    </div>
  );
}
