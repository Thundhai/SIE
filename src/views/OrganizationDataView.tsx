import React, { useState } from 'react';
import { 
  Database, 
  CheckCircle2, 
  AlertTriangle, 
  RefreshCw, 
  Layers, 
  Cpu, 
  FileSpreadsheet, 
  Radio, 
  Zap, 
  FileText,
  Activity,
  ArrowRight,
  TrendingUp,
  ShieldCheck,
  Filter,
  Search,
  RotateCcw,
  Calendar
} from 'lucide-react';
import { DataIngestionSource } from '../types';
import { DATA_SOURCES, SAFETY_DATA_METRICS } from '../mockData';

interface OrganizationDataViewProps {
  onOpenEvidence: (evidence: any) => void;
}

export const OrganizationDataView: React.FC<OrganizationDataViewProps> = ({
  onOpenEvidence
}) => {
  const [sources, setSources] = useState<DataIngestionSource[]>(DATA_SOURCES);
  const [isSyncing, setIsSyncing] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedType, setSelectedType] = useState<string>('all');
  const [selectedSeverity, setSelectedSeverity] = useState<string>('all');
  const [selectedTimeframe, setSelectedTimeframe] = useState<string>('90d');

  const handleRefreshSync = () => {
    setIsSyncing(true);
    setTimeout(() => {
      setIsSyncing(false);
    }, 800);
  };

  const rawRecords = [
    { id: 'OBS-1021', type: 'Observation', title: 'Tag line not utilized on 12-ton turbine casing lift', severity: 'High', source: 'Safelytic Mobile App', timestamp: '2026-08-30 14:15', status: 'Ingested & Parsed' },
    { id: 'OBS-1044', type: 'Observation', title: 'Unsafe sling angle exceeding 60-degree envelope', severity: 'Moderate', source: 'Safelytic Mobile App', timestamp: '2026-08-29 11:20', status: 'Ingested & Parsed' },
    { id: 'NM-203', type: 'Near Miss', title: 'Uncontrolled load swing near fuel manifold during gust', severity: 'Critical', source: 'Safelytic Core', timestamp: '2026-08-28 09:45', status: 'Flagged for Model Review' },
    { id: 'INC-089', type: 'Incident', title: 'Hydraulic hose rupture during crane boom extension', severity: 'High', source: 'Incident Reporting Engine', timestamp: '2026-08-24 16:30', status: 'Causal Synthesis Complete' },
    { id: 'INS-409', type: 'Inspection', title: 'Flange B-104 weeping traces detected via soap bubble test', severity: 'High', source: 'SAP ERP Work Order', timestamp: '2026-08-20 08:10', status: 'Ingested & Parsed' },
    { id: 'AUD-302', type: 'Audit', title: 'Permit-to-Work gas test stamp missing at 14:00 check', severity: 'Moderate', source: 'Excel SFTP Sync', timestamp: '2026-08-15 14:00', status: 'Ingested & Parsed' },
    { id: 'IOT-881', type: 'IoT Telemetry', title: 'High vibration alert on primary hoisting gearbox #2', severity: 'Critical', source: 'IoT Telemetry Stream', timestamp: '2026-08-10 22:15', status: 'Ingested & Parsed' },
    { id: 'OBS-0988', type: 'Observation', title: 'Personal fall arrest lanyard anchored below D-ring', severity: 'High', source: 'Safelytic Mobile App', timestamp: '2026-07-28 10:05', status: 'Ingested & Parsed' },
    { id: 'OBS-0941', type: 'Observation', title: 'Scaffolding toe-board dislodged on Platform Deck 3', severity: 'Low', source: 'Safelytic Mobile App', timestamp: '2026-07-15 13:40', status: 'Ingested & Parsed' },
  ];

  // Real-time filtered records
  const filteredRecords = rawRecords.filter(rec => {
    const matchesSearch = searchQuery === '' || 
      rec.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rec.id.toLowerCase().includes(searchQuery.toLowerCase()) ||
      rec.source.toLowerCase().includes(searchQuery.toLowerCase());

    const matchesType = selectedType === 'all' || rec.type.toLowerCase() === selectedType.toLowerCase();
    const matchesSeverity = selectedSeverity === 'all' || rec.severity.toLowerCase() === selectedSeverity.toLowerCase();

    return matchesSearch && matchesType && matchesSeverity;
  });

  return (
    <div className="space-y-6 animate-in fade-in duration-200">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-white/5 pb-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold text-white tracking-tight flex items-center gap-2.5">
              <Database className="w-6 h-6 text-emerald-400" />
              <span>Organization Safety Data</span>
            </h1>
            <span className="text-[11px] font-mono px-2 py-0.5 rounded-full bg-emerald-950/80 text-emerald-300 border border-emerald-800/60">
              6 Active Ingestion Connectors
            </span>
          </div>
          <p className="text-xs sm:text-sm text-slate-400 mt-1 max-w-3xl leading-relaxed">
            Real-time field telemetry, ERP work records, mobile incident reports, and legacy data feeds driving continuous risk intelligence.
          </p>
        </div>

        <button
          onClick={handleRefreshSync}
          disabled={isSyncing}
          className="px-3.5 py-2 rounded-lg bg-[#16181D] hover:bg-white/5 border border-white/10 text-slate-200 text-xs font-semibold transition-colors flex items-center gap-2 shrink-0 shadow-sm"
        >
          <RefreshCw className={`w-4 h-4 text-blue-400 ${isSyncing ? 'animate-spin' : ''}`} />
          <span>{isSyncing ? 'Synchronizing Connectors...' : 'Sync All Feeds'}</span>
        </button>
      </div>

      {/* Hero Quality Score & Operational Volumes */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Overall Quality KPI (4 cols) */}
        <div className="lg:col-span-4 p-6 rounded-xl bg-gradient-to-br from-[#16181D] to-emerald-950/20 border border-emerald-800/50 shadow-xl flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold uppercase tracking-wider text-emerald-300">
                Data Quality Score
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-400 border border-emerald-800">
                Grade A
              </span>
            </div>
            <div className="mt-3 flex items-baseline gap-2">
              <span className="text-4xl font-extrabold text-white font-mono">{SAFETY_DATA_METRICS.dataQualityScore}%</span>
              <span className="text-xs text-emerald-400 font-medium">Valid Schema & Integrity</span>
            </div>
            <p className="text-xs text-slate-300 mt-2 leading-relaxed">
              Synthesized across 1,480,000+ total telemetry events and operational records with active field validation.
            </p>
          </div>

          <div className="space-y-2 mt-4 pt-4 border-t border-white/5 text-xs">
            <div className="flex justify-between text-slate-400">
              <span>Field Completeness:</span>
              <span className="font-mono text-slate-200 font-bold">96.4%</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Timestamp Latency:</span>
              <span className="font-mono text-emerald-400 font-bold">&lt; 1.8s avg</span>
            </div>
            <div className="flex justify-between text-slate-400">
              <span>Duplicate Deduplication:</span>
              <span className="font-mono text-slate-200 font-bold">100% Resolved</span>
            </div>
          </div>
        </div>

        {/* Data Volume Badges (8 cols) */}
        <div className="lg:col-span-8 p-6 rounded-xl bg-[#16181D] border border-white/5 flex flex-col justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Activity className="w-4 h-4 text-blue-400" />
              <span>Safety Record Aggregates (Lagos Operations)</span>
            </h3>
            <p className="text-[11px] text-slate-400 mb-4">Historical and real-time records indexed in the SIE semantic graph</p>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Incidents</span>
                <span className="text-xl font-bold text-slate-100 font-mono mt-0.5 block">{SAFETY_DATA_METRICS.incidentsCount}</span>
                <span className="text-[10px] text-slate-500">Last 90 Days</span>
              </div>
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Near Misses</span>
                <span className="text-xl font-bold text-amber-400 font-mono mt-0.5 block">{SAFETY_DATA_METRICS.nearMissesCount}</span>
                <span className="text-[10px] text-slate-500">2 High-Potential</span>
              </div>
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Observations</span>
                <span className="text-xl font-bold text-blue-400 font-mono mt-0.5 block">{SAFETY_DATA_METRICS.observationsCount}</span>
                <span className="text-[10px] text-slate-500">+14% vs Baseline</span>
              </div>
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Inspections</span>
                <span className="text-xl font-bold text-slate-100 font-mono mt-0.5 block">{SAFETY_DATA_METRICS.inspectionsCount}</span>
                <span className="text-[10px] text-slate-500">100% Completed</span>
              </div>
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Audits</span>
                <span className="text-xl font-bold text-slate-100 font-mono mt-0.5 block">{SAFETY_DATA_METRICS.auditsCount}</span>
                <span className="text-[10px] text-slate-500">Internal & 3rd Party</span>
              </div>
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Training Passports</span>
                <span className="text-xl font-bold text-slate-100 font-mono mt-0.5 block">{SAFETY_DATA_METRICS.trainingRecordsCount}</span>
                <span className="text-[10px] text-amber-400">8 Refresher Gaps</span>
              </div>
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Corrective Actions</span>
                <span className="text-xl font-bold text-slate-100 font-mono mt-0.5 block">{SAFETY_DATA_METRICS.correctiveActionsTotal}</span>
                <span className="text-[10px] text-red-400">14 Overdue</span>
              </div>
              <div className="p-3 rounded-lg bg-[#09090B] border border-white/5">
                <span className="text-[10px] text-slate-400 uppercase tracking-wider block">Active Permits</span>
                <span className="text-xl font-bold text-emerald-400 font-mono mt-0.5 block">{SAFETY_DATA_METRICS.permitsActive}</span>
                <span className="text-[10px] text-slate-500">Hot Work, Lifts, Confined</span>
              </div>
            </div>
          </div>

          <div className="mt-3 pt-2 border-t border-white/5 text-[11px] text-slate-400 flex items-center justify-between">
            <span>Automated Ingestion Protocol: Verified</span>
            <span className="font-mono text-blue-400">Continuous Ingestion Graph</span>
          </div>
        </div>
      </div>

      {/* Ingestion Sources List */}
      <div className="p-6 rounded-xl bg-[#16181D] border border-white/5 space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <Zap className="w-4 h-4 text-blue-400" />
              <span>Data Ingestion Connectors Status</span>
            </h3>
            <p className="text-[11px] text-slate-400">Live connectors extracting and transforming operational data into SIE</p>
          </div>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
            All 6 Feeds Live
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sources.map((src) => (
            <div key={src.id} className="p-4 rounded-lg bg-[#09090B] border border-white/5 space-y-3 flex flex-col justify-between">
              <div>
                <div className="flex items-start justify-between">
                  <div>
                    <span className="text-[10px] font-mono text-blue-400 uppercase font-semibold">{src.type}</span>
                    <h4 className="text-xs font-bold text-white mt-0.5">{src.name}</h4>
                  </div>
                  <span className="flex items-center gap-1 text-[10px] font-mono px-2 py-0.5 rounded bg-emerald-950 text-emerald-300 border border-emerald-800">
                    <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                    Connected
                  </span>
                </div>

                <div className="space-y-1 text-[11px] text-slate-300 mt-3">
                  <div className="flex justify-between">
                    <span className="text-slate-400">Records Processed:</span>
                    <span className="font-mono font-bold text-slate-100">{src.recordsProcessed.toLocaleString()}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Last Sync:</span>
                    <span className="font-mono text-slate-400">{src.lastSync}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-400">Quality Score:</span>
                    <span className="font-mono text-emerald-400 font-bold">{src.dataQualityScore}%</span>
                  </div>
                </div>
              </div>

              <div className="pt-2 border-t border-white/5 text-[10px] text-slate-400 flex items-center justify-between">
                <span className="truncate max-w-[170px]">{src.statusText}</span>
                <span className="font-mono text-blue-400 text-[10px]">OK</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Ingested Records Table with Live Filtering */}
      <div className="p-5 rounded-xl bg-[#16181D] border border-white/5 space-y-4">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
              <FileText className="w-4 h-4 text-blue-400" />
              <span>Ingested Records Filterable Data Table</span>
            </h3>
            <p className="text-[11px] text-slate-400">
              Showing {filteredRecords.length} of {rawRecords.length} records matching filter parameters
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            {/* Search Input */}
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2" />
              <input
                type="text"
                placeholder="Search record text, IDs, sources..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="bg-[#09090B] border border-white/10 rounded-lg pl-8 pr-2.5 py-1.5 text-xs text-slate-100 placeholder-slate-500 focus:outline-none focus:border-blue-500 w-52"
              />
            </div>

            {/* Type Filter */}
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value)}
              className="bg-[#09090B] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
            >
              <option value="all">All Record Types</option>
              <option value="observation">Observations</option>
              <option value="near miss">Near Misses</option>
              <option value="incident">Incidents</option>
              <option value="inspection">Inspections</option>
              <option value="audit">Audits</option>
              <option value="iot telemetry">IoT Telemetry</option>
            </select>

            {/* Severity Filter */}
            <select
              value={selectedSeverity}
              onChange={(e) => setSelectedSeverity(e.target.value)}
              className="bg-[#09090B] border border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-blue-500"
            >
              <option value="all">All Severities</option>
              <option value="critical">Critical</option>
              <option value="high">High</option>
              <option value="moderate">Moderate</option>
              <option value="low">Low</option>
            </select>

            {(searchQuery || selectedType !== 'all' || selectedSeverity !== 'all') && (
              <button
                onClick={() => {
                  setSearchQuery('');
                  setSelectedType('all');
                  setSelectedSeverity('all');
                }}
                className="p-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-slate-400 hover:text-white transition-colors"
                title="Reset table filters"
              >
                <RotateCcw className="w-3.5 h-3.5" />
              </button>
            )}
          </div>
        </div>

        {/* Table */}
        <div className="overflow-x-auto">
          {filteredRecords.length > 0 ? (
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-white/5 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
                  <th className="py-2.5 px-3">Record ID</th>
                  <th className="py-2.5 px-3">Type</th>
                  <th className="py-2.5 px-3">Title / Summary</th>
                  <th className="py-2.5 px-3">Severity</th>
                  <th className="py-2.5 px-3">Source Connector</th>
                  <th className="py-2.5 px-3">Timestamp</th>
                  <th className="py-2.5 px-3 text-right">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5 text-slate-300">
                {filteredRecords.map((rec) => (
                  <tr 
                    key={rec.id} 
                    onClick={() => onOpenEvidence({ id: rec.id, title: rec.title, type: rec.type, severity: rec.severity, date: rec.timestamp, details: `Detailed payload ingested from ${rec.source}` })}
                    className="hover:bg-white/5 transition-colors cursor-pointer group"
                  >
                    <td className="py-2.5 px-3 font-mono font-bold text-blue-400">{rec.id}</td>
                    <td className="py-2.5 px-3 text-slate-300">{rec.type}</td>
                    <td className="py-2.5 px-3 text-slate-200 group-hover:text-blue-300 font-medium max-w-sm truncate">{rec.title}</td>
                    <td className="py-2.5 px-3">
                      <span className={`text-[10px] font-mono px-2 py-0.5 rounded font-bold ${
                        rec.severity === 'Critical' ? 'bg-red-950/70 text-red-300 border border-red-500/70' :
                        rec.severity === 'High' ? 'bg-orange-950/70 text-orange-300 border border-orange-500/70' :
                        rec.severity === 'Moderate' ? 'bg-amber-950/70 text-amber-300 border border-amber-500/70' :
                        'bg-emerald-950/70 text-emerald-300 border border-emerald-500/70'
                      }`}>
                        {rec.severity}
                      </span>
                    </td>
                    <td className="py-2.5 px-3 text-[11px] text-slate-400">{rec.source}</td>
                    <td className="py-2.5 px-3 text-[11px] font-mono text-slate-500">{rec.timestamp}</td>
                    <td className="py-2.5 px-3 text-right">
                      <span className="text-[10px] font-mono text-emerald-400 bg-emerald-950/60 px-2 py-0.5 rounded border border-emerald-800/50">
                        {rec.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="py-12 text-center text-slate-400">
              <Search className="w-8 h-8 mx-auto mb-2 text-slate-600" />
              <div className="text-xs font-semibold text-slate-300">No operational records match filter criteria</div>
              <p className="text-[11px] text-slate-500 mt-1">Try selecting 'All Record Types' or clearing search keywords.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

