import { EmergingRisk, GlobalFilterState, RiskLevel, DataSourceFilter } from '../types';

export const INITIAL_FILTER_STATE: GlobalFilterState = {
  dateRangePreset: '90d',
  customStartDate: '2026-06-01',
  customEndDate: '2026-08-31',
  riskLevels: [], // empty = all active
  dataSources: [], // empty = all active
  searchQuery: '',
  selectedCategory: null
};

// Reference date for simulation: 2026-08-31
const REFERENCE_DATE = new Date('2026-08-31T23:59:59Z');

export function getPresetDateRange(preset: string): { start: Date; end: Date; label: string } {
  const end = new Date(REFERENCE_DATE);
  const start = new Date(REFERENCE_DATE);

  switch (preset) {
    case '7d':
      start.setDate(end.getDate() - 7);
      return { start, end, label: 'Last 7 Days (Aug 24 - Aug 31)' };
    case '30d':
      start.setDate(end.getDate() - 30);
      return { start, end, label: 'Last 30 Days (Aug 01 - Aug 31)' };
    case '90d':
      start.setDate(end.getDate() - 90);
      return { start, end, label: 'Last 90 Days (Jun 02 - Aug 31)' };
    case '180d':
      start.setDate(end.getDate() - 180);
      return { start, end, label: 'Last 180 Days (Mar 04 - Aug 31)' };
    case 'ytd':
      start.setFullYear(2026, 0, 1);
      return { start, end, label: 'Year to Date 2026 (Jan 01 - Aug 31)' };
    case 'custom':
    default:
      return { start, end, label: 'Custom Date Range' };
  }
}

export function isDateWithinFilter(dateStr: string, filter?: GlobalFilterState): boolean {
  if (!dateStr) return true;
  const currentFilter = filter || INITIAL_FILTER_STATE;
  
  let itemDate: Date;
  // Handle formats: '2026-08-28', '12 Aug 2026', '2026-08-28 14:00', etc.
  if (dateStr.includes('-')) {
    itemDate = new Date(dateStr);
  } else {
    itemDate = new Date(dateStr);
  }

  if (isNaN(itemDate.getTime())) return true;

  if (currentFilter.dateRangePreset === 'custom' && currentFilter.customStartDate && currentFilter.customEndDate) {
    const customStart = new Date(`${currentFilter.customStartDate}T00:00:00Z`);
    const customEnd = new Date(`${currentFilter.customEndDate}T23:59:59Z`);
    return itemDate >= customStart && itemDate <= customEnd;
  }

  const { start, end } = getPresetDateRange(currentFilter.dateRangePreset || '90d');
  return itemDate >= start && itemDate <= end;
}

export function filterRisks(risks: EmergingRisk[], filter?: GlobalFilterState): EmergingRisk[] {
  if (!risks || !Array.isArray(risks)) return [];
  const safeFilter: GlobalFilterState = {
    ...INITIAL_FILTER_STATE,
    ...(filter || {})
  };

  return risks.filter(risk => {
    // 1. Search Query Filter
    if (safeFilter.searchQuery && safeFilter.searchQuery.trim()) {
      const q = safeFilter.searchQuery.toLowerCase();
      const matchText = (
        (risk.title && risk.title.toLowerCase().includes(q)) ||
        (risk.category && risk.category.toLowerCase().includes(q)) ||
        (risk.mainDriver && risk.mainDriver.toLowerCase().includes(q)) ||
        (risk.location && risk.location.toLowerCase().includes(q)) ||
        (risk.drivers && risk.drivers.some(d => d.toLowerCase().includes(q)))
      );
      if (!matchText) return false;
    }

    // 2. Category Filter
    if (safeFilter.selectedCategory && risk.category !== safeFilter.selectedCategory) {
      return false;
    }

    // 3. Risk Level Filter (if any specific level selected)
    if (safeFilter.riskLevels && safeFilter.riskLevels.length > 0) {
      if (!safeFilter.riskLevels.includes(risk.level)) {
        return false;
      }
    }

    // 4. Date Range Filter
    if (!isDateWithinFilter(risk.identifiedDate, safeFilter)) {
      return false;
    }

    // 5. Data Sources Filter (if specific sources selected)
    if (safeFilter.dataSources && safeFilter.dataSources.length > 0) {
      const hasMatchingOrgEvidence = risk.organizationEvidence && risk.organizationEvidence.some(ev => {
        if (safeFilter.dataSources.includes('Observation') && ev.type === 'Observation') return true;
        if (safeFilter.dataSources.includes('Near Miss') && ev.type === 'Near Miss') return true;
        if (safeFilter.dataSources.includes('Incident') && (ev.type as string) === 'Incident') return true;
        if (safeFilter.dataSources.includes('Audit Finding') && (ev.type === 'Audit Finding' || ev.type === 'Inspection Defect')) return true;
        if (safeFilter.dataSources.includes('Permit Exception') && ev.type === 'Permit Exception') return true;
        return false;
      });

      const hasMatchingExtEvidence = (
        safeFilter.dataSources.includes('External Standard') &&
        risk.externalEvidence &&
        risk.externalEvidence.length > 0
      );

      const hasMatchingIoTEvidence = (
        safeFilter.dataSources.includes('IoT Telemetry') &&
        (risk.category === 'Process Safety' || risk.category === 'Lifting Operations' || (risk.mainDriver && (risk.mainDriver.toLowerCase().includes('telematics') || risk.mainDriver.toLowerCase().includes('sensor'))))
      );

      if (!hasMatchingOrgEvidence && !hasMatchingExtEvidence && !hasMatchingIoTEvidence) {
        return false;
      }
    }

    return true;
  });
}

export function filterTrendData(
  trendData: Array<{ day: string; date: string; overall: number; lifting: number; vehicle: number; processSafety: number; height: number }>,
  filter?: GlobalFilterState
) {
  if (!trendData || !Array.isArray(trendData)) return [];
  const safeFilter: GlobalFilterState = {
    ...INITIAL_FILTER_STATE,
    ...(filter || {})
  };

  // Slice or downsample trend points based on timeframe preset
  if (safeFilter.dateRangePreset === '7d') {
    return trendData.slice(-3); // last ~7-10 days
  } else if (safeFilter.dateRangePreset === '30d') {
    return trendData.slice(-5); // last 30-40 days
  } else if (safeFilter.dateRangePreset === '180d' || safeFilter.dateRangePreset === 'ytd') {
    // Return full trend sequence
    return trendData;
  }
  // default 90d: return full array
  return trendData;
}
