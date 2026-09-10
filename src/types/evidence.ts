/**
 * Evidence types — SIE is evidence-grounded (§16): every "what SIE
 * found" statement must be traceable to specific supporting records,
 * never presented as free-standing AI output. These types back
 * `InsightPanel`/`EvidenceList`/`EvidenceItem`.
 */

export interface EvidenceRecord {
  /** A short, stable reference code shown to the reader (e.g. "E1") —
   * never a raw database id. */
  reference: string;
  title: string;
  /** e.g. a site or project name — kept generic since this is reused
   * across features. */
  context?: string;
  /** Optional deep link (e.g. to the source event's own detail page). */
  href?: string;
}

export interface DocumentReferenceRecord {
  id: string;
  title: string;
  source: string;
  verificationStatus: 'verified' | 'pending' | 'flagged' | 'rejected';
  href?: string;
}

export interface RelatedRecordItem {
  id: string;
  title: string;
  type: string;
  href?: string;
}
