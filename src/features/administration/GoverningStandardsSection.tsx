import { useCallback, useEffect, useState } from 'react';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { LoadingState } from '../../components/ui/LoadingState';
import { StatusBadge } from '../../components/ui/StatusBadge';
import {
  listActiveGoverningStandards,
  listAvailableGoverningStandards,
  listGoverningStandardHistory,
  type ActiveGoverningStandard,
  type GoverningStandard,
  type OrganizationGoverningStandardEntry,
} from '../../services/api/administration';
import type { AsyncState } from '../../types/common';
import { RetireGoverningStandardDialog } from './RetireGoverningStandardDialog';
import { SelectGoverningStandardDrawer } from './SelectGoverningStandardDrawer';
import { selectionStatusLabel, selectionStatusTone, standardTypeLabel, standardVerificationStatusLabel, standardVerificationStatusTone } from './administrationLabels';

export interface GoverningStandardsSectionProps {
  organizationId: string;
}

/**
 * Governing Standards (SIE Milestone 43A). Deliberately keeps AVAILABLE
 * and SELECTED as two separate lists, never merged into one — the
 * architectural distinction the backend itself enforces: "available does
 * not mean selected, selected does not automatically mean applicable."
 * No AI-based applicability reasoning exists anywhere here, and none is
 * implied by any label or action.
 */
