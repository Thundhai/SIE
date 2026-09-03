import { Info, Plus } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../auth/AuthContext';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import { Button } from '../../components/ui/Button';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { FilterBar } from '../../components/ui/FilterBar';
import { LoadingState } from '../../components/ui/LoadingState';
import { Pagination } from '../../components/ui/Pagination';
import { PriorityBadge } from '../../components/ui/PriorityBadge';
import { SearchInput } from '../../components/ui/SearchInput';
import { Select } from '../../components/ui/Select';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Table, type TableColumn } from '../../components/ui/Table';
import type { AsyncState, Page } from '../../types/common';
import type { ActionPriority, ActionStatus, ActionType, SafetyAction } from '../../types/actions';
import { ActionFormDrawer } from './ActionFormDrawer';
import {
  ACTION_PRIORITY_OPTIONS,
  ACTION_TYPE_OPTIONS,
  ACTION_STATUS_OPTIONS,
  actionStatusLabel,
  actionStatusTone,
  actionTypeLabel,
  toPriorityLevel,
} from './actionStatus';
import type { ActionOption } from './actionRepository';
import { useActionRepository } from './useActionRepository';

const PAGE_SIZE = 10;

/**
 * Actions — "What needs to be corrected, who owns it, and what happens
 * next?" A filterable, searchable, paginated table of safety actions.
 *
 * Backed by the real `GET /api/v1/actions` endpoint (SIE Milestone 17:
 * Actions & Intervention Foundation v0.1) once an organization is
 * established; falls back to `FixtureActionRepository` example data
 * otherwise — see `useActionRepository.ts`. Mirrors `EventsPage`'s own
 * structure exactly (§11: one consistent list-screen pattern across the
 * app, not a bespoke one for Actions).
 */
