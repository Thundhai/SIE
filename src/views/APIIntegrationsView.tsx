import React, { useState } from 'react';
import { 
  Code2, 
  Copy, 
  Check, 
  Play, 
  Key, 
  Layers, 
  Workflow, 
  Send, 
  Server, 
  Cpu, 
  ShieldCheck,
  ExternalLink,
  ChevronRight
} from 'lucide-react';
import { API_ENDPOINTS } from '../mockData';
import { ApiEndpoint } from '../types';

export const APIIntegrationsView: React.FC = () => {
  const [endpoints] = useState<ApiEndpoint[]>(API_ENDPOINTS);
  const [selectedEndpoint, setSelectedEndpoint] = useState<ApiEndpoint>(API_ENDPOINTS[0]);
  const [requestBody, setRequestBody] = useState(selectedEndpoint.sampleRequest);
  const [responseOutput, setResponseOutput] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

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
    }, 450);
  };

  const handleCopyCode = (text: string) => {
    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-800 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <Code2 className="w-6 h-6 text-cyan-400" />
              <span>API & Enterprise Integrations</span>
            </h1>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-cyan-950 text-cyan-300 border border-cyan-800">
              API-First Safety Brain
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Connect SIE directly to Safelytic Core, SAP/Oracle ERP, IoT sensors, Permit-to-Work systems, or custom internal dashboards.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <div className="p-2 px-3 rounded-lg bg-slate-900 border border-slate-800 text-xs font-mono text-cyan-300 flex items-center gap-2">
            <Key className="w-3.5 h-3.5 text-cyan-400" />
            <span>Key: sie_live_9f82...3b1a</span>
          </div>
        </div>
      </div>

      {/* System Architecture Flow Diagram */}
      <div className="p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Workflow className="w-4 h-4 text-cyan-400" />
              <span>API Topology: The Intelligence Brain for Enterprise Systems</span>
            </h3>
            <p className="text-[11px] text-slate-400">Bidirectional REST & Webhook data flow architecture</p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
            Latency: ~42ms
          </span>
        </div>

        {/* Visual 3-Node Connected Diagram */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2">
          <div className="p-4 rounded-lg bg-slate-950/80 border border-slate-800 space-y-2 text-center">
            <div className="w-10 h-10 mx-auto rounded-lg bg-cyan-950 border border-cyan-800 text-cyan-400 flex items-center justify-center">
              <Server className="w-5 h-5" />
            </div>
            <h4 className="text-xs font-bold text-white">Client & Operational Systems</h4>
            <p className="text-[11px] text-slate-400 leading-snug">
              Safelytic App, SAP ERP, SCADA/IoT, SFTP Data Lakes, Mobile Incident Apps
            </p>
          </div>

          <div className="p-4 rounded-lg bg-cyan-950/40 border border-cyan-700/60 space-y-2 text-center relative">
            <div className="w-10 h-10 mx-auto rounded-lg bg-cyan-900 border border-cyan-600 text-white flex items-center justify-center">
              <Code2 className="w-5 h-5 text-cyan-200" />
            </div>
            <h4 className="text-xs font-bold text-white">SIE REST & Webhook Gateway</h4>
            <p className="text-[11px] text-cyan-200 leading-snug">
              JSON API v1 • HMAC-SHA256 Signed Webhooks • Real-time Ingestion Pipelines
            </p>
          </div>

          <div className="p-4 rounded-lg bg-slate-950/80 border border-slate-800 space-y-2 text-center">
            <div className="w-10 h-10 mx-auto rounded-lg bg-purple-950 border border-purple-800 text-purple-400 flex items-center justify-center">
              <Cpu className="w-5 h-5" />
            </div>
            <h4 className="text-xs font-bold text-white">SIE Intelligence Core</h4>
            <p className="text-[11px] text-slate-400 leading-snug">
              Causal Bayesian Graph • 436 Verified Standards • Prescriptive Intervention Engine
            </p>
          </div>
        </div>
      </div>

      {/* Interactive API Tester & Endpoints Workbench */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Endpoints Sidebar (4 cols) */}
        <div className="lg:col-span-4 space-y-2.5">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-400 block px-1">
            Available Endpoints:
          </span>
          {endpoints.map((ep) => {
            const isSelected = selectedEndpoint.path === ep.path;
            return (
              <div
                key={ep.path}
                onClick={() => handleSelectEndpoint(ep)}
                className={`p-3.5 rounded-lg border cursor-pointer transition-all ${
                  isSelected
                    ? 'bg-cyan-950/50 border-cyan-500 shadow-md ring-1 ring-cyan-500/50'
                    : 'bg-slate-900/90 border-slate-800 hover:border-slate-700'
                }`}
              >
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
                <p className="text-[11px] text-slate-400 mt-1.5 line-clamp-2">
                  {ep.description}
                </p>
              </div>
            );
          })}
        </div>

        {/* Live Interactive API Tester (8 cols) */}
        <div className="lg:col-span-8 p-6 rounded-xl bg-slate-900/90 border border-slate-800 space-y-4">
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
              <p className="text-xs text-slate-400 mt-1">{selectedEndpoint.description}</p>
            </div>

            <button
              onClick={handleRunRequest}
              disabled={isLoading}
              className="px-4 py-2 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold shadow transition-colors flex items-center gap-1.5 shrink-0"
            >
              <Play className="w-3.5 h-3.5 fill-white" />
              <span>{isLoading ? 'Executing...' : 'Send Test Request'}</span>
            </button>
          </div>

          {/* Request Payload Editor */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-slate-300">Request Body (JSON Payload):</span>
              <button
                onClick={() => handleCopyCode(requestBody)}
                className="text-[11px] text-cyan-400 hover:underline flex items-center gap-1"
              >
                {copied ? <Check className="w-3 h-3" /> : <Copy className="w-3 h-3" />}
                <span>Copy JSON</span>
              </button>
            </div>
            <textarea
              value={requestBody}
              onChange={(e) => setRequestBody(e.target.value)}
              rows={7}
              className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-xs text-cyan-300 focus:outline-none focus:border-cyan-500 leading-relaxed"
            />
          </div>

          {/* Response Payload Box */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-semibold text-slate-300">Response (Live JSON Output):</span>
              {responseOutput && (
                <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950 px-2 py-0.5 rounded border border-emerald-800">
                  HTTP 200 OK • 38ms
                </span>
              )}
            </div>
            <pre className="w-full bg-slate-950 border border-slate-800 rounded-lg p-3 font-mono text-xs text-slate-200 overflow-x-auto max-h-60 leading-relaxed">
              {responseOutput || '// Click "Send Test Request" above to simulate live API invocation...'}
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};
