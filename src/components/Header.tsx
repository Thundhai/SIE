import React, { useState } from 'react';
import { 
  Building2, 
  MapPin, 
  Calendar, 
  Search, 
  Bell, 
  ShieldCheck, 
  ChevronDown, 
  Sparkles,
  SlidersHorizontal,
  Activity,
  Sliders
} from 'lucide-react';
import { SITES_LIST } from '../mockData';
import { AppScreen } from '../types';

interface HeaderProps {
  currentScreen?: AppScreen;
  onNavigate?: (screen: AppScreen) => void;
  currentSite: string;
  onSiteChange: (site: string) => void;
  currentTimeRange?: string;
  onTimeRangeChange?: (range: string) => void;
  timePeriod?: string;
  onTimePeriodChange?: (period: string) => void;
  onOpenSearch: () => void;
  onOpenNotifications: () => void;
  unreadNotificationsCount?: number;
  unreadCount?: number;
}

export const Header: React.FC<HeaderProps> = ({
  currentScreen,
  onNavigate,
  currentSite,
  onSiteChange,
  currentTimeRange,
  onTimeRangeChange,
  timePeriod = 'Last 90 Days',
  onTimePeriodChange,
  onOpenSearch,
  onOpenNotifications,
  unreadNotificationsCount,
  unreadCount
}) => {
  const [showOrgMenu, setShowOrgMenu] = useState(false);
  const [showSiteMenu, setShowSiteMenu] = useState(false);
  const [showTimeMenu, setShowTimeMenu] = useState(false);
  const [showProfileMenu, setShowProfileMenu] = useState(false);

  const activeTimePeriod = currentTimeRange || timePeriod;
  const setTimePeriod = onTimeRangeChange || onTimePeriodChange || (() => {});
  const activeUnreadCount = unreadNotificationsCount ?? unreadCount ?? 0;

  const timeOptions = ['Last 30 Days', 'Last 90 Days', 'Last 180 Days', 'Year to Date (2026)'];

  return (
    <header className="h-16 border-b border-white/5 bg-[#09090B]/90 backdrop-blur-md px-6 flex items-center justify-between gap-4 sticky top-0 z-30">
      {/* Left: Organization & Site Selectors with Elegant Dark structure */}
      <div className="flex items-center gap-6 flex-wrap">
        {/* Org Selector */}
        <div className="relative">
          <div className="flex flex-col">
            <span className="text-[10px] text-slate-500 uppercase font-bold tracking-widest leading-none mb-1">
              Organization
            </span>
            <button
              onClick={() => {
                setShowOrgMenu(!showOrgMenu);
                setShowSiteMenu(false);
                setShowTimeMenu(false);
                setShowProfileMenu(false);
              }}
              className="flex items-center gap-1.5 text-xs sm:text-sm font-semibold text-white hover:text-slate-200 transition-colors"
            >
              <span>Demo Energy & Engineering Ltd.</span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
            </button>
          </div>

          {showOrgMenu && (
            <div className="absolute left-0 mt-2 w-72 rounded-lg bg-[#16181D] border border-white/10 shadow-2xl p-3 z-50 animate-in fade-in zoom-in-95">
              <div className="text-[10px] font-semibold text-slate-400 border-b border-white/5 pb-1.5 uppercase tracking-wider">
                Enterprise Tenant
              </div>
              <div className="mt-2 p-2.5 rounded-md bg-blue-600/10 border border-blue-500/20">
                <p className="text-xs font-semibold text-blue-300">Demo Energy & Engineering Ltd.</p>
                <p className="text-[11px] text-slate-400 mt-0.5">Tier: Enterprise Intelligence (Global)</p>
                <div className="flex items-center gap-2 mt-2 text-[10px] text-blue-400">
                  <ShieldCheck className="w-3.5 h-3.5" /> Tenant Isolation: Verified Active
                </div>
              </div>
              <div className="mt-2 text-[10px] text-slate-500 font-mono flex items-center justify-between pt-1">
                <span>Tenant ID:</span>
                <span className="text-slate-300">ORG-ENG-4921-NG</span>
              </div>
            </div>
          )}
        </div>

        {/* Subtle Divider */}
        <div className="h-8 w-[1px] bg-white/5 hidden sm:block" />

        {/* Site Selector */}
        <div className="relative">
          <div className="flex flex-col">
            <span className="text-[10px] text-slate-500 uppercase font-bold tracking-widest leading-none mb-1">
              Operational Site
            </span>
            <button
              onClick={() => {
                setShowSiteMenu(!showSiteMenu);
                setShowOrgMenu(false);
                setShowTimeMenu(false);
                setShowProfileMenu(false);
              }}
              className="flex items-center gap-1.5 text-xs sm:text-sm font-semibold text-blue-400 hover:text-blue-300 transition-colors"
            >
              <span>{currentSite}</span>
              <ChevronDown className="w-3.5 h-3.5 text-slate-500" />
            </button>
          </div>

          {showSiteMenu && (
            <div className="absolute left-0 mt-2 w-64 rounded-lg bg-[#16181D] border border-white/10 shadow-2xl p-2 z-50 animate-in fade-in zoom-in-95">
              <div className="text-[10px] font-semibold text-slate-400 border-b border-white/5 pb-1.5 px-2 uppercase tracking-wider">
                Operational Sites
              </div>
              {SITES_LIST.map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    onSiteChange(s.name);
                    setShowSiteMenu(false);
                  }}
                  className={`w-full text-left p-2 rounded-md my-1 text-xs transition-colors flex items-start justify-between ${
                    currentSite === s.name
                      ? 'bg-blue-600/15 text-blue-300 font-medium border border-blue-500/30'
                      : 'hover:bg-white/5 text-slate-300'
                  }`}
                >
                  <div>
                    <div className="font-medium text-slate-100">{s.name}</div>
                    <div className="text-[10px] text-slate-500">{s.type}</div>
                  </div>
                  <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-[#09090B] text-slate-400 border border-white/5">
                    Score {s.riskScore}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Right: Timeframe, Search, Notifications, Profile */}
      <div className="flex items-center gap-3">
        {/* Time Period Selector Badge */}
        <div className="relative hidden md:block">
          <button
            onClick={() => {
              setShowTimeMenu(!showTimeMenu);
              setShowOrgMenu(false);
              setShowSiteMenu(false);
              setShowProfileMenu(false);
            }}
            className="flex items-center gap-2 bg-white/5 px-3 py-1.5 rounded border border-white/5 text-xs text-slate-300 hover:bg-white/10 transition-colors"
          >
            <Calendar className="w-3.5 h-3.5 text-slate-400" />
            <span>{activeTimePeriod}</span>
            <ChevronDown className="w-3 h-3 text-slate-500" />
          </button>

          {showTimeMenu && (
            <div className="absolute right-0 mt-1.5 w-48 rounded-lg bg-[#16181D] border border-white/10 shadow-2xl p-1.5 z-50">
              <div className="px-2 py-1 text-[10px] font-semibold text-slate-500 border-b border-white/5 uppercase tracking-wider">
                Analysis Window
              </div>
              {timeOptions.map((opt) => (
                <button
                  key={opt}
                  onClick={() => {
                    setTimePeriod(opt);
                    setShowTimeMenu(false);
                  }}
                  className={`w-full text-left px-2.5 py-1.5 rounded text-xs transition-colors my-0.5 ${
                    activeTimePeriod === opt
                      ? 'bg-blue-600/20 text-blue-300 font-medium'
                      : 'hover:bg-white/5 text-slate-300'
                  }`}
                >
                  {opt}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Global Search Button */}
        <button
          onClick={onOpenSearch}
          className="flex items-center gap-2 px-3 py-1.5 rounded bg-white/5 hover:bg-white/10 border border-white/5 text-slate-400 hover:text-slate-200 text-xs transition-colors group"
          title="Search intelligence, evidence, documents, risks (Cmd+K)"
        >
          <Search className="w-3.5 h-3.5 text-slate-500 group-hover:text-blue-400" />
          <span className="hidden sm:inline">Search...</span>
          <kbd className="hidden sm:inline-block font-mono text-[10px] bg-black/40 px-1.5 py-0.5 rounded border border-white/10 text-slate-500">
            ⌘K
          </kbd>
        </button>

        {/* Alert Thresholds Settings Button */}
        {onNavigate && (
          <button
            onClick={() => onNavigate('settings')}
            className={`w-8 h-8 flex items-center justify-center rounded-full border transition-colors ${
              currentScreen === 'settings'
                ? 'bg-blue-600/20 text-blue-400 border-blue-500/30'
                : 'bg-white/5 hover:bg-white/10 border-white/5 text-slate-300 hover:text-white'
            }`}
            title="Configure Risk Probability & Confidence Thresholds"
          >
            <Sliders className="w-4 h-4 text-slate-400 hover:text-blue-400" />
          </button>
        )}

        {/* Notifications Icon Button */}
        <button
          onClick={onOpenNotifications}
          className="relative w-8 h-8 flex items-center justify-center rounded-full bg-white/5 hover:bg-white/10 border border-white/5 text-slate-300 hover:text-white transition-colors"
          title="Alerts & Signals"
        >
          <Bell className="w-4 h-4 text-slate-400" />
          {activeUnreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 w-3.5 h-3.5 rounded-full bg-red-500 text-white font-mono text-[9px] flex items-center justify-center font-bold">
              {activeUnreadCount}
            </span>
          )}
        </button>
      </div>
    </header>
  );
};

