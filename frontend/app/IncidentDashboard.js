'use client';

import { useState, useEffect, useRef, useCallback, useMemo } from 'react';

const WS_URL = 'ws://localhost:8000/ws/incidents';
const API_URL = 'http://localhost:8000';

export default function IncidentDashboard() {
  const [incidents, setIncidents] = useState([]);
  const [activeIncidentId, setActiveIncidentId] = useState(null);
  const [activeTab, setActiveTab] = useState('list');
  const [connected, setConnected] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [debugLog, setDebugLog] = useState([]);
  const pollRef = useRef(null);
  const logWrapperRef = useRef(null);

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
    let isCleanedUp = false;
    
    const connect = () => {
      if (isCleanedUp) return;
      try {
        ws = new WebSocket(WS_URL);
        ws.addEventListener('open', () => {
          setConnected(true);
          log('WS Connected');
        });
        ws.addEventListener('close', () => {
          setConnected(false);
          if (!isCleanedUp) {
            log('WS Disconnected, reconnecting in 3s...');
            reconnectTimeout = setTimeout(connect, 3000);
          }
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
                if (exists) {
                  return prev.map((item) => (item.incident_id === parsed.incident_id ? { ...item, ...parsed } : item));
                }
                return [...prev, parsed];
              });
            }
          } catch (e) {
            log('WS msg non-json');
          }
        });
      } catch (e) {
        log(`WS error: ${e?.message || e}`);
        if (!isCleanedUp) {
          reconnectTimeout = setTimeout(connect, 3000);
        }
      }
    };
    
    connect();
    return () => {
      isCleanedUp = true;
      if (ws) ws.close();
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
    };
  }, [log]);

  const activeIncident = useMemo(() => {
    return incidents.find((inc) => inc.incident_id === activeIncidentId);
  }, [incidents, activeIncidentId]);

  // Auto-scroll logs wrapper on update
  useEffect(() => {
    if (logWrapperRef.current) {
      logWrapperRef.current.scrollTop = logWrapperRef.current.scrollHeight;
    }
  }, [activeIncident?.agent_history]);

  const selectIncident = (id) => {
    setActiveIncidentId(id);
    setActiveTab('details');
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
          prev.map((item) => (item.incident_id === activeIncidentId ? data : item))
        );
      }
    } catch (e) {
      log(`Resolve error: ${e?.message || e}`);
    } finally {
      setIsUpdating(false);
    }
  };

  // Helper mapping: Node classes based on history & status
  const getNodeClass = (nodeId) => {
    if (!activeIncident) return '';
    const status = activeIncident.resolution?.status || 'pending';
    const history = activeIncident.agent_history || [];
    
    if (status === 'resolved') return 'node-success';
    if (history.length === 0) {
      if (nodeId === 'node-insight') return 'node-active';
      return '';
    }

    const hasSmartQueue = history.some(e => e.node === 'SmartQueue');
    const hasKnowledgeAgent = history.some(e => e.node === 'KnowledgeAgent');
    const hasAutoInfra = history.some(e => e.node === 'AutoInfra');
    const hasComplianceAgent = history.some(e => e.node === 'ComplianceAgent');

    const smartQueueRunning = history.some(e => e.node === 'SmartQueue' && e.status === 'running') && !history.some(e => e.node === 'SmartQueue' && e.status === 'completed');
    const knowledgeRunning = history.some(e => e.node === 'KnowledgeAgent' && e.status === 'running') && !history.some(e => e.node === 'KnowledgeAgent' && e.status === 'completed');
    const autoInfraRunning = history.some(e => e.node === 'AutoInfra' && e.status === 'running') && !history.some(e => e.node === 'AutoInfra' && e.status === 'completed');
    const complianceRunning = history.some(e => e.node === 'ComplianceAgent' && e.status === 'running') && !history.some(e => e.node === 'ComplianceAgent' && e.status === 'completed');

    if (nodeId === 'node-insight') return 'node-success';

    if (nodeId === 'node-smart') {
      if (smartQueueRunning) return 'node-active';
      if (hasSmartQueue) return 'node-success';
    }

    if (nodeId === 'node-resolve' || nodeId === 'node-mcp') {
      if (knowledgeRunning) return 'node-active';
      if (hasKnowledgeAgent) return 'node-success';
    }

    if (nodeId === 'node-supervisor') {
      if (autoInfraRunning || complianceRunning) return 'supervisor-active';
      if (hasComplianceAgent) return 'node-success';
    }

    if (nodeId === 'node-sub-policy' || nodeId === 'node-sub-infra') {
      if (autoInfraRunning) return 'node-active';
      if (hasAutoInfra) return 'node-success';
    }

    if (nodeId === 'node-sub-verify') {
      if (complianceRunning) return 'node-active';
      if (hasComplianceAgent) return 'node-success';
    }

    if (nodeId === 'node-security') {
      if (status === 'resolved') return 'node-success';
      if (history.length > 2) return 'node-success';
    }

    return '';
  };

  // Helper mapping: Connection glow classes
  const getArrowClass = (arrowId) => {
    if (!activeIncident) return '';
    const status = activeIncident.resolution?.status || 'pending';
    const history = activeIncident.agent_history || [];

    if (status === 'resolved') return 'connection-active';
    if (history.length === 0) return '';

    const hasSmartQueue = history.some(e => e.node === 'SmartQueue' && e.status === 'completed');
    const hasKnowledgeAgent = history.some(e => e.node === 'KnowledgeAgent' && e.status === 'completed');
    const hasAutoInfra = history.some(e => e.node === 'AutoInfra' && e.status === 'completed');
    const hasComplianceAgent = history.some(e => e.node === 'ComplianceAgent' && e.status === 'completed');

    if (arrowId === 'arr-1' && (hasSmartQueue || history.some(e => e.node === 'SmartQueue'))) return 'connection-active';
    if (arrowId === 'arr-2' && (hasKnowledgeAgent || history.some(e => e.node === 'KnowledgeAgent'))) return 'connection-active';
    if (arrowId === 'arr-mcp' && history.some(e => e.node === 'KnowledgeAgent')) return 'connection-active';
    if (arrowId === 'arr-sub' && (hasAutoInfra || history.some(e => e.node === 'AutoInfra'))) return 'connection-active';
    if (arrowId === 'arr-3' && history.some(e => e.node === 'AutoInfra')) return 'connection-active';
    if (arrowId === 'arr-4' && hasComplianceAgent) return 'connection-active';

    return '';
  };

  // Helper mapping: Stepper progress
  const stepperProgress = useMemo(() => {
    if (!activeIncident) return { height: '0%', steps: ['pending', 'pending', 'pending', 'pending'] };
    const status = activeIncident.resolution?.status || 'pending';
    const history = activeIncident.agent_history || [];

    if (status === 'resolved') {
      return { height: '100%', steps: ['completed', 'completed', 'completed', 'completed'] };
    }

    const hasSmartQueue = history.some(e => e.node === 'SmartQueue');
    const hasKnowledgeAgent = history.some(e => e.node === 'KnowledgeAgent');
    const hasAutoInfra = history.some(e => e.node === 'AutoInfra');
    const hasComplianceAgent = history.some(e => e.node === 'ComplianceAgent');

    const smartQueueCompleted = history.some(e => e.node === 'SmartQueue' && e.status === 'completed');
    const knowledgeCompleted = history.some(e => e.node === 'KnowledgeAgent' && e.status === 'completed');
    const autoInfraCompleted = history.some(e => e.node === 'AutoInfra' && e.status === 'completed');
    const complianceCompleted = history.some(e => e.node === 'ComplianceAgent' && e.status === 'completed');

    let height = '0%';
    let steps = ['pending', 'pending', 'pending', 'pending'];

    if (hasSmartQueue || hasKnowledgeAgent) {
      steps[0] = knowledgeCompleted ? 'completed' : 'active';
      height = '15%';
    }
    if (hasAutoInfra) {
      steps[0] = 'completed';
      steps[1] = autoInfraCompleted ? 'completed' : 'active';
      height = '48%';
    }
    if (hasComplianceAgent) {
      steps[0] = 'completed';
      steps[1] = 'completed';
      steps[2] = complianceCompleted ? 'completed' : 'active';
      height = '75%';
    }
    if (status === 'resolved') {
      steps = ['completed', 'completed', 'completed', 'completed'];
      height = '100%';
    }

    return { height, steps };
  }, [activeIncident]);

  const renderStepIcon = (state) => {
    if (state === 'completed') {
      return (
        <div className="step-icon relative z-10 w-6 h-6 rounded-full bg-emerald-500 border-2 border-emerald-500 flex items-center justify-center mt-0.5 shadow-[0_0_12px_rgba(16,185,129,0.4)] text-white">
          <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="3.5">
            <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
          </svg>
        </div>
      );
    }
    if (state === 'active') {
      return (
        <div className="step-icon relative z-10 w-6 h-6 rounded-full bg-blue-900/50 border-2 border-blue-500 flex items-center justify-center mt-0.5 shadow-[0_0_12px_rgba(59,130,246,0.5)]">
          <svg className="animate-spin h-3 w-3 text-blue-400" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
        </div>
      );
    }
    return (
      <div className="step-icon relative z-10 w-6 h-6 rounded-full bg-slate-800 border-2 border-slate-600 flex items-center justify-center mt-0.5 transition-all duration-300">
        <div className="w-1.5 h-1.5 rounded-full bg-slate-500"></div>
      </div>
    );
  };

  const renderLogLine = (logEvent, idx) => {
    const logText = logEvent.message;
    const timestamp = logEvent.timestamp;
    const timeStr = timestamp ? `[${timestamp.split('T')[1]?.slice(0, 8) || timestamp}]` : '';

    const regex = /\[(.*?)\]:\s(.*)/;
    const match = logText.match(regex);

    if (match) {
      const agent = match[1];
      const msg = match[2];

      let agentColor = 'text-blue-400';
      if (agent === 'Supervisor') agentColor = 'text-indigo-400';
      else if (agent === 'InsightWatch') agentColor = 'text-rose-400';
      else if (agent === 'SmartQueue') agentColor = 'text-sky-400';
      else if (agent === 'ResolveAI') agentColor = 'text-fuchsia-400';
      else if (agent.includes('HealthCheck') || agent.includes('System') || agent.includes('Verification') || agent === 'ComplianceAgent') agentColor = 'text-emerald-400';
      else if (agent.includes('KnowledgeBase') || agent === 'MCP' || agent === 'KnowledgeAgent') agentColor = 'text-amber-400';

      let msgContent = msg;
      let detail = '';
      if (msg.includes('|')) {
        const parts = msg.split('|');
        msgContent = parts[0];
        detail = parts[1];
      }

      return (
        <div key={idx} className="font-mono text-[0.7rem] leading-relaxed tracking-wide">
          <span className="text-slate-500 mr-2">{timeStr}</span>
          <span className={`${agentColor} font-bold`}>[{agent}]:</span>{' '}
          <span className="text-slate-300">{msgContent}</span>
          {detail && (
            <>
              <span className="text-slate-500 mx-1">|</span>
              <span className="text-slate-400">{detail}</span>
            </>
          )}
        </div>
      );
    }

    let colorClass = logText.includes('System') ? 'text-emerald-400 font-bold' : 'text-slate-300';
    return (
      <div key={idx} className="font-mono text-[0.7rem] leading-relaxed tracking-wide">
        <span className="text-slate-500 mr-2">{timeStr}</span>
        <span className={colorClass}>{logText}</span>
      </div>
    );
  };

  const getPriorityBadgeClass = (prio) => {
    if (prio === 'P0' || prio === 'P1') return 'text-red-400 font-bold';
    if (prio === 'P2') return 'text-orange-400 font-semibold';
    return 'text-slate-300';
  };

  const activeCount = incidents.filter(i => i.resolution?.status !== 'resolved').length;
  const resolvedCount = incidents.filter(i => i.resolution?.status === 'resolved').length;

  return (
    <div className="h-screen w-screen overflow-hidden flex flex-col p-3 gap-3 bg-[#020617] text-slate-100">
      
      {/* Top Header */}
      <header className="glass-panel rounded-xl px-5 py-3 flex justify-between items-center shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center shadow-lg shadow-indigo-500/20">
            <svg className="w-5 h-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
              <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <h1 className="text-xl font-bold tracking-tight text-white">
            MTTRAgent <span className="text-slate-500 font-normal ml-2 mr-2">|</span> <span className="text-slate-300 font-medium">Incident Resolution Platform</span>
          </h1>
        </div>
        <div className="flex items-center gap-5">
          <div className="flex items-center gap-2 text-sm font-medium px-3 py-1 rounded-full bg-slate-800 border border-slate-700">
            <span className={`w-2 h-2 rounded-full bg-emerald-500 ${connected ? 'animate-pulse' : ''}`} />
            <span className="text-slate-300">{connected ? 'System Active' : 'Offline'}</span>
          </div>
          <div className="w-9 h-9 rounded-full bg-slate-700 border-2 border-slate-600 flex items-center justify-center overflow-hidden">
            <span className="text-xs font-bold text-slate-300">AD</span>
          </div>
        </div>
      </header>

      {/* Navigation tabs */}
      <div className="flex gap-4 px-2 shrink-0 border-b border-slate-800">
        <button
          onClick={() => setActiveTab('list')}
          className={`${activeTab === 'list' ? 'tab-active' : 'tab-inactive'} px-4 py-2 text-sm font-medium border-b-2 transition-colors`}
        >
          Incidents
        </button>
        <button
          onClick={() => activeIncidentId && setActiveTab('details')}
          disabled={!activeIncidentId}
          className={`${activeTab === 'details' ? 'tab-active' : 'tab-inactive'} px-4 py-2 text-sm font-medium border-b-2 transition-colors disabled:opacity-50 disabled:cursor-not-allowed`}
        >
          Incident Details
        </button>
      </div>

      {/* Tabs Container */}
      <div className="flex-1 overflow-hidden min-h-0 relative">

        {/* TAB 1: INCIDENTS LIST */}
        {activeTab === 'list' && (
          <div className="absolute inset-0 flex flex-col">
            <main className="flex-1 glass-panel rounded-xl p-0 overflow-hidden flex flex-col">
              <div className="p-4 border-b border-slate-700/50 flex justify-between items-center bg-slate-900/30">
                <h2 className="text-lg font-semibold text-slate-200">Active Incidents</h2>
                <div className="flex gap-2">
                  <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-slate-800 text-slate-300 border border-slate-700">
                    {activeCount} Open
                  </span>
                  <span className="text-xs font-medium px-2.5 py-1 rounded-full bg-emerald-900/30 text-emerald-400 border border-emerald-800/50">
                    {resolvedCount} Resolved
                  </span>
                </div>
              </div>
              <div className="flex-1 overflow-y-auto">
                <table className="w-full text-left text-sm text-slate-400">
                  <thead className="text-xs uppercase bg-slate-800/50 text-slate-500 sticky top-0 z-10">
                    <tr>
                      <th scope="col" class="px-6 py-3 font-medium tracking-wider">Incident ID</th>
                      <th scope="col" class="px-6 py-3 font-medium tracking-wider">Message</th>
                      <th scope="col" class="px-6 py-3 font-medium tracking-wider">Priority</th>
                      <th scope="col" class="px-6 py-3 font-medium tracking-wider">Status</th>
                      <th scope="col" class="px-6 py-3 font-medium tracking-wider">Category</th>
                      <th scope="col" class="px-6 py-3 font-medium tracking-wider text-right">Action</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-700/50">
                    {incidents.map((inc) => {
                      const status = inc.resolution?.status || 'pending';
                      const isResolved = status === 'resolved';
                      const rowPriority = inc.triage?.priority || 'P4';
                      
                      return (
                        <tr
                          key={inc.incident_id}
                          onClick={() => selectIncident(inc.incident_id)}
                          className="hover:bg-slate-800/50 transition-colors cursor-pointer border-b border-slate-800/50 last:border-0"
                        >
                          <td className="px-6 py-4 font-mono font-medium text-slate-200">INC-{inc.incident_id}</td>
                          <td className="px-6 py-4 text-slate-300 font-medium max-w-sm truncate">{inc.structured_log?.message || inc.raw_line}</td>
                          <td className={`px-6 py-4 ${getPriorityBadgeClass(rowPriority)}`}>{rowPriority}</td>
                          <td className="px-6 py-4">
                            <span className={`text-xs font-medium px-2.5 py-1 rounded-full border ${
                              isResolved 
                                ? 'bg-emerald-900/50 text-emerald-400 border-emerald-800/50' 
                                : 'bg-blue-900/50 text-blue-400 border-blue-800/50'
                            }`}>
                              {isResolved ? 'Resolved' : 'Active'}
                            </span>
                          </td>
                          <td className="px-6 py-4">{inc.triage?.category || 'General'}</td>
                          <td className="px-6 py-4 text-right">
                            <button className="text-blue-400 hover:text-blue-300 font-medium text-xs uppercase tracking-wider transition-colors">
                              View Details
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                    {incidents.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-6 py-12 text-center text-slate-500 font-medium">
                          No active incidents reported. Setup the background log generators to start receiving alerts.
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </main>
          </div>
        )}

        {/* TAB 2: INCIDENT DETAILS WORKSPACE */}
        {activeTab === 'details' && activeIncident && (
          <div className="absolute inset-0 flex gap-3">
            
            {/* Left Panel: Architecture Flow Map */}
            <main className="flex-1 glass-panel rounded-xl p-6 overflow-y-auto flex flex-col items-center relative">
              <div className="w-full flex justify-between items-start mb-2">
                <h2 className="text-lg font-semibold text-slate-200">Agentic Architecture Map</h2>
                <div className="text-xs text-slate-500 uppercase tracking-wider font-semibold bg-slate-800/50 px-3 py-1 rounded-md border border-slate-700">
                  Live Orchestration
                </div>
              </div>

              {/* Visual Grid Map */}
              <div className="flex flex-col items-center gap-2 w-full max-w-4xl mx-auto mt-4 pb-10">
                
                {/* 1. InsightWatch (Ingest Monitor) */}
                <div className={`node-base w-72 bg-slate-800 border border-slate-600 rounded-xl p-3 flex items-center gap-4 text-left ${getNodeClass('node-insight')}`}>
                  <div className="p-2.5 rounded-lg bg-slate-700/50 text-rose-400">
                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                      <path stroke-linecap="round" stroke-linejoin="round" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="font-bold text-sm text-slate-200">InsightWatch</h3>
                    <p className="text-[0.65rem] text-slate-400">Monitoring Ingest Agent</p>
                  </div>
                </div>

                {/* Arrow down to SmartQueue */}
                <svg className={`w-6 h-6 text-slate-600 transition-colors duration-300 ${getArrowClass('arr-1')}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>

                {/* 2. SmartQueue (Triage Agent) */}
                <div className={`node-base w-72 bg-slate-800 border border-slate-600 rounded-xl p-3 flex items-center gap-4 text-left ${getNodeClass('node-smart')}`}>
                  <div className="p-2.5 rounded-lg bg-slate-700/50 text-sky-400">
                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="font-bold text-sm text-slate-200">SmartQueue</h3>
                    <p className="text-[0.65rem] text-slate-400">Triage & Routing Agent</p>
                  </div>
                </div>

                {/* Arrow down to ResolveAI */}
                <svg className={`w-6 h-6 text-slate-600 transition-colors duration-300 ${getArrowClass('arr-2')}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>

                {/* 3. ResolveAI (Diagnosis Agent) */}
                <div className={`node-base w-80 bg-slate-800 border border-slate-600 rounded-xl p-3 flex items-center gap-4 text-left ${getNodeClass('node-resolve')}`}>
                  <div className="p-2.5 rounded-lg bg-slate-700/50 text-fuchsia-400">
                    <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                    </svg>
                  </div>
                  <div>
                    <h3 className="font-bold text-sm text-slate-200">ResolveAI + KnowledgeAgent</h3>
                    <p className="text-[0.65rem] text-slate-400">Diagnosis & Deep Analytics</p>
                  </div>
                </div>

                {/* Link connector line down */}
                <div className="h-6 w-px bg-slate-600 my-1 relative">
                  <div className={`absolute inset-0 bg-blue-500 w-full h-full opacity-0 transition-opacity duration-300 shadow-[0_0_8px_rgba(59,130,246,1)] ${getArrowClass('arr-3')}`}></div>
                </div>

                {/* Middle Cross Section layout */}
                <div className="w-full grid grid-cols-[1fr_auto_1fr] gap-6 items-center">
                  
                  {/* Left: Knowledge Base (MCP DB) */}
                  <div className="flex justify-end relative">
                    <div className={`node-base w-60 bg-slate-800 border-dashed border-2 border-slate-600 rounded-xl p-4 text-left relative z-10 ${getNodeClass('node-mcp')}`}>
                      <div className="flex items-center gap-2 mb-2">
                        <svg className="w-5 h-5 text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4" />
                        </svg>
                        <h3 className="font-bold text-sm text-slate-200">Knowledge Base</h3>
                      </div>
                      <p className="text-[0.65rem] text-slate-400 leading-tight">
                        MCP (Model Context Protocol): Vector DB, Runbooks, Historical Configs
                      </p>
                    </div>
                    {/* Arrow pointing to center */}
                    <div className="absolute right-[-1.5rem] top-1/2 -translate-y-1/2 flex items-center z-0">
                      <svg className={`w-6 h-6 text-slate-600 transition-colors duration-300 ${getArrowClass('arr-mcp')}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                      </svg>
                    </div>
                  </div>

                  {/* Center: Supervisor Orchestrator */}
                  <div className={`node-base w-44 h-44 rounded-full bg-slate-800 border-4 border-slate-700 flex flex-col justify-center items-center text-center shadow-lg relative z-20 ${getNodeClass('node-supervisor')}`}>
                    <svg className="w-10 h-10 text-indigo-400 mb-2" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                    </svg>
                    <h2 className="font-bold text-sm text-slate-100 leading-tight">Supervisor<br/>Orchestration</h2>
                    <span className="text-[0.6rem] text-indigo-300/80 mt-1 uppercase tracking-widest">Agent</span>
                  </div>

                  {/* Right: Subagents list (Policy, Infra, Verify) */}
                  <div className="flex flex-col gap-3 relative pl-6">
                    {/* Arrow pointing from center to right */}
                    <div className="absolute left-[-1.5rem] top-1/2 -translate-y-1/2 flex items-center z-0">
                      <svg className={`w-6 h-6 text-slate-600 transition-colors duration-300 ${getArrowClass('arr-sub')}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 8l4 4m0 0l-4 4m4-4H3" />
                      </svg>
                    </div>

                    <div className={`node-base w-64 bg-slate-800/80 border-l-4 border-slate-700 border-y border-r rounded-r-xl p-3 flex items-center gap-3 ${getNodeClass('node-sub-policy')}`}>
                      <div className="p-1.5 rounded bg-slate-700 text-slate-300">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
                        </svg>
                      </div>
                      <span className="text-xs font-semibold text-slate-200">Policy & Rule Check</span>
                    </div>

                    <div className={`node-base w-64 bg-slate-800/80 border-l-4 border-slate-700 border-y border-r rounded-r-xl p-3 flex items-center gap-3 ${getNodeClass('node-sub-infra')}`}>
                      <div className="p-1.5 rounded bg-slate-700 text-slate-300">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" />
                        </svg>
                      </div>
                      <span className="text-xs font-semibold text-slate-200">Infrastructure Execution</span>
                    </div>

                    <div className={`node-base w-64 bg-slate-800/80 border-l-4 border-slate-700 border-y border-r rounded-r-xl p-3 flex items-center gap-3 ${getNodeClass('node-sub-verify')}`}>
                      <div className="p-1.5 rounded bg-slate-700 text-slate-300">
                        <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                        </svg>
                      </div>
                      <span className="text-xs font-semibold text-slate-200">Change Verification</span>
                    </div>

                  </div>
                </div>

                {/* Arrow down to Security Layer */}
                <svg className={`w-6 h-6 text-slate-600 mt-4 mb-2 transition-colors duration-300 ${getArrowClass('arr-4')}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 14l-7 7m0 0l-7-7m7 7V3" />
                </svg>

                {/* Bottom: Security Layer (A2A) */}
                <div className={`node-base w-full max-w-2xl bg-slate-900/80 border border-slate-700 border-t-4 border-t-amber-500 rounded-lg p-4 flex flex-col items-center shadow-lg relative overflow-hidden ${getNodeClass('node-security')}`}>
                  <div className="absolute inset-0 opacity-[0.03]" style={{ backgroundImage: 'repeating-linear-gradient(45deg, #f59e0b 25%, transparent 25%, transparent 75%, #f59e0b 75%, #f59e0b), repeating-linear-gradient(45deg, #f59e0b 25%, transparent 25%, transparent 75%, #f59e0b 75%, #f59e0b)', backgroundPosition: '0 0, 10px 10px', backgroundSize: '20px 20px' }}></div>
                  <div className="flex items-center gap-3 mb-2 relative z-10">
                    <svg className="w-4 h-4 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
                    </svg>
                    <h3 className="font-bold text-xs tracking-widest text-slate-300 uppercase">
                      A2A Communication & Security Zone
                    </h3>
                  </div>
                  <div className="flex flex-wrap justify-center gap-x-8 gap-y-2 text-[0.65rem] text-slate-400 font-mono relative z-10">
                    <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-500/50"></span> Mutual TLS (mTLS)</span>
                    <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-500/50"></span> OAuth2/JWT Tokens</span>
                    <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-500/50"></span> OPA Authorization</span>
                  </div>
                </div>

              </div>
            </main>

            {/* Right Panel: Workflow Status & Logs */}
            <aside className="w-[30rem] flex flex-col gap-3 shrink-0 h-full overflow-y-auto pr-2 pb-4">
              
              {/* Metadata Row */}
              <div className="glass-panel p-3 rounded-xl flex items-center justify-between shadow-md shrink-0 bg-slate-900/30">
                <div>
                  <div className="text-[0.65rem] text-slate-400 font-bold uppercase tracking-widest mb-1">
                    Incident Workflow
                  </div>
                  <div className="text-sm font-mono font-bold text-slate-200 bg-slate-800 px-2 py-0.5 rounded border border-slate-700">
                    INC-{activeIncident.incident_id}
                  </div>
                </div>
                <div className="flex gap-2 text-center">
                  <div className="bg-slate-850 border border-slate-700 px-2.5 py-1.5 rounded-lg w-18">
                    <div className="text-[0.55rem] text-slate-400 uppercase font-bold">Priority</div>
                    <div className={`text-xs font-bold ${getPriorityBadgeClass(activeIncident.triage?.priority)}`}>
                      {activeIncident.triage?.priority || 'P4'}
                    </div>
                  </div>
                  <div className="bg-slate-850 border border-slate-700 px-2.5 py-1.5 rounded-lg w-18">
                    <div className="text-[0.55rem] text-slate-400 uppercase font-bold">Category</div>
                    <div className="text-xs font-bold text-slate-200">
                      {activeIncident.triage?.category || 'General'}
                    </div>
                  </div>
                  <div className="bg-slate-850 border border-slate-700 px-2.5 py-1.5 rounded-lg w-24">
                    <div className="text-[0.55rem] text-slate-400 uppercase font-bold">Status</div>
                    <div className={`text-xs font-bold ${
                      activeIncident.resolution?.status === 'resolved' ? 'text-emerald-400' : 'text-amber-400'
                    }`}>
                      {activeIncident.resolution?.status || 'pending'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Resolution Summary (Shown on completion) */}
              {activeIncident.resolution?.status === 'resolved' && (
                <div className="glass-panel p-4 rounded-xl border-l-4 border-l-emerald-500 shadow-[0_4px_20px_rgba(16,185,129,0.15)] transition-all duration-500 shrink-0">
                  <h3 className="text-xs font-bold text-emerald-400 uppercase tracking-widest mb-2 flex items-center gap-2">
                    <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    AI Resolution Summary
                  </h3>
                  <p className="text-xs text-slate-200 leading-relaxed font-medium">
                    {activeIncident.resolution?.recommendation || 'The incident was resolved successfully using agentic auto-remediation playbooks.'}
                  </p>
                </div>
              )}

              {/* Progress Flow Tracker */}
              <div className="glass-panel p-5 rounded-xl flex flex-col shrink-0 relative bg-slate-900/10">
                <h3 className="text-sm font-bold text-white mb-5 flex items-center gap-2">
                  <svg className="w-4 h-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
                  </svg>
                  Resolution Progress
                </h3>
                
                <div className="relative pl-3 pr-2 pb-2">
                  {/* Background vertical line */}
                  <div className="absolute left-[1.1rem] top-2 bottom-8 w-px bg-slate-700/60 z-0"></div>
                  {/* Glowing dynamic height progress line */}
                  <div 
                    className="absolute left-[1.1rem] top-2 w-px bg-blue-500 transition-all duration-700 shadow-[0_0_8px_rgba(59,130,246,0.8)] z-0" 
                    style={{ height: stepperProgress.height }}
                  />

                  {/* Step 0 */}
                  <div className={`relative flex items-start gap-4 transition-all duration-500 mb-6 ${
                    stepperProgress.steps[0] === 'pending' ? 'opacity-40' : 'opacity-100'
                  }`}>
                    {renderStepIcon(stepperProgress.steps[0])}
                    <div>
                      <h4 className="text-sm font-bold text-slate-200">Incident Alert Reported</h4>
                      <p className="text-[0.7rem] text-slate-400 mt-1 leading-relaxed">
                        Monitoring systems ingest alert triggers, parsing log files and raising the incident.
                      </p>
                    </div>
                  </div>

                  {/* Step 1 */}
                  <div className={`relative flex items-start gap-4 transition-all duration-500 mb-6 ${
                    stepperProgress.steps[1] === 'pending' ? 'opacity-40' : 'opacity-100'
                  }`}>
                    {renderStepIcon(stepperProgress.steps[1])}
                    <div>
                      <h4 className="text-sm font-bold text-slate-200">Resolution Execution</h4>
                      <p className="text-[0.7rem] text-slate-400 mt-1 leading-relaxed">
                        Orchestrator pulls corresponding runbooks and executes sandbox remediation jobs.
                      </p>
                    </div>
                  </div>

                  {/* Step 2 */}
                  <div className={`relative flex items-start gap-4 transition-all duration-500 mb-6 ${
                    stepperProgress.steps[2] === 'pending' ? 'opacity-40' : 'opacity-100'
                  }`}>
                    {renderStepIcon(stepperProgress.steps[2])}
                    <div>
                      <h4 className="text-sm font-bold text-slate-200">Technical Validation</h4>
                      <p className="text-[0.7rem] text-slate-400 mt-1 leading-relaxed">
                        Verification Agent runs endpoint health pings and metric checks to confirm status.
                      </p>
                    </div>
                  </div>

                  {/* Step 3 */}
                  <div className={`relative flex items-start gap-4 transition-all duration-500 ${
                    stepperProgress.steps[3] === 'pending' ? 'opacity-40' : 'opacity-100'
                  }`}>
                    {renderStepIcon(stepperProgress.steps[3])}
                    <div>
                      <h4 className="text-sm font-bold text-slate-200">Record Closure</h4>
                      <p className="text-[0.7rem] text-slate-400 mt-1 leading-relaxed">
                        Logs finalized, compliance reports submitted, and incident record closed.
                      </p>
                    </div>
                  </div>
                </div>

                {/* Manual approval for P0/P1 alerts (HITL simulation) */}
                {activeIncident.resolution?.status === 'pending' && (activeIncident.triage?.priority === 'P0' || activeIncident.triage?.priority === 'P1') && (
                  <div className="mt-4 p-3 bg-amber-500/10 border border-amber-500/30 rounded-lg flex items-center justify-between shadow-[0_0_15px_rgba(245,158,11,0.05)]">
                    <div className="flex gap-2 items-center text-amber-400 text-xs font-semibold">
                      <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      Awaiting Action (HITL Gate)
                    </div>
                    <button 
                      onClick={resolveIncident}
                      disabled={isUpdating}
                      className="px-3 py-1 bg-amber-500 hover:bg-amber-600 disabled:bg-slate-700 text-slate-950 text-xs font-bold rounded shadow transition-colors"
                    >
                      Authorize Fix
                    </button>
                  </div>
                )}

                {/* Success Banner */}
                {activeIncident.resolution?.status === 'resolved' && (
                  <div className="mt-4 bg-emerald-500/20 border border-emerald-500/50 text-emerald-400 p-2.5 rounded-lg flex items-center justify-center gap-2 font-bold text-sm shadow-[0_0_20px_rgba(16,185,129,0.2)] z-20">
                    <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="2">
                      <path stroke-linecap="round" stroke-linejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                    Incident resolved successfully
                  </div>
                )}
              </div>

              {/* Real-time Agent Logs Terminal */}
              <div className="glass-panel rounded-xl flex flex-col shrink-0 h-[22rem] border-t-2 border-t-slate-700/50 overflow-hidden bg-[#09090b]">
                <div className="bg-slate-900/80 px-4 py-2 border-b border-slate-800 flex justify-between items-center shrink-0">
                  <h3 className="text-xs font-bold text-slate-400 uppercase tracking-widest flex items-center gap-2">
                    <svg className="w-3.5 h-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 9l3 3-3 3m5 0h3M5 20h14a2 2 0 002-2V6a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                    </svg>
                    Real-time Agent Logs
                  </h3>
                  <div className="flex gap-1.5">
                    <div className="w-2.5 h-2.5 rounded-full bg-slate-700"></div>
                    <div className="w-2.5 h-2.5 rounded-full bg-slate-700"></div>
                    <div className="w-2.5 h-2.5 rounded-full bg-slate-700"></div>
                  </div>
                </div>
                
                <div ref={logWrapperRef} className="p-3 overflow-y-auto flex-1 shadow-inner">
                  <div className="space-y-1.5 pb-2">
                    <div className="font-mono text-[0.7rem] leading-relaxed tracking-wide text-slate-500">
                      Platform initialized. Monitoring telemetry feeds... <span className="cursor-blink">_</span>
                    </div>
                    {(activeIncident.agent_history || []).map((logEv, idx) => renderLogLine(logEv, idx))}
                  </div>
                </div>
              </div>

            </aside>
          </div>
        )}
      </div>

      {/* Footer System Status details */}
      <div className="flex justify-between items-center text-[0.65rem] text-slate-500 font-mono px-2 shrink-0">
        <div>ORCHESTRATOR PATH: {activeIncidentId ? `incidents/${activeIncidentId}/stream` : 'idle'}</div>
        <div className="flex items-center gap-3">
          <span>HOST: localhost:8000</span>
          <span>PROVIDER: {activeIncident?.triage?.category ? 'PostgreSQL' : 'SQLite'}</span>
        </div>
      </div>

    </div>
  );
}
