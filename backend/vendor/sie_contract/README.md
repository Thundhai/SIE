# sie-contract

The versioned Shared Contract between **Public SIE** (`Thundhai/SIE`) and
the **Private Commercial Core** (`Thundhai/SIE-Commercial-Core`). This
package is deliberately small, deliberately boring, and deliberately
independent: it contains DTOs (data shapes) and small closed
enumerations only, never an algorithm, an internal model, or
orchestration logic.

> **Read this before adding anything here.** The single question that
> decides whether a field belongs in this package: *does an external
> consumer need to know **what** happened, or is this **how** Commercial
> Core decided it happened?* The first belongs here. The second never
> does. See "What this package must never contain" below.

## Ownership

This package is owned and versioned by the **Private Commercial Core**
repository (it lives at `sie-contract/` at that repository's root) but
its content is a joint interface: a breaking change here is a breaking
change for Public SIE too, not a unilateral Commercial Core decision.
Treat any change to an existing type's required fields as a
coordination event across both repositories, not a routine commit.

## Independence (why this is its own package, not `app/schemas/*` copied)

- **Zero Commercial Core internal imports.** Nothing under
  `src/sie_contract/` imports from `app.intelligence`, `app.predictions`,
  `app.rag`, `app.models`, or any other private implementation module.
  `tests/test_private_model_isolation.py` proves this by static AST
  inspection, not by convention alone.
- **Zero Public SIE runtime dependency.** This package does not import
  anything from a `Thundhai/SIE` checkout, does not need one present to
  install, build, or test, and carries no dependency on that
  repository's Git history (see the parent repository's CI, which
  installs and tests this package in isolation on every run).
  `pip install ./sie-contract` (or the equivalent from a built wheel)
  works standalone.
- **Not a copy of `app/schemas/*`.** Every type in this package was
  designed from scratch against the question above, not copy-pasted
  from an existing internal schema and trimmed. Several internal
  schemas (`PredictionRead`, `OrganizationalMemoryRead`, the deep
  `FieldIntelligenceContext` sample lists) have **no** analog here at
  all — see `../docs/BOUNDARY_DECISIONS.md` for exactly which fields
  were deliberately left out and why.

## What this package must never contain

- Proprietary algorithms, scoring formulas, or feature weights.
- Internal ranking/priority *calculation* (a `priority` **value** —
  e.g. `"HIGH"` — is fine; the arithmetic that produced it is not).
- Ontology/terminology governance internals or resolution state.
- Evidence-selection or evidence-sufficiency policy.
- Organizational-memory retrieval mechanics or learning-loop internals.
- Predictive-model internals (probabilities, risk scores, feature
  contributions, model IDs/versions) — see
  `../docs/BOUNDARY_DECISIONS.md` §Predictions for why this entire
  category is deferred, not merely trimmed.
- SQLAlchemy models, ORM relationships, or any database-shaped type.
- Raw internal database identifiers used for internal linkage
  (`entity_ids`, `event_ids` on an internal evidence object) — where a
  consumer needs to reference something, it gets an opaque
  `EvidenceReference`, never the internal foreign key shape.

## Versioning strategy

- **Semantic versioning**, tracked in `VERSION` (single source of
  truth; `sie_contract.__version__` reads it at import time — see
  `tests/test_version.py`).