export function ActionsPage() {
  const repository = useActionRepository();
  const { hasPermission } = useAuth();
  const navigate = useNavigate();
  const canCreate = hasPermission('intervention:manage');

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<ActionStatus | ''>('');
  const [priority, setPriority] = useState<ActionPriority | ''>('');
  const [actionType, setActionType] = useState<ActionType | ''>('');
  const [site, setSite] = useState('');
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<AsyncState<Page<SafetyAction>>>({ status: 'loading' });
  const [siteOptions, setSiteOptions] = useState<ActionOption[]>([]);
  const [isCreateOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    repository.listSiteOptions().then((options) => {
      if (!cancelled) setSiteOptions(options);
    });
    return () => {
      cancelled = true;
    };
  }, [repository]);

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading' });
    repository
      .list({
        page,
        pageSize: PAGE_SIZE,
        search: search || undefined,
        status: status || undefined,
        priority: priority || undefined,
        actionType: actionType || undefined,
        site: site || undefined,
      })
      .then((result) => {
        if (!cancelled) setState({ status: 'success', data: result });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load actions.' });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repository, page, search, status, priority, actionType, site, reloadToken]);

  const hasActiveFilters = Boolean(search || status || priority || actionType || site);

  const columns: TableColumn<SafetyAction>[] = [
    {
      key: 'action',
      header: 'Action',
      render: (row) => (
        <div>
          <p className="font-medium text-text-primary">{row.title}</p>
          <p className="text-xs text-text-muted">{actionTypeLabel(row.actionType)}</p>
        </div>
      ),
    },
    { key: 'priority', header: 'Priority', render: (row) => <PriorityBadge priority={toPriorityLevel(row.priority)} /> },
    { key: 'status', header: 'Status', render: (row) => <StatusBadge tone={actionStatusTone(row.status)} label={actionStatusLabel(row.status)} /> },
    { key: 'owner', header: 'Owner', render: (row) => row.ownerName ?? 'Unassigned' },
    {
      key: 'due',
      header: 'Due date',
      render: (row) => (row.dueDate ? new Date(row.dueDate).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) : '—'),
    },
    {
      key: 'source',
      header: 'Source',
      // Human-readable, never the raw source_event_id UUID (SIE Milestone
      // 18 corrective patch, §2A) — the id itself is still the real
      // routing target on Action Detail's own "View source event" link
      // (ActionDetailPage.tsx), not fabricated or hidden, just not shown
      // here as a primary label.
      render: (row) => (row.sourceEventId ? 'Linked event' : '—'),
    },
    {
      key: 'updated',
      header: 'Updated',
      render: (row) => new Date(row.updatedAt).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }),
    },
  ];

  return (
    <PageContainer>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-text-primary">Actions</h1>
          <p className="mt-1 text-sm text-text-secondary">
            Track what needs to be corrected, who owns it, and what happens next.
          </p>
        </div>
        {canCreate && (
          <Button onClick={() => setCreateOpen(true)}>
            <Plus className="h-4 w-4" aria-hidden="true" />
            Create action
          </Button>
        )}
      </div>

      {repository.isFixtureBacked && (
        <div className="flex items-start gap-2 rounded-md border border-informational/30 bg-informational-surface px-3 py-2.5 text-sm text-informational">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            Showing example action data. No development identity is configured, or it could not be resolved against
            the backend — see <code>docs/FRONTEND_ARCHITECTURE.md</code>.
          </p>
        </div>
      )}

      <Section title="All actions">
        <FilterBar
          onClear={() => {
            setSearch('');
            setStatus('');
            setPriority('');
            setActionType('');
            setSite('');
            setPage(1);
          }}
          hasActiveFilters={hasActiveFilters}
        >
          <div className="w-64">
            <SearchInput
              label="Search actions"
              placeholder="Search by title, description, or reference"
              value={search}
              onChange={(event) => {
                setSearch(event.target.value);
                setPage(1);
              }}
              onClear={() => {
                setSearch('');
                setPage(1);
              }}
            />
          </div>
          <div className="w-44">
            <Select
              label="Status"
              options={[{ value: '', label: 'All statuses' }, ...ACTION_STATUS_OPTIONS]}
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as ActionStatus | '');
                setPage(1);
              }}
            />
          </div>
          <div className="w-40">
            <Select
              label="Priority"
              options={[{ value: '', label: 'All priorities' }, ...ACTION_PRIORITY_OPTIONS]}
              value={priority}
              onChange={(event) => {
                setPriority(event.target.value as ActionPriority | '');
                setPage(1);
              }}
            />
          </div>
          <div className="w-44">
            <Select
              label="Action type"
              options={[{ value: '', label: 'All types' }, ...ACTION_TYPE_OPTIONS]}
              value={actionType}
              onChange={(event) => {
                setActionType(event.target.value as ActionType | '');
                setPage(1);
              }}
            />
          </div>
          <div className="w-48">
            <Select
              label="Site"
              options={[{ value: '', label: 'All sites' }, ...siteOptions]}
              value={site}
              onChange={(event) => {
                setSite(event.target.value);
                setPage(1);
              }}
            />
          </div>
        </FilterBar>

        {state.status === 'loading' && <LoadingState label="Loading actions…" />}

        {state.status === 'error' && (
          <ErrorState description={state.message} onRetry={() => setReloadToken((token) => token + 1)} />
        )}

        {state.status === 'success' && state.data.items.length === 0 && (
          <EmptyState title="No actions match your filters" description="Try adjusting or clearing your filters." />
        )}

        {state.status === 'success' && state.data.items.length > 0 && (
          <>
            <Table
              columns={columns}
              rows={state.data.items}
              getRowKey={(row) => row.id}
              onRowClick={(row) => navigate(`/actions/${row.id}`)}
              caption="Safety actions"
            />
            <Pagination page={state.data.page} pageSize={state.data.pageSize} total={state.data.total} onPageChange={setPage} />
          </>
        )}
      </Section>

      <ActionFormDrawer
        isOpen={isCreateOpen}
        onClose={() => setCreateOpen(false)}
        mode="create"
        onSaved={(action) => {
          setReloadToken((token) => token + 1);
          navigate(`/actions/${action.id}`);
        }}
      />
    </PageContainer>
  );
}
