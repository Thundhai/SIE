/**
 * Outcome Verification & Evidence service — SIE Milestone 38/42. Thin
 * typed wrappers around the real, already-built, already-tested backend
 * endpoints (`backend/app/api/v1/intelligence_outcomes.py`'s
 * `POST /intelligence/outcomes/{outcome_id}/verifications` and
 * `GET /intelligence/outcomes/{outcome_id}/verification-state`).
 * Mirrors `IntelligenceOutcomeVerificationCreate`/
 * `IntelligenceOutcomeVerificationStateRead`
 * (`backend/app/schemas/intelligence_outcome_verification.py`)
 * field-for-field.
 *
 * **A governance judgment about the recorded outcome, never a second
 * opinion on the original decision, and never itself an act of
 * learning.** A verification always references an existing
 * `IntelligenceOutcome` by `outcome_id`; this module never creates,
 * infers, or mutates an outcome or a decision, and never triggers
 * anything beyond persisting the verification record itself.
 *
 * `learning_eligibility` is deliberately **not** exposed by this module
 * (the backend's own `verification-state` response always includes it,
 * but the deterministic learning-eligibility gate is a downstream
 * concern for a future, separately-scoped milestone — SIE Milestone 42
 * spec: "Do NOT implement Learning Candidate UI"). `evidence_evaluation`
 * *is* exposed: it directly answers a question the reviewer needs
 * answered right here ("why might VERIFIED be rejected?"), computed
 * entirely server-side, never re-derived on this side.
 */
import { apiRequest } from './client';

/** Mirrors `app/models/intelligence_outcome_verification_enums.py::IntelligenceOutcomeVerificationStatus` — the real, closed, three-value vocabulary. */
export type IntelligenceOutcomeVerificationStatus = 'VERIFIED' | 'INSUFFICIENT_EVIDENCE' | 'DISPUTED';

/** Mirrors `app/models/intelligence_outcome_verification_enums.py::EvidenceStatus`. */
export type EvidenceStatus = 'NO_EVIDENCE' | 'INVALID_EVIDENCE' | 'INSUFFICIENT_EVIDENCE' | 'VALID_EVIDENCE';

export interface IntelligenceOutcomeVerification {
  id: string;
  organization_id: string;
  outcome_id: string;
  status: IntelligenceOutcomeVerificationStatus;
  rationale: string;
  verified_at: string;
  verified_by_user_id: string | null;
  verified_by_api_client_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface EvidenceEvaluation {
  evidence_count: number;
  valid_evidence_count: number;
  invalid_evidence_count: number;
  future_evidence_count: number;
  evidence_status: EvidenceStatus;
  evidence_eligible_for_verification: boolean;
  reasons: string[];
}

/** The full `verification-state` response shape, kept for contract
 * fidelity even though `learning_eligibility` is never rendered by this
 * module's own consumers — see module docstring. */
export interface VerificationState {
  outcome_id: string;
  current_verification: IntelligenceOutcomeVerification | null;
  evidence_evaluation: EvidenceEvaluation;
  learning_eligibility: { eligible: boolean; reasons: string[] };
}

export interface CreateVerificationInput {
  status: IntelligenceOutcomeVerificationStatus;
  rationale: string;
  /** The real-world instant a human actually reviewed the outcome/
   * evidence — never "now" supplied blindly; must not be in the future
   * (backend-enforced, `reject_future_verified_at()`). */
  verifiedAt: string;
}

export function getVerificationState(
  params: { organizationId: string; outcomeId: string },
  signal?: AbortSignal,
): Promise<VerificationState> {
  return apiRequest<VerificationState>(`/intelligence/outcomes/${params.outcomeId}/verification-state`, {
    query: { organization_id: params.organizationId },
    signal,
  });
}

export function createVerification(
  params: { organizationId: string; outcomeId: string; input: CreateVerificationInput },
  idempotencyKey: string,
  signal?: AbortSignal,
): Promise<IntelligenceOutcomeVerification> {
  const { organizationId, outcomeId, input } = params;
  return apiRequest<IntelligenceOutcomeVerification>(`/intelligence/outcomes/${outcomeId}/verifications`, {
    method: 'POST',
    query: { organization_id: organizationId },
    headers: { 'Idempotency-Key': idempotencyKey },
    body: {
      status: input.status,
      rationale: input.rationale,
      verified_at: input.verifiedAt,
    },
    signal,
  });
}
