import type { StatusTone } from '../../types/common';
import { formatCanonicalLabel } from '../events/eventStatus';

/**
 * Plain-language presentation for Knowledge's governed vocabularies —
 * following `administrationLabels.ts`'s own precedent: map known values,
 * fall back to `formatCanonicalLabel()` for anything unmapped, never
 * hide or coerce a value.
 */

// --- Verification status (VerificationStatus) ---------------------------------------------------

const VERIFICATION_STATUS_LABEL: Record<string, string> = {
  PENDING: 'Pending',
  UNDER_REVIEW: 'Under review',
  VERIFIED: 'Verified',
  REJECTED: 'Rejected',
  EXPIRED: 'Expired',
  SUPERSEDED: 'Superseded',
};

const VERIFICATION_STATUS_TONE: Record<string, StatusTone> = {
  PENDING: 'neutral',
  UNDER_REVIEW: 'informational',
  VERIFIED: 'success',
  REJECTED: 'critical',
  EXPIRED: 'warning',
  SUPERSEDED: 'warning',
};

export function verificationStatusLabel(value: string): string {
  return VERIFICATION_STATUS_LABEL[value] ?? formatCanonicalLabel(value);
}

export function verificationStatusTone(value: string): StatusTone {
  return VERIFICATION_STATUS_TONE[value] ?? 'neutral';
}

// --- Scope (GLOBAL | ORGANIZATION) ---------------------------------------------------------------

export function scopeLabel(value: string): string {
  return value === 'GLOBAL' ? 'Global' : value === 'ORGANIZATION' ? 'Organization' : formatCanonicalLabel(value);
}

export function scopeTone(value: string): StatusTone {
  return value === 'GLOBAL' ? 'informational' : 'neutral';
}

// --- Relevance (bucketed similarity label — never called "confidence") --------------------------

const RELEVANCE_TONE: Record<string, StatusTone> = {
  HIGH: 'success',
  MODERATE: 'informational',
  LOW: 'neutral',
};

export function relevanceLabel(value: string): string {
  return formatCanonicalLabel(value);
}

export function relevanceTone(value: string): StatusTone {
  return RELEVANCE_TONE[value] ?? 'neutral';
}

// --- Extraction quality (QualityStatus) -----------------------------------------------------------

const QUALITY_STATUS_TONE: Record<string, StatusTone> = {
  HIGH: 'success',
  MEDIUM: 'informational',
  LOW: 'warning',
  INSUFFICIENT: 'critical',
};

export function qualityStatusLabel(value: string): string {
  return formatCanonicalLabel(value);
}

export function qualityStatusTone(value: string): StatusTone {
  return QUALITY_STATUS_TONE[value] ?? 'neutral';
}

// --- Extraction method (ExtractionMethod) ---------------------------------------------------------

const EXTRACTION_METHOD_LABEL: Record<string, string> = {
  TEXT_EXTRACTION: 'Text extraction',
  STRUCTURED_PARSE: 'Structured parse',
  OCR: 'OCR',
  NONE: 'None',
};

export function extractionMethodLabel(value: string): string {
  return EXTRACTION_METHOD_LABEL[value] ?? formatCanonicalLabel(value);
}

// --- Document-version ingestion status (IngestionStatus) --------------------------------------

const INGESTION_STATUS_LABEL: Record<string, string> = {
  RECEIVED: 'Received',
  PROCESSING: 'Processing',
  PROCESSED: 'Processed',
  FAILED: 'Failed',
  ARCHIVED: 'Archived',
};

const INGESTION_STATUS_TONE: Record<string, StatusTone> = {
  RECEIVED: 'neutral',
  PROCESSING: 'informational',
  PROCESSED: 'success',
  FAILED: 'critical',
  ARCHIVED: 'neutral',
};

export function ingestionStatusLabel(value: string): string {
  return INGESTION_STATUS_LABEL[value] ?? formatCanonicalLabel(value);
}

export function ingestionStatusTone(value: string): StatusTone {
  return INGESTION_STATUS_TONE[value] ?? 'neutral';
}

// --- Upload outcome: extraction status (ExtractionStatus) --------------------------------------

const EXTRACTION_STATUS_LABEL: Record<string, string> = {
  PENDING: 'Pending',
  SUCCEEDED: 'Succeeded',
  PARTIAL: 'Partial',
  FAILED: 'Failed',
};

const EXTRACTION_STATUS_TONE: Record<string, StatusTone> = {
  PENDING: 'neutral',
  SUCCEEDED: 'success',
  PARTIAL: 'warning',
  FAILED: 'critical',
};

export function extractionStatusLabel(value: string): string {
  return EXTRACTION_STATUS_LABEL[value] ?? formatCanonicalLabel(value);
}

export function extractionStatusTone(value: string): StatusTone {
  return EXTRACTION_STATUS_TONE[value] ?? 'neutral';
}