- **0.x is pre-stable.** Every type in `0.1.0` is a first draft; minor
  version bumps within `0.x` may still add fields (additive only) or
  narrow documentation. A breaking change to an existing `0.x` type
  (removing/renaming a required field, changing a field's meaning)
  requires a **minor** bump in the `0.x` series and a note in this
  README's changelog section until `1.0.0` is declared stable.
- **From `1.0.0` onward**: additive changes (new optional field, new
  DTO, new enum value on an explicitly "open vocabulary" field) are
  **minor** version bumps. Any change that could break an existing,
  correctly-written consumer (removing a field, making an optional
  field required, narrowing an enum, changing a field's type or
  semantics) is a **major** version bump.
- **Deprecation policy**: a field or type is marked deprecated in its
  docstring for at least one minor version before removal, with the
  removal called out explicitly in that version's changelog entry
  here. Nothing is silently removed.
- **Open vs. closed vocabularies.** Some string fields (e.g.
  `AttentionItemDTO.category`, `DecisionReferenceDTO.decision_type`)
  are deliberately typed as `str`, not a Python `Enum`, and documented
  as *open vocabularies*: Commercial Core may introduce a new value
  without that being a breaking contract change, because a well-written
  consumer must already handle an unrecognized value gracefully (display
  it verbatim, do not crash). Fields typed as a closed `Enum`
  (`AttentionPriority`, `DecisionActorType`, `IntelligenceOverallStatus`)
  are a genuine closed set — adding a new member to those **is** a
  breaking change and requires a major/minor bump per the rule above.

## Compatibility expectations for consumers

- Never construct a DTO by positional args across a version bump —
  always by keyword, so an additive new field never breaks a caller.
- Never assume a `str`-typed "open vocabulary" field is exhaustively
  enumerable; always have a documented fallback for an unrecognized
  value.
- `as_of` / `generated_at` semantics (see `common.py`) are always UTC,
  always explicit — a DTO never implies "current" without stating a
  timestamp.
- Every DTO that represents an organization-scoped fact carries its own
  `organization_id`; a consumer must never assume the tenant context of
  the surrounding call implicitly applies to a nested object.

## Tenant/organization scope rules

See `tenancy.py` and `../docs/BOUNDARY_DECISIONS.md` §Tenant/security
boundary for the full rationale. Summary: `TenantContext` represents an
**already-authorized** result — the organization a caller is allowed to
act as, resolved by whichever side of the boundary performed
authentication/authorization — never a raw, unverified value taken at
face value from request input. A machine caller's `organization_id` is
fixed at credential-issuance time and is never request-overridable; a
human caller's is resolved through the existing authorization service.
This package does not change that mechanism — it only gives the
already-resolved result a stable external shape.

## Error semantics

See `errors.py`. Every error crossing the boundary is an
`ErrorResponse` with a stable `error_code` (an open vocabulary, like
the category fields above), a human-readable `message`, an optional
`request_id` for cross-system correlation, and an explicit `retryable`
flag — never a bare exception, a stack trace, or an HTTP status code
alone.

## Package layout

```
sie-contract/
    VERSION                 single source of truth for the package version
    README.md               this file
    pyproject.toml          standalone install metadata (pydantic only)
    src/sie_contract/
        __init__.py          public exports + __version__
        version.py           VERSION file reader
        errors.py            ErrorResponse, ErrorCode semantics
        tenancy.py            TenantContext, ActorType
        common.py             EvidenceReference, AsOfWindow, Page[T]
        attention.py           AttentionPriority, AttentionItemDTO, AttentionResultDTO, ...
        analytics.py            AnalyticsSummaryDTO, AnalyticsTrendDTO, AnalyticsSignalsResultDTO, ...
        intelligence_context.py IntelligenceContextSummaryDTO, category status
        decisions.py            DecisionReferenceDTO, DecisionActorType
        rag.py                  CitationReferenceDTO, RAGAnswerDTO
        status.py               IntelligenceStatusDTO, IntelligenceOverallStatus
    tests/                    contract compatibility tests (see Phase 10
                               of the M43-IP-02 milestone report) -- run
                               standalone, no Commercial Core app/ import
```

## What is deliberately NOT in v0.1.0

Documented in full in `../docs/BOUNDARY_DECISIONS.md`, summarized here:
predictions (any field), organizational memory content, learning-loop
governance internals, deep `FieldIntelligenceContext` sample data
(finding/action samples, predictive signal values), and risk-assessment
scoring detail. Each is either genuinely private (proprietary model
output) or left `REVIEW_REQUIRED` pending a deliberate future design
pass — never included "because the internal schema already exists."

## Changelog

### 0.3.0 — Analytics (Task 01D-F2)
Additive: `AnalyticsSummaryDTO`, `AnalyticsTrendDTO`/`AnalyticsTrendPeriodDTO`,
`AnalyticsSignalsResultDTO`/`AnalyticsSignalDTO`, plus their supporting
enums (`AnalyticsDataSufficiency`, `AnalyticsIndicatorCategory`,
`AnalyticsSignalSeverity`, `AnalyticsTrendDirection`). No existing DTO
changed.

### 0.1.0 — initial contract (M43-IP-02)
Initial draft: `TenantContext`, `ErrorResponse`, `EvidenceReference`,
`AsOfWindow`, `Page[T]`, `AttentionItemDTO`/`AttentionResultDTO`,
`IntelligenceContextSummaryDTO`, `DecisionReferenceDTO`,
`CitationReferenceDTO`/`RAGAnswerDTO`, `IntelligenceStatusDTO`. Pre-1.0:
expect additive and clarifying changes; nothing here is a production
integration yet.
