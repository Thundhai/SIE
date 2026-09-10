import { describe, expect, it, vi } from 'vitest';
import { ApiError } from '../../services/api/errors';
import { ApiEventRepository } from './apiEventRepository';

vi.mock('../../services/api/events', () => ({
  listEvents: vi.fn(),
  getEvent: vi.fn(),
}));
vi.mock('../../services/api/sites', () => ({
  listSites: vi.fn(),
}));

import { getEvent, listEvents } from '../../services/api/events';
import { listSites } from '../../services/api/sites';

const ORG_ID = 'org-1';

describe('ApiEventRepository', () => {
  it('is not fixture-backed', () => {
    expect(new ApiEventRepository(ORG_ID).isFixtureBacked).toBe(false);
  });

  it('list() maps the real response onto SafetyEventSummary, deriving a title from event_type', async () => {
    vi.mocked(listEvents).mockResolvedValue({
      items: [
        {
          id: 'evt-1',
          event_time: '2026-06-01T00:00:00Z',
          event_type: 'NEAR_MISS',
          event_subtype: 'VEHICLE',
          site_id: 'site-1',
          site_name: 'North Yard',
          status: 'open',
          severity: null,
          source_system: 'SafetyCloud',
          source_record_id: 'REF-1',
          data_quality_status: 'VALID',
        },
      ],
      total: 1,
      page: 1,
      page_size: 25,
    });

    const page = await new ApiEventRepository(ORG_ID).list({ page: 1, pageSize: 25 });

    expect(listEvents).toHaveBeenCalledWith(
      expect.objectContaining({ organizationId: ORG_ID, page: 1, pageSize: 25 }),
    );
    expect(page.total).toBe(1);
    expect(page.items[0]).toMatchObject({
      id: 'evt-1',
      title: 'Near miss',
      eventType: 'NEAR_MISS',
      subtype: 'VEHICLE',
      site: 'North Yard',
      status: 'open',
      sourceSystem: 'SafetyCloud',
    });
  });

  it('list() falls back to honest placeholders for a null site or status, never inventing one', async () => {
    vi.mocked(listEvents).mockResolvedValue({
      items: [
        {
          id: 'evt-2',
          event_time: '2026-06-01T00:00:00Z',
          event_type: 'INCIDENT',
          event_subtype: null,
          site_id: null,
          site_name: null,
          status: null,
          severity: null,
          source_system: 'Manual Entry',
          source_record_id: 'REF-2',
          data_quality_status: 'VALID',
        },
      ],
      total: 1,
      page: 1,
      page_size: 25,
    });

    const page = await new ApiEventRepository(ORG_ID).list({ page: 1, pageSize: 25 });

    expect(page.items[0].site).toBe('Unassigned site');
    expect(page.items[0].status).toBe('Unspecified');
  });

  it('getById() returns the full detail including real provenance', async () => {
    vi.mocked(getEvent).mockResolvedValue({
      id: 'evt-1',
      event_time: '2026-06-01T00:00:00Z',
      event_type: 'INCIDENT',
      event_subtype: null,
      site_id: 'site-1',
      site_name: 'North Yard',
      status: 'open',
      severity: null,
      source_system: 'SafetyCloud',
      source_record_id: 'REF-1',
      data_quality_status: 'VALID',
      organization_id: ORG_ID,
      period_end: null,
      reported_time: null,
      potential_severity: null,
      description: 'A forklift near miss.',
      location: null,
      project: null,
      department: null,
      contractor: null,
      activity: null,
      attributes: {},
      data_quality_issues: null,
      provenance: {
        organization_id: ORG_ID,
        source_system: 'SafetyCloud',
        source_record_id: 'REF-1',
        source_record_version: 'v2',
        source_schema_version: '1.0',
        ingestion_batch_id: 'batch-1',
        ingestion_source_id: 'ds-1',
        data_source_name: 'SafetyCloud Feed',
        ingestion_time: '2026-06-02T00:00:00Z',
        normalization_version: 'normalize-v1',
        schema_version: 'schema-v1',
        correlation_id: 'corr-1',
      },
    });

    const detail = await new ApiEventRepository(ORG_ID).getById('evt-1');

    expect(detail).not.toBeNull();
    expect(detail?.narrative).toBe('A forklift near miss.');
    expect(detail?.finding).toBeNull();
    expect(detail?.evidence).toEqual([]);
    expect(detail?.relatedRecords).toEqual([]);
    expect(detail?.relevantKnowledge).toEqual([]);
    expect(detail?.provenance).toEqual({
      organizationId: ORG_ID,
      sourceSystem: 'SafetyCloud',
      sourceRecordId: 'REF-1',
      sourceRecordVersion: 'v2',
      ingestionBatchId: 'batch-1',
      dataSourceName: 'SafetyCloud Feed',
      ingestionTime: '2026-06-02T00:00:00Z',
      correlationId: 'corr-1',
    });
  });

  it('getById() returns null for a 404 (nonexistent or cross-tenant) rather than throwing', async () => {
    vi.mocked(getEvent).mockRejectedValue(new ApiError('Event not found.', { status: 404 }));

    const detail = await new ApiEventRepository(ORG_ID).getById('does-not-exist');

    expect(detail).toBeNull();
  });

  it('getById() rethrows a non-404 failure rather than silently treating it as not-found', async () => {
    vi.mocked(getEvent).mockRejectedValue(new ApiError('Server error.', { status: 500 }));

    await expect(new ApiEventRepository(ORG_ID).getById('evt-1')).rejects.toThrow('Server error.');
  });

  it('listSiteOptions() maps real sites to id/name option pairs', async () => {
    vi.mocked(listSites).mockResolvedValue([
      { id: 'site-1', name: 'North Yard', location: null, country: null, status: 'active', organization_id: ORG_ID },
    ]);

    const options = await new ApiEventRepository(ORG_ID).listSiteOptions();

    expect(options).toEqual([{ value: 'site-1', label: 'North Yard' }]);
  });
});
