import React, { useState } from 'react';
import { 
  Code2, 
  Copy, 
  Check, 
  Play, 
  Key, 
  Layers, 
  Workflow, 
  Server, 
  Cpu, 
  ShieldCheck, 
  ExternalLink, 
  ChevronRight,
  Database,
  ArrowDown,
  ArrowRight,
  CheckCircle2,
  Plug,
  Boxes,
  FileSpreadsheet,
  Webhook,
  Terminal,
  Settings,
  Sparkles,
  RefreshCw,
  SlidersHorizontal,
  HardHat,
  Factory,
  Radio,
  FileCode2,
  Lock,
  Layers3,
  Lightbulb
} from 'lucide-react';
import { API_ENDPOINTS } from '../mockData';
import { ApiEndpoint } from '../types';

interface APIIntegrationsViewProps {
  onNavigateToCanonicalModel?: () => void;
}

export const APIIntegrationsView: React.FC<APIIntegrationsViewProps> = ({ onNavigateToCanonicalModel }) => {
  const [endpoints] = useState<ApiEndpoint[]>(API_ENDPOINTS);
  const [selectedEndpoint, setSelectedEndpoint] = useState<ApiEndpoint>(API_ENDPOINTS[0]);
  const [requestBody, setRequestBody] = useState(selectedEndpoint.sampleRequest);
  const [responseOutput, setResponseOutput] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<'all' | 'ingestion' | 'intelligence'>('all');
  const [selectedConnectModal, setSelectedConnectModal] = useState<string | null>(null);
  const [connectedSystems, setConnectedSystems] = useState<{ [key: string]: boolean }>({
    'safelytic': true,
    'ehs': true,
    'erp': true,
    'iot': true,
    'cmms': false,
    'lms': false,
    'warehouse': false,
    'hr': false
  });

  const handleSelectEndpoint = (ep: ApiEndpoint) => {
    setSelectedEndpoint(ep);
    setRequestBody(ep.sampleRequest);
    setResponseOutput(null);
  };

  const handleRunRequest = () => {
    setIsLoading(true);
    setTimeout(() => {
      setResponseOutput(selectedEndpoint.sampleResponse);
      setIsLoading(false);
    }, 380);
  };

  const handleCopyCode = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  const toggleConnection = (systemId: string) => {
    setConnectedSystems(prev => ({
      ...prev,
      [systemId]: !prev[systemId]
    }));
    setSelectedConnectModal(null);
  };

  const filteredEndpoints = endpoints.filter(ep => {
    if (activeTab === 'ingestion') return ep.method === 'POST' && ep.path !== '/api/v1/feedback';
    if (activeTab === 'intelligence') return ep.method === 'GET' || ep.path === '/api/v1/feedback';
    return true;
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header with Primary Proposition */}
      <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2 flex-wrap">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <Code2 className="w-6 h-6 text-cyan-400" />
              <span>SIE Integration & API Platform</span>
            </h1>
            <span className="text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-700 font-semibold">
              Application-Agnostic
            </span>
          </div>
          
          {/* Prominent Primary Message */}
          <div className="mt-2.5 text-base sm:text-lg font-extrabold text-cyan-300 tracking-tight">
            "Use SIE with your existing systems. You do not need Safelytic."
          </div>
          
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            The Safelytic Intelligence Engine (SIE) operates as an independent safety intelligence brain. Ingest observations, incidents, audits, and operational telemetry from your existing enterprise stack or custom software.
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <div className="p-2.5 px-3.5 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono text-cyan-300 flex items-center gap-2 shadow-sm">
            <Key className="w-3.5 h-3.5 text-cyan-400" />
            <span>Key: <strong className="text-slate-100">sie_live_9f82...3b1a</strong></span>
          </div>
        </div>
      </div>

      {/* Prominent Architectural Statement Banner */}
      <div className="p-4 rounded-xl bg-gradient-to-r from-slate-900 via-cyan-950/40 to-slate-900 border border-cyan-800/60 flex flex-col md:flex-row md:items-center justify-between gap-3 shadow-md">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-lg bg-cyan-950 border border-cyan-700 text-cyan-300 shrink-0">
            <Sparkles className="w-5 h-5 text-cyan-400" />
          </div>
          <div>
            <span className="text-xs sm:text-sm font-bold text-slate-100 block">
              SIE is application-agnostic. Safelytic is one consumer of the Intelligence Engine.
            </span>
            <span className="text-[11px] text-slate-400">
              Integrate with your ERP, EHS software, CMMS, IoT gateways, or custom mobile applications with identical mathematical rigor.
            </span>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[11px] font-mono text-cyan-300 shrink-0">
          <span className="px-2.5 py-1 rounded bg-slate-950 border border-cyan-700/60 font-semibold">
            Zero Vendor Lock-in
          </span>
        </div>
      </div>

      {/* 3 Integration Pathways Cards */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
            <Plug className="w-4 h-4 text-cyan-400" />
            <span>Three Integration Pathways</span>
          </h2>
          <span className="text-xs text-slate-400 font-mono">Connect Any Data Source</span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {/* Pathway 1: Safelytic Native */}
          <div className="p-5 rounded-xl bg-slate-900/90 border border-emerald-700/60 relative overflow-hidden flex flex-col justify-between shadow-sm">
            <div className="space-y-3">
              <div className="flex items-start justify-between">
                <div className="p-2.5 rounded-lg bg-emerald-950 border border-emerald-800 text-emerald-400">
                  <Boxes className="w-5 h-5" />
                </div>
                <div className="text-right">
                  <span className="text-[10px] uppercase font-mono text-slate-400 block">Status</span>
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-mono font-bold px-2.5 py-1 rounded bg-emerald-950 text-emerald-300 border border-emerald-700 mt-0.5">
                    <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    <span>Connected</span>
                  </span>
                </div>
              </div>

              <div>
                <span className="text-[10px] font-mono text-emerald-400 font-bold uppercase tracking-wider">Pathway 1</span>
                <h3 className="text-lg font-bold text-white mt-0.5">1. Safelytic</h3>
                <p className="text-xs text-emerald-300/90 font-medium mt-1">
                  Native integration.
                </p>
                <p className="text-xs text-slate-400 mt-1 leading-relaxed">
                  Turnkey native synchronization with the Safelytic front-end suite, supervisor portal, and mobile worker apps.
                </p>
              </div>

              <div className="pt-2 text-[11px] text-slate-400 space-y-1 font-mono">
                <div className="flex items-center justify-between text-slate-300">
                  <span>Integration Type:</span>
                  <strong className="text-emerald-300">Native Core Protocol</strong>
                </div>
                <div className="flex items-center justify-between text-slate-300">
                  <span>Data Flow:</span>
                  <strong className="text-cyan-300">Bi-directional Live Stream</strong>
                </div>
                <div className="flex items-center justify-between text-slate-300">
                  <span>Consumer Status:</span>
                  <strong className="text-emerald-300">Active Consumer #1</strong>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800 text-[11px] font-mono text-emerald-300 flex items-center justify-between">
              <span>Status: Connected</span>
              <span className="text-[10px] text-slate-500">Zero Configuration</span>
            </div>
          </div>

          {/* Pathway 2: Existing Enterprise Systems */}
          <div className="p-5 rounded-xl bg-slate-900/90 border border-cyan-800/60 relative overflow-hidden flex flex-col justify-between shadow-sm">
            <div className="space-y-3">
              <div className="flex items-start justify-between">
                <div className="p-2.5 rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400">
                  <Database className="w-5 h-5" />
                </div>
                <div className="text-right">
                  <span className="text-[10px] uppercase font-mono text-slate-400 block">Status</span>
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-mono font-bold px-2.5 py-1 rounded bg-cyan-950 text-cyan-300 border border-cyan-700 mt-0.5">
                    <Plug className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Connect</span>
                  </span>
                </div>
              </div>

              <div>
                <span className="text-[10px] font-mono text-cyan-400 font-bold uppercase tracking-wider">Pathway 2</span>
                <h3 className="text-lg font-bold text-white mt-0.5">2. Existing Enterprise Systems</h3>
                <p className="text-xs text-cyan-300/90 font-medium mt-1">
                  Connect your existing enterprise platforms directly to SIE.
                </p>
              </div>

              <div className="space-y-1.5 pt-1">
                <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider font-semibold block">
                  Examples & Connectors:
                </span>
                <div className="grid grid-cols-2 gap-1.5 text-[10px] font-mono">
                  <div className="p-1.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300">EHS / EHSQ</span>
                    <button onClick={() => setSelectedConnectModal('EHS/EHSQ')} className="text-cyan-400 hover:underline font-bold">
                      {connectedSystems['ehs'] ? 'Connected' : 'Connect'}
                    </button>
                  </div>
                  <div className="p-1.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300">ERP</span>
                    <button onClick={() => setSelectedConnectModal('ERP')} className="text-cyan-400 hover:underline font-bold">
                      {connectedSystems['erp'] ? 'Connected' : 'Connect'}
                    </button>
                  </div>
                  <div className="p-1.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300">HR</span>
                    <button onClick={() => setSelectedConnectModal('HR')} className="text-cyan-400 hover:underline font-bold">
                      {connectedSystems['hr'] ? 'Connected' : 'Connect'}
                    </button>
                  </div>
                  <div className="p-1.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300">Training / LMS</span>
                    <button onClick={() => setSelectedConnectModal('Training/LMS')} className="text-cyan-400 hover:underline font-bold">
                      {connectedSystems['lms'] ? 'Connected' : 'Connect'}
                    </button>
                  </div>
                  <div className="p-1.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300">CMMS</span>
                    <button onClick={() => setSelectedConnectModal('CMMS')} className="text-cyan-400 hover:underline font-bold">
                      {connectedSystems['cmms'] ? 'Connected' : 'Connect'}
                    </button>
                  </div>
                  <div className="p-1.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between">
                    <span className="text-slate-300">IoT</span>
                    <button onClick={() => setSelectedConnectModal('IoT')} className="text-cyan-400 hover:underline font-bold">
                      {connectedSystems['iot'] ? 'Connected' : 'Connect'}
                    </button>
                  </div>
                  <div className="p-1.5 rounded bg-slate-950 border border-slate-800 flex items-center justify-between col-span-2">
                    <span className="text-slate-300">Data Warehouse</span>
                    <button onClick={() => setSelectedConnectModal('Data Warehouse')} className="text-cyan-400 hover:underline font-bold">
                      {connectedSystems['warehouse'] ? 'Connected' : 'Connect'}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between">
              <button
                onClick={() => setSelectedConnectModal('Enterprise Connector Hub')}
                className="text-xs text-cyan-400 hover:text-cyan-300 font-semibold flex items-center gap-1"
              >
                <span>Status: Connect Systems</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>

          {/* Pathway 3: Custom Applications */}
          <div className="p-5 rounded-xl bg-slate-900/90 border border-purple-800/60 relative overflow-hidden flex flex-col justify-between shadow-sm">
            <div className="space-y-3">
              <div className="flex items-start justify-between">
                <div className="p-2.5 rounded-lg bg-purple-950 border border-purple-800 text-purple-400">
                  <Terminal className="w-5 h-5" />
                </div>
                <div className="text-right">
                  <span className="text-[10px] uppercase font-mono text-slate-400 block">Integration</span>
                  <span className="inline-flex items-center gap-1.5 text-[11px] font-mono font-bold px-2.5 py-1 rounded bg-purple-950 text-purple-300 border border-purple-700 mt-0.5">
                    <Code2 className="w-3.5 h-3.5 text-purple-400" />
                    <span>Developer Ingestion</span>
                  </span>
                </div>
              </div>

              <div>
                <span className="text-[10px] font-mono text-purple-400 font-bold uppercase tracking-wider">Pathway 3</span>
                <h3 className="text-lg font-bold text-white mt-0.5">3. Custom Applications</h3>
                <p className="text-xs text-purple-300/90 font-medium mt-1">
                  Connect proprietary systems, bespoke frontends, or automation scripts.
                </p>
              </div>

              <div className="space-y-1.5 pt-1">
                <span className="text-[10px] font-mono text-slate-400 uppercase tracking-wider font-semibold block">
                  Integration Methods:
                </span>
                <div className="flex flex-col gap-1.5 text-xs font-mono">
                  <div className="p-2 rounded bg-slate-950 border border-slate-800 flex items-center justify-between text-slate-200">
                    <span className="flex items-center gap-1.5"><Code2 className="w-3.5 h-3.5 text-cyan-400" /> REST API</span>
                    <span className="text-[10px] text-slate-400">JSON v1 Endpoints</span>
                  </div>
                  <div className="p-2 rounded bg-slate-950 border border-slate-800 flex items-center justify-between text-slate-200">
                    <span className="flex items-center gap-1.5"><Webhook className="w-3.5 h-3.5 text-purple-400" /> Webhooks</span>
                    <span className="text-[10px] text-slate-400">Real-time Push</span>
                  </div>
                  <div className="p-2 rounded bg-slate-950 border border-slate-800 flex items-center justify-between text-slate-200">
                    <span className="flex items-center gap-1.5"><Layers className="w-3.5 h-3.5 text-amber-400" /> Batch upload</span>
                    <span className="text-[10px] text-slate-400">Scheduled S3/SFTP</span>
                  </div>
                  <div className="p-2 rounded bg-slate-950 border border-slate-800 flex items-center justify-between text-slate-200">
                    <span className="flex items-center gap-1.5"><FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" /> CSV/Excel</span>
                    <span className="text-[10px] text-slate-400">Manual & Auto Ingestion</span>
                  </div>
                  <div className="p-2 rounded bg-slate-950 border border-slate-800 flex items-center justify-between text-slate-200">
                    <span className="flex items-center gap-1.5"><FileCode2 className="w-3.5 h-3.5 text-blue-400" /> SDK</span>
                    <span className="text-[10px] text-slate-400">Python, Node, Go</span>
                  </div>
                </div>
              </div>
            </div>

            <div className="mt-4 pt-3 border-t border-slate-800 flex items-center justify-between">
              <span className="text-[11px] font-mono text-purple-300">OpenAPI 3.1 & SDKs</span>
              <button 
                onClick={() => {
                  const el = document.getElementById('api-tester-workbench');
                  el?.scrollIntoView({ behavior: 'smooth' });
                }}
                className="text-xs text-cyan-400 hover:text-cyan-300 font-semibold flex items-center gap-1"
              >
                <span>Explore Endpoints</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Visual System Architecture Diagram */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-800/80">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Workflow className="w-4 h-4 text-cyan-400" />
              <span>End-to-End Safety Intelligence Pipeline</span>
            </h3>
            <p className="text-[11px] text-slate-400">
              How any operational source is mapped to the canonical model and converted into actionable intelligence
            </p>
          </div>
          <span className="text-[10px] font-mono px-2.5 py-1 rounded bg-slate-950 text-cyan-300 border border-cyan-800 shrink-0">
            Harmonized Schema v2.4
          </span>
        </div>

        {/* 5-Stage Visual Linear Pipeline: Existing Application ↓ SIE API ↓ Canonical Safety Data Model ↓ Intelligence Engine ↓ Prediction / Analysis / Recommendation */}
        <div className="grid grid-cols-1 sm:grid-cols-5 gap-3 pt-2">
          {/* Stage 1 */}
          <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 space-y-2 text-center relative group hover:border-cyan-500 transition-colors">
            <div className="w-9 h-9 mx-auto rounded-lg bg-blue-950 border border-blue-800 text-blue-400 flex items-center justify-center">
              <Server className="w-4 h-4" />
            </div>
            <div className="text-[10px] font-mono uppercase text-blue-400 font-bold">Step 1</div>
            <h4 className="text-xs font-bold text-white">Existing Application</h4>
            <p className="text-[11px] text-slate-400 leading-snug">
              Safelytic, SAP ERP, Intelex, Maximo, Spreadsheets, or Custom App
            </p>
            <div className="sm:hidden text-slate-500 font-mono text-xs pt-1">
              ↓
            </div>
          </div>

          {/* Stage 2 */}
          <div className="p-3.5 rounded-xl bg-slate-950 border border-cyan-800/80 space-y-2 text-center relative group hover:border-cyan-400 transition-colors shadow-sm">
            <div className="w-9 h-9 mx-auto rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400 flex items-center justify-center">
              <Code2 className="w-4 h-4" />
            </div>
            <div className="text-[10px] font-mono uppercase text-cyan-400 font-bold">Step 2</div>
            <h4 className="text-xs font-bold text-cyan-200">SIE API</h4>
            <p className="text-[11px] text-slate-300 leading-snug">
              REST Endpoints, Webhooks, Batch Uploads, CSV/Excel, SDKs
            </p>
            <div className="sm:hidden text-slate-500 font-mono text-xs pt-1">
              ↓
            </div>
          </div>

          {/* Stage 3 */}
          <div 
            onClick={onNavigateToCanonicalModel}
            className="p-3.5 rounded-xl bg-slate-950 border border-cyan-700/60 space-y-2 text-center relative group hover:border-cyan-400 transition-colors shadow-sm cursor-pointer"
          >
            <div className="w-9 h-9 mx-auto rounded-lg bg-cyan-900 border border-cyan-600 text-white flex items-center justify-center">
              <Layers3 className="w-4 h-4 text-cyan-300" />
            </div>
            <div className="text-[10px] font-mono uppercase text-cyan-300 font-bold">Step 3</div>
            <h4 className="text-xs font-bold text-white group-hover:text-cyan-300 transition-colors">Canonical Safety Data Model</h4>
            <p className="text-[11px] text-slate-400 leading-snug">
              Harmonized Taxonomy, Vectorization, Schema Validation & Cleansing
            </p>
            {onNavigateToCanonicalModel && (
              <span className="inline-block text-[10px] text-cyan-400 font-mono underline pt-1">
                Explore Model →
              </span>
            )}
            <div className="sm:hidden text-slate-500 font-mono text-xs pt-1">
              ↓
            </div>
          </div>

          {/* Stage 4 */}
          <div className="p-3.5 rounded-xl bg-slate-950 border border-purple-800/80 space-y-2 text-center relative group hover:border-purple-500 transition-colors">
            <div className="w-9 h-9 mx-auto rounded-lg bg-purple-950 border border-purple-800 text-purple-400 flex items-center justify-center">
              <Cpu className="w-4 h-4" />
            </div>
            <div className="text-[10px] font-mono uppercase text-purple-400 font-bold">Step 4</div>
            <h4 className="text-xs font-bold text-white">Intelligence Engine</h4>
            <p className="text-[11px] text-slate-400 leading-snug">
              Causal Bayesian Graph, Precursor Surges & 436 Verified Standards
            </p>
            <div className="sm:hidden text-slate-500 font-mono text-xs pt-1">
              ↓
            </div>
          </div>

          {/* Stage 5 */}
          <div className="p-3.5 rounded-xl bg-gradient-to-b from-slate-950 to-emerald-950/40 border border-emerald-800/80 space-y-2 text-center relative group hover:border-emerald-500 transition-colors">
            <div className="w-9 h-9 mx-auto rounded-lg bg-emerald-950 border border-emerald-700 text-emerald-400 flex items-center justify-center">
              <ShieldCheck className="w-4 h-4" />
            </div>
            <div className="text-[10px] font-mono uppercase text-emerald-400 font-bold">Step 5</div>
            <h4 className="text-xs font-bold text-white">Prediction / Analysis / Recommendation</h4>
            <p className="text-[11px] text-slate-300 leading-snug">
              Predictions, Precursor Analysis, Prioritized Recommendations
            </p>
          </div>
        </div>
      </div>

      {/* Interactive API Tester & Endpoints Workbench */}
      <div id="api-tester-workbench" className="space-y-4 pt-2">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div>
            <h2 className="text-sm font-bold text-slate-200 uppercase tracking-wider flex items-center gap-2">
              <Terminal className="w-4 h-4 text-cyan-400" />
              <span>SIE API Capabilities & Interactive Workbench</span>
            </h2>
            <p className="text-xs text-slate-400">
              10 example production endpoints for ingestion, prediction retrieval, and closed-loop feedback
            </p>
          </div>

          {/* Filter Tabs */}
          <div className="flex items-center gap-1.5 p-1 rounded-lg bg-slate-900 border border-slate-800 text-xs font-medium">
            <button
              onClick={() => setActiveTab('all')}
              className={`px-2.5 py-1 rounded-md transition-colors ${activeTab === 'all' ? 'bg-cyan-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
            >
              All (10)
            </button>
            <button
              onClick={() => setActiveTab('ingestion')}
              className={`px-2.5 py-1 rounded-md transition-colors ${activeTab === 'ingestion' ? 'bg-cyan-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Data Ingestion (6)
            </button>
            <button
              onClick={() => setActiveTab('intelligence')}
              className={`px-2.5 py-1 rounded-md transition-colors ${activeTab === 'intelligence' ? 'bg-cyan-600 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
            >
              Intelligence & Feedback (4)
            </button>
          </div>
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
          {/* Endpoints Sidebar (5 cols) */}
          <div className="lg:col-span-5 space-y-2 max-h-[580px] overflow-y-auto pr-1">
            {filteredEndpoints.map((ep) => {
              const isSelected = selectedEndpoint.path === ep.path;
              return (
                <div
                  key={ep.path}
                  onClick={() => handleSelectEndpoint(ep)}
                  className={`p-3 rounded-lg border cursor-pointer transition-all ${
                    isSelected
                      ? 'bg-cyan-950/60 border-cyan-400 shadow-md ring-1 ring-cyan-400/50'
                      : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className={`text-[10px] font-mono font-bold px-1.5 py-0.5 rounded ${
                        ep.method === 'POST' ? 'bg-amber-950 text-amber-300 border border-amber-800' : 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      }`}>
                        {ep.method}
                      </span>
                      <span className="font-mono text-xs text-slate-200 font-bold truncate">
                        {ep.path}
                      </span>
                    </div>
                    {isSelected && <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse"></span>}
                  </div>
                  <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 leading-relaxed">
                    {ep.description}
                  </p>
                </div>
              );
            })}
          </div>

          {/* Live Interactive API Tester (7 cols) */}
          <div className="lg:col-span-7 p-5 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-slate-800">
              <div>
                <div className="flex items-center gap-2">
                  <span className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${
                    selectedEndpoint.method === 'POST' ? 'bg-amber-950 text-amber-300 border border-amber-800' : 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                  }`}>
                    {selectedEndpoint.method}
                  </span>
                  <span className="text-xs font-mono font-bold text-white">
                    https://api.safelytic.com{selectedEndpoint.path}
                  </span>
                </div>
                <p className="text-xs text-slate-300 mt-1 leading-snug">{selectedEndpoint.description}</p>
              </div>

              <button
                onClick={handleRunRequest}
                disabled={isLoading}
                className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow transition-colors flex items-center gap-1.5 shrink-0 self-start sm:self-auto"
              >
                <Play className="w-3.5 h-3.5 fill-white" />
                <span>{isLoading ? 'Executing...' : 'Test Request'}</span>
              </button>
            </div>

            {/* Request Payload Editor */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                  <span>Request Payload:</span>
                  <span className="text-[10px] font-mono text-slate-500">application/json</span>
                </span>
                <button
                  onClick={() => handleCopyCode(requestBody)}
                  className="text-[11px] text-cyan-400 hover:underline flex items-center gap-1 font-mono"
                >
                  {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                  <span>{copied ? 'Copied' : 'Copy JSON'}</span>
                </button>
              </div>
              <textarea
                value={requestBody}
                onChange={(e) => setRequestBody(e.target.value)}
                rows={6}
                className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-xs text-cyan-300 focus:outline-none focus:border-cyan-500 leading-relaxed resize-y"
              />
            </div>

            {/* Response Payload Box */}
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-semibold text-slate-300">Simulated Live Response Output:</span>
                {responseOutput && (
                  <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800 flex items-center gap-1">
                    <CheckCircle2 className="w-3 h-3" />
                    <span>HTTP 200 OK • 38ms</span>
                  </span>
                )}
              </div>
              <pre className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-xs text-slate-200 overflow-x-auto max-h-52 leading-relaxed">
                {responseOutput || '// Click "Test Request" above to simulate live API invocation...'}
              </pre>
            </div>

            {/* Quick Curl Snippet */}
            <div className="p-2.5 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-between text-[11px] font-mono text-slate-400 overflow-x-auto">
              <span className="truncate mr-2">
                curl -X {selectedEndpoint.method} "https://api.safelytic.com{selectedEndpoint.path}" -H "Authorization: Bearer sie_live_..."
              </span>
              <button 
                onClick={() => handleCopyCode(`curl -X ${selectedEndpoint.method} "https://api.safelytic.com${selectedEndpoint.path}" \\\n  -H "Authorization: Bearer sie_live_9f823b1a" \\\n  -H "Content-Type: application/json" \\\n  -d '${requestBody.replace(/'/g, "\\'")}'`)}
                className="text-cyan-400 hover:text-cyan-300 shrink-0 font-sans text-xs underline"
              >
                Copy cURL
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* Interactive Connector Configuration Modal */}
      {selectedConnectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-xl shadow-2xl p-6 space-y-4">
            <div className="flex items-start justify-between gap-4 border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400">
                  <Plug className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-white">
                    Connect {selectedConnectModal}
                  </h3>
                  <p className="text-xs text-slate-400">
                    Automated Bi-directional Enterprise Ingestion Adapter
                  </p>
                </div>
              </div>
              <button
                onClick={() => setSelectedConnectModal(null)}
                className="p-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                <span className="font-bold text-slate-200">1. Authentication & Credentials</span>
                <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                  <div>
                    <label className="text-[10px] text-slate-400 block mb-0.5">Auth Protocol</label>
                    <select className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-slate-200">
                      <option>OAuth 2.0 Client Credentials</option>
                      <option>mTLS Certificate Authentication</option>
                      <option>Secure API Key / Token</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-400 block mb-0.5">Sync Frequency</label>
                    <select className="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-slate-200">
                      <option>Real-time Webhook (Push)</option>
                      <option>Every 15 minutes (Batch Pull)</option>
                      <option>Hourly Incremental Sync</option>
                    </select>
                  </div>
                </div>
              </div>

              <div className="p-3 rounded-lg bg-slate-950 border border-slate-800 space-y-2">
                <span className="font-bold text-slate-200">2. Canonical Schema Mapping</span>
                <p className="text-[11px] text-slate-400">
                  Field values from {selectedConnectModal} are automatically normalized to SIE Canonical Safety Schema definitions with zero loss of lineage.
                </p>
                <div className="p-2 rounded bg-slate-900 font-mono text-[10px] text-cyan-300">
                  source.custom_hazard_code → canonical.Lifting.Precursor.GearDegradation
                </div>
              </div>

              <div className="p-3 rounded-lg bg-emerald-950/30 border border-emerald-800/60 text-emerald-200 flex items-center gap-2">
                <ShieldCheck className="w-4 h-4 text-emerald-400 shrink-0" />
                <span>Zero-Knowledge Tenant Isolation active for this connector.</span>
              </div>
            </div>

            <div className="flex items-center justify-between border-t border-slate-800 pt-3">
              <button
                onClick={() => setSelectedConnectModal(null)}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold"
              >
                Cancel
              </button>
              <button
                onClick={() => {
                  // toggle status
                  const key = selectedConnectModal.toLowerCase().includes('ehs') ? 'ehs' :
                              selectedConnectModal.toLowerCase().includes('erp') ? 'erp' :
                              selectedConnectModal.toLowerCase().includes('cmms') ? 'cmms' :
                              selectedConnectModal.toLowerCase().includes('lms') ? 'lms' :
                              selectedConnectModal.toLowerCase().includes('iot') ? 'iot' : 'warehouse';
                  toggleConnection(key);
                }}
                className="px-4 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-bold flex items-center gap-1.5 shadow"
              >
                <Check className="w-3.5 h-3.5" />
                <span>Save & Authorize Connector</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

