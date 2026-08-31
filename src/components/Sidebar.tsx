import React, { useState } from 'react';
import {
  LayoutDashboard,
  BrainCircuit,
  FileText,
  BookOpen,
  CheckCircle2,
  Database,
  Workflow,
  ShieldAlert,
  GraduationCap,
  Bot,
  Network,
  ShieldCheck,
  ChevronRight,
  ChevronDown,
  Sparkles,
  Layers,
  Cpu,
  Lock,
  BarChart2,
  Activity,
  Sliders,
  Boxes,
  GitBranch
} from 'lucide-react';
import { AppScreen } from '../types';

interface SidebarProps {
  currentScreen: AppScreen;
  onNavigate: (screen: AppScreen) => void;
  collapsed?: boolean;
  onToggleCollapse?: () => void;
}

interface NavCategory {
  title: string;
  items: {
    id: AppScreen;
    label: string;
    icon: React.ElementType;
    badge?: string;
    badgeColor?: string;
  }[];
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentScreen,
  onNavigate,
  collapsed = false,
  onToggleCollapse
}) => {
  const navCategories: NavCategory[] = [
    {
      title: 'Main Intelligence',
      items: [
        {
          id: 'overview',
          label: 'Executive Overview',
          icon: LayoutDashboard
        },
        {
          id: 'intelligence',
          label: 'Intelligence Center',
          icon: BrainCircuit,
          badge: '6 Risks',
          badgeColor: 'bg-red-500/10 text-red-400 border-red-500/20'
        },
        {
          id: 'prediction-detail',
          label: 'Prediction & Causal Graph',
          icon: Activity,
          badge: 'Live',
          badgeColor: 'bg-blue-500/10 text-blue-400 border-blue-500/20'
        }
      ]
    },
    {
      title: 'Knowledge & Verification',
      items: [
        {
          id: 'knowledge-center',
          label: 'Knowledge Repository',
          icon: BookOpen,
          badge: '436 Sources',
          badgeColor: 'bg-blue-500/10 text-blue-400 border-blue-500/20'
        },
        {
          id: 'source-verification',
          label: 'Source Verification',
          icon: CheckCircle2,
          badge: 'Audit',
          badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
        },
        {
          id: 'organization-data',
          label: 'Organization Data',
          icon: Database,
          badge: '94% Q-Score',
          badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
        }
      ]
    },
    {
      title: 'Action & Learning',
      items: [
        {
          id: 'interventions',
          label: 'Intervention Center',
          icon: ShieldAlert,
          badge: '3 Active',
          badgeColor: 'bg-amber-500/10 text-amber-400 border-amber-500/20'
        },
        {
          id: 'outcome-learning',
          label: 'Outcome & Learning',
          icon: BarChart2,
          badge: 'Closed-Loop',
          badgeColor: 'bg-purple-500/10 text-purple-400 border-purple-500/20'
        },
        {
          id: 'intelligence-learning',
          label: 'Intelligence Learning & Improvement',
          icon: Workflow,
          badge: '4 Mechanisms',
          badgeColor: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
        }
      ]
    },
    {
      title: 'Platform & Security',
      items: [
        {
          id: 'assistant',
          label: 'SIE Intelligence Assistant',
          icon: Cpu,
          badge: 'Engine',
          badgeColor: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
        },
        {
          id: 'api-integrations',
          label: 'API & Integrations',
          icon: Network,
          badge: 'v1.4',
          badgeColor: 'bg-slate-800 text-slate-400 border-white/5'
        },
        {
          id: 'canonical-model',
          label: 'Canonical Safety Data Model',
          icon: Boxes,
          badge: 'Schema',
          badgeColor: 'bg-cyan-500/10 text-cyan-400 border-cyan-500/20'
        },
        {
          id: 'governance',
          label: 'Privacy & Governance',
          icon: ShieldCheck,
          badge: 'SOC 2',
          badgeColor: 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
        },
        {
          id: 'settings',
          label: 'Alert Thresholds',
          icon: Sliders,
          badge: 'Custom',
          badgeColor: 'bg-purple-500/10 text-purple-400 border-purple-500/20'
        }
      ]
    }
  ];

  return (
    <aside 
      className={`h-full min-h-screen border-r border-white/5 bg-[#0F1117] flex flex-col shrink-0 transition-all duration-200 select-none z-20 ${
        collapsed ? 'w-16' : 'w-64'
      }`}
    >
      {/* Brand Header */}
      <div className="p-5 border-b border-white/5 flex items-center justify-between shrink-0">
        {!collapsed ? (
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 bg-blue-600 rounded-md flex items-center justify-center text-[10px] font-black text-white shadow-md shadow-blue-600/30">
              SIE
            </div>
            <div>
              <h1 className="text-xs font-bold tracking-tight text-white flex items-center gap-1.5">
                SAFELYTIC ENGINE
              </h1>
              <p className="text-[9px] text-slate-500 font-medium uppercase tracking-widest">
                Intelligence Platform
              </p>
            </div>
          </div>
        ) : (
          <div className="w-7 h-7 mx-auto bg-blue-600 rounded-md flex items-center justify-center text-[10px] font-black text-white">
            SIE
          </div>
        )}
      </div>

      {/* Navigation List */}
      <nav className="flex-1 overflow-y-auto p-3 space-y-5 custom-scrollbar text-[13px]">
        {navCategories.map((category) => (
          <div key={category.title} className="space-y-1">
            {!collapsed && (
              <p className="px-3 mb-1.5 text-[10px] font-semibold text-slate-500 uppercase tracking-wider">
                {category.title}
              </p>
            )}
            
            {category.items.map((item) => {
              const isActive = currentScreen === item.id;
              const Icon = item.icon;

              return (
                <button
                  key={item.id}
                  onClick={() => onNavigate(item.id)}
                  className={`w-full flex items-center gap-3 px-3 py-2 rounded-md text-xs font-medium transition-all group relative ${
                    isActive
                      ? 'bg-blue-600/15 text-blue-400 border border-blue-500/25 shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-white/5 border border-transparent'
                  }`}
                  title={collapsed ? item.label : undefined}
                >
                  <Icon className={`w-4 h-4 shrink-0 transition-colors ${
                    isActive ? 'text-blue-400' : 'text-slate-500 group-hover:text-slate-300'
                  }`} />

                  {!collapsed && (
                    <>
                      <span className="flex-1 text-left truncate">{item.label}</span>
                      {item.badge && (
                        <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded border ${item.badgeColor || 'bg-slate-800 text-slate-400 border-white/5'}`}>
                          {item.badge}
                        </span>
                      )}
                    </>
                  )}
                </button>
              );
            })}
          </div>
        ))}
      </nav>

      {/* User Profile / Tenant at Bottom */}
      <div className="p-3 border-t border-white/5 shrink-0 bg-[#0F1117]">
        {!collapsed ? (
          <button
            onClick={() => onNavigate('settings')}
            className={`w-full flex items-center gap-3 p-2 rounded-lg transition-all text-left ${
              currentScreen === 'settings'
                ? 'bg-blue-600/15 border border-blue-500/30'
                : 'bg-[#16181D] border border-white/5 hover:border-white/20 hover:bg-white/5'
            }`}
            title="Configure HSE Alert Thresholds & Profile"
          >
            <div className="w-8 h-8 rounded-full bg-blue-950/80 border border-blue-500/30 flex items-center justify-center text-blue-300 text-xs font-bold shrink-0">
              AV
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs font-medium text-white truncate">Dr. Alistair Vance</p>
              <p className="text-[10px] text-slate-500 truncate">HSE Director • CMIOSH</p>
            </div>
            <span className="w-2 h-2 rounded-full bg-emerald-400" title="Tenant Isolated" />
          </button>
        ) : (
          <button 
            onClick={() => onNavigate('settings')}
            className="w-full flex justify-center p-1 hover:bg-white/5 rounded"
            title="Configure Alert Thresholds"
          >
            <div className="w-2 h-2 rounded-full bg-emerald-400" title="System Operational" />
          </button>
        )}
      </div>
    </aside>
  );
};

