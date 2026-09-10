import { Info } from 'lucide-react';
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { EmptyState } from '../../components/ui/EmptyState';
import { ErrorState } from '../../components/ui/ErrorState';
import { FilterBar } from '../../components/ui/FilterBar';
import { LoadingState } from '../../components/ui/LoadingState';
import { Pagination } from '../../components/ui/Pagination';
import { SearchInput } from '../../components/ui/SearchInput';
import { Select } from '../../components/ui/Select';
import { StatusBadge } from '../../components/ui/StatusBadge';
import { Table, type TableColumn } from '../../components/ui/Table';
import { PageContainer } from '../../components/layout/PageContainer';
import { Section } from '../../components/layout/Section';
import type { AsyncState, Page } from '../../types/common';
import type { EventStatus, SafetyEventSummary } from '../../types/events';
import { eventStatusLabel, eventStatusTone } from './eventStatus';
import type { SiteOption } from './eventRepository';
import { useEventRepository } from './useEventRepository';

const PAGE_SIZE = 10;

const STATUS_OPTIONS: { value: EventStatus | ''; label: string }[] = [
  { value: '', label: 'All statuses' },
  { value: 'open', label: 'Open' },
  { value: 'under_review', label: 'Under review' },
  { value: 'closed', label: 'Closed' },
  { value: 'quarantined', label: 'Quarantined' },
];

/**
 * Events — "What happened?" A filterable, searchable, paginated table of
 * safety events.
 *
 * Backed by the real `GET /api/v1/events` endpoint (SIE Enterprise Read
 * API & Browser Integration Foundation v0.1) once an organization is
 * established; falls back to `FixtureEventRepository` example data
 * otherwise — see `useEventRepository.ts`. The banner below only renders
 * when the active repository actually is fixture-backed
 * (`repository.isFixtureBacked`), so example data is never presented as
 * live.
 */
export function EventsPage() {
  const repository = useEventRepository();
  const navigate = useNavigate();

  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [status, setStatus] = useState<EventStatus | ''>('');
  const [site, setSite] = useState('');
  const [reloadToken, setReloadToken] = useState(0);
  const [state, setState] = useState<AsyncState<Page<SafetyEventSummary>>>({ status: 'loading' });
  const [siteOptions, setSiteOptions] = useState<SiteOption[]>([]);

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
      .list({ page, pageSize: PAGE_SIZE, search: search || undefined, status: status || undefined, site: site || undefined })
      .then((result) => {
        if (!cancelled) setState({ status: 'success', data: result });
      })
      .catch((error: unknown) => {
        if (!cancelled) {
          setState({ status: 'error', message: error instanceof Error ? error.message : 'Could not load events.' });
        }
      });
    return () => {
      cancelled = true;
    };
  }, [repository, page, search, status, site, reloadToken]);

  const hasActiveFilters = Boolean(search || status || site);

  const columns: TableColumn<SafetyEventSummary>[] = [
    { key: 'date', header: 'Date', render: (row) => new Date(row.date).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) },
    {
      key: 'event',
      header: 'Event',
      render: (row) => (
        <div>
          <p className="font-medium text-text-primary">{row.title}</p>
          <p className="text-xs text-text-muted">
            {row.eventType}
            {row.subtype ? ` · ${row.subtype}` : ''}
          </p>
        </div>
      ),
    },
    { key: 'site', header: 'Site', render: (row) => row.site },
    {
      key: 'status',
      header: 'Status',
      render: (row) => <StatusBadge tone={eventStatusTone(row.status)} label={eventStatusLabel(row.status)} />,
    },
    { key: 'source', header: 'Source', render: (row) => row.sourceSystem },
  ];

  return (
    <PageContainer>
      <div>
        <h1 className="text-xl font-semibold text-navy-900">Events</h1>
        <p className="mt-1 text-sm text-text-secondary">
          A record of safety events across your organization — incidents, observations, and near misses.
        </p>
      </div>

      {repository.isFixtureBacked && (
        <div className="flex items-start gap-2 rounded-md border border-informational/30 bg-informational-surface px-3 py-2.5 text-sm text-informational">
          <Info className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
          <p>
            Showing example event data. No development identity is configured, or it could not be resolved against
            the backend — see <code>docs/FRONTEND_ARCHITECTURE.md</code>.
          </p>
        </div>
      )}

      <Section title="All events">
        <FilterBar
          onClear={() => {
            setSearch('');
            setStatus('');
            setSite('');
            setPage(1);
          }}
          hasActiveFilters={hasActiveFilters}
        >
          <div className="w-64">
            <SearchInput
              label="Search events"
              placeholder="Search by title, type, or site"
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
              options={STATUS_OPTIONS}
              value={status}
              onChange={(event) => {
                setStatus(event.target.value as EventStatus | '');
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

        {state.status === 'loading' && <LoadingState label="Loading events…" />}

        {state.status === 'error' && (
          <ErrorState
            description={state.message}
            onRetry={() => setReloadToken((token) => token + 1)}
          />
        )}

        {state.status === 'success' && state.data.items.length === 0 && (
          <EmptyState title="No events match your filters" description="Try adjusting or clearing your filters." />
        )}

        {state.status === 'success' && state.data.items.length > 0 && (
          <>
            <Table
              columns={columns}
              rows={state.data.items}
              getRowKey={(row) => row.id}
              onRowClick={(row) => navigate(`/events/${row.id}`)}
              caption="Safety events"
            />
            <Pagination page={state.data.page} pageSize={state.data.pageSize} total={state.data.total} onPageChange={setPage} />
          </>
        )}
      </Section>
    </PageContainer>
  );
}