export function GoverningStandardsSection({ organizationId }: GoverningStandardsSectionProps) {
  const [availableState, setAvailableState] = useState<AsyncState<GoverningStandard[]>>({ status: 'loading' });
  const [activeState, setActiveState] = useState<AsyncState<ActiveGoverningStandard[]>>({ status: 'loading' });
  const [refreshToken, setRefreshToken] = useState(0);

  const [selectingStandard, setSelectingStandard] = useState<GoverningStandard | null>(null);
  const [retiringEntry, setRetiringEntry] = useState<ActiveGoverningStandard | null>(null);

  const [historyVisible, setHistoryVisible] = useState(false);
  const [historyState, setHistoryState] = useState<AsyncState<OrganizationGoverningStandardEntry[]>>({ status: 'loading' });

  useEffect(() => {
    const controller = new AbortController();
    setAvailableState({ status: 'loading' });
    listAvailableGoverningStandards(organizationId, controller.signal)
      .then((result) => setAvailableState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setAvailableState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load available standards.' });
      });
    return () => controller.abort();
  }, [organizationId, refreshToken]);

  useEffect(() => {
    const controller = new AbortController();
    setActiveState({ status: 'loading' });
    listActiveGoverningStandards(organizationId, controller.signal)
      .then((result) => setActiveState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setActiveState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load selected standards.' });
      });
    return () => controller.abort();
  }, [organizationId, refreshToken]);

  const loadHistory = useCallback(() => {
    const controller = new AbortController();
    setHistoryState({ status: 'loading' });
    listGoverningStandardHistory(organizationId, { page: 1, pageSize: 50 }, controller.signal)
      .then((result) => setHistoryState({ status: 'success', data: result.items }))
      .catch((error: unknown) => {
        if (controller.signal.aborted) return;
        setHistoryState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load selection history.' });
      });
    return () => controller.abort();
  }, [organizationId]);

  useEffect(() => {
    if (!historyVisible) return;
    return loadHistory();
  }, [historyVisible, refreshToken, loadHistory]);

  const knownStandardsById = new Map<string, GoverningStandard>();
  if (availableState.status === 'success') {
    for (const standard of availableState.data) knownStandardsById.set(standard.id, standard);
  }
  if (activeState.status === 'success') {
    for (const entry of activeState.data) knownStandardsById.set(entry.standard.id, entry.standard);
  }

  return (
    <>
      <Section
        title="Governing standards — available"
        description="The full catalogue this organization can choose from. Being listed here does not mean it has been selected."
      >
        {availableState.status === 'loading' && <LoadingState label="Loading available standards…" />}
        {availableState.status === 'error' && <ErrorState description={availableState.message} />}
        {availableState.status === 'success' && availableState.data.length === 0 && (
          <EmptyState title="No standards available" description="No global or organization-specific standards are currently in the catalogue." />
        )}
        {availableState.status === 'success' && availableState.data.length > 0 && (
          <div className="grid gap-2">
            {availableState.data.map((standard) => (
              <div key={standard.id} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-border bg-surface p-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-text-primary">{standard.name}</p>
                    <StatusBadge tone={standardVerificationStatusTone(standard.verification_status)} label={standardVerificationStatusLabel(standard.verification_status)} />
                  </div>
                  <p className="mt-1 text-xs text-text-secondary">
                    {standard.issuing_organization} · {standardTypeLabel(standard.standard_type)}
                    {standard.version ? ` · ${standard.version}` : ''}
                  </p>
                </div>
                <Button size="sm" variant="secondary" onClick={() => setSelectingStandard(standard)}>
                  Select
                </Button>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section
        title="Governing standards — selected"
        description="This organization's Active Governing Set: standards explicitly selected and not since retired. Selection does not by itself establish legal applicability."
      >
        {activeState.status === 'loading' && <LoadingState label="Loading selected standards…" />}
        {activeState.status === 'error' && <ErrorState description={activeState.message} />}
        {activeState.status === 'success' && activeState.data.length === 0 && (
          <EmptyState title="No governing standards selected" description="This organization currently has no explicitly selected active governing standards." />
        )}
        {activeState.status === 'success' && activeState.data.length > 0 && (
          <div className="grid gap-2">
            {activeState.data.map((entry) => (
              <div key={entry.selection.id} className="flex flex-wrap items-start justify-between gap-3 rounded-lg border border-border bg-surface p-4">
                <div>
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="text-sm font-medium text-text-primary">{entry.standard.name}</p>
                    <StatusBadge tone={selectionStatusTone(entry.selection.status)} label={selectionStatusLabel(entry.selection.status)} />
                  </div>
                  <p className="mt-1 text-xs text-text-secondary">
                    {entry.standard.issuing_organization} · {standardTypeLabel(entry.standard.standard_type)}
                  </p>
                  {entry.selection.rationale && <p className="mt-1.5 text-xs text-text-secondary">{entry.selection.rationale}</p>}
                </div>
                <Button size="sm" variant="secondary" onClick={() => setRetiringEntry(entry)}>
                  Retire
                </Button>
              </div>
            ))}
          </div>
        )}
      </Section>

      <Section
        title="Selection history"
        description="The raw, append-only selection/retirement log for this organization."
        action={
          <Button size="sm" variant="ghost" onClick={() => setHistoryVisible((visible) => !visible)}>
            {historyVisible ? 'Hide history' : 'View history'}
          </Button>
        }
      >
        {historyVisible && historyState.status === 'loading' && <LoadingState label="Loading history…" />}
        {historyVisible && historyState.status === 'error' && <ErrorState description={historyState.message} />}
        {historyVisible && historyState.status === 'success' && historyState.data.length === 0 && (
          <EmptyState title="No history yet" description="No standard has ever been selected or retired for this organization." />
        )}
        {historyVisible && historyState.status === 'success' && historyState.data.length > 0 && (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[650px] text-left text-sm">
              <thead>
                <tr className="border-b border-border text-xs uppercase tracking-wide text-text-muted">
                  <th className="px-3 py-2">Standard</th>
                  <th className="px-3 py-2">Event</th>
                  <th className="px-3 py-2">Decided</th>
                  <th className="px-3 py-2">Rationale</th>
                </tr>
              </thead>
              <tbody>
                {historyState.data.map((record) => (
                  <tr key={record.id} className="border-b border-border">
                    <td className="px-3 py-3">{knownStandardsById.get(record.standard_id)?.name ?? record.standard_id}</td>
                    <td className="px-3 py-3">
                      <StatusBadge tone={selectionStatusTone(record.status)} label={selectionStatusLabel(record.status)} />
                    </td>
                    <td className="px-3 py-3">{new Date(record.decided_at).toLocaleString(undefined, { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })}</td>
                    <td className="px-3 py-3 text-text-secondary">{record.rationale ?? '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <SelectGoverningStandardDrawer
        isOpen={selectingStandard !== null}
        onClose={() => setSelectingStandard(null)}
        organizationId={organizationId}
        standard={selectingStandard}
        onSelected={() => setRefreshToken((token) => token + 1)}
      />
      <RetireGoverningStandardDialog
        isOpen={retiringEntry !== null}
        onClose={() => setRetiringEntry(null)}
        organizationId={organizationId}
        entry={retiringEntry}
        onRetired={() => setRefreshToken((token) => token + 1)}
      />
    </>
  );
}
