function normalizeIncident(incident) {
  if (!incident || typeof incident !== 'object') return {};
  const structured = incident.structured_log || incident.structuredLog || {};
  const detection = incident.detection || {};
  const triage = incident.triage || {};
  const resolution = incident.resolution || {};
  return {
    id: incident.incident_id ?? incident.id ?? '#',
    severity: structured.severity ?? incident.severity ?? 'info',
    timestamp: incident.timestamp || detection.timestamp || triage.timestamp || '',
    priority: triage.priority || incident.priority || 'minor',
    category: detection.category || incident.category || '',
    message:
      structured.message ||
      incident.message ||
      detection.summary ||
      incident.resolution ||
      '',
    recommended_action: triage.recommended_action || incident.recommended_action || 'Investigate',
  };
}

export default function IncidentCard({ incident, onResolve, resolving }) {
  const data = normalizeIncident(incident);
  const severityClass = data.severity ? `severity-${data.severity.toLowerCase()}` : '';

  return (
    <div className={`card ${resolving ? 'resolving' : ''}`} data-severity={data.severity || 'low'}>
      <div className="card-header">
        <div className="card-title">{data.id}</div>
        <div className={`badge ${severityClass}`}>{data.severity || 'info'}</div>
      </div>
      <div className="card-meta">
        <span>{data.timestamp}</span>
        <span className={`priority-${data.priority.toLowerCase()}`}>{data.priority}</span>
        <span>{data.category}</span>
      </div>
      <div className="card-body">{Array.isArray(data.message) ? data.message.join(' ') : data.message}</div>
      <div className="card-action">Action: {data.recommended_action}</div>
      {onResolve && (
        <button
          className="resolve-btn"
          onClick={() => onResolve(incident)}
          disabled={resolving}
        >
          {resolving ? 'Resolving' : 'Resolve'}
        </button>
      )}
    </div>
  );
}
