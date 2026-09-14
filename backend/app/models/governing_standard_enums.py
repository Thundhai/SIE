"""Enums for SIE Milestone 43A: Organizational Standards & Governance
Foundation.

Deliberately does NOT introduce a parallel scope-type or
verification-status vocabulary: `GoverningStandard` reuses
`app.models.enums.ScopeType` (GLOBAL/ORGANIZATION -- identical meaning to
`KnowledgeSource`'s own field) and `app.models.enums.VerificationStatus`
(the same governance-maturity vocabulary already used for a
`KnowledgeSource`) verbatim. Only the two genuinely new concepts this
milestone introduces get new enums here.
"""

from enum import Enum


class GoverningStandardType(str, Enum):
    """What *kind* of standard/framework a catalogue entry is -- not a
    judgment about its authority or applicability (that is
    `VerificationStatus` and, in a later milestone, applicability
    reasoning). `OTHER` exists precisely so the catalogue is never
    blocked on a taxonomy gap (M43A spec §1: "the architecture must
    allow additional standards to be added later") -- a new type of
    standard never needs a schema migration just to be entered into the
    catalogue, only a considered choice of the closest existing bucket.
    """

    REGULATORY = "REGULATORY"
    INTERNATIONAL_STANDARD = "INTERNATIONAL_STANDARD"
    INDUSTRY_GUIDANCE = "INDUSTRY_GUIDANCE"
    MANAGEMENT_FRAMEWORK = "MANAGEMENT_FRAMEWORK"
    CLIENT_STANDARD = "CLIENT_STANDARD"
    ORGANIZATION_SPECIFIC = "ORGANIZATION_SPECIFIC"
    OTHER = "OTHER"


class OrganizationGoverningStandardStatus(str, Enum):
    """One event in the append-only `OrganizationGoverningStandard` log
    (M43A spec §2, §12) -- mirrors the `ACTIVE`/`RETRACTED` shape of
    `OrganizationalMemoryGovernanceStatus` (SIE Milestone 40) exactly,
    renamed to this domain's own vocabulary. `SELECTED` records "this
    organization has explicitly adopted this standard as governing their
    operations" (M43A spec §4's "Selected" concept -- never inferred from
    mere catalogue availability, M43A spec's own "Core principle").
    `RETIRED` records the organization explicitly withdrawing a
    previously-selected standard. There is no third "currently governing"
    state stored anywhere -- that is always *resolved*, never persisted,
    by `app.services.governing_standard_service.resolve_current_selection()`
    taking the most recent row for an (organization, standard) pair.
    """

    SELECTED = "SELECTED"
    RETIRED = "RETIRED"


__all__ = ["GoverningStandardType", "OrganizationGoverningStandardStatus"]
