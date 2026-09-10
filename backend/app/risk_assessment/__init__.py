"""SIE Milestone 25: Enterprise Risk Assessment Foundation v0.1.

    Events -> Indicators -> Trends -> Patterns -> Anomalies -> Associations
        -> enterprise-risk-v1
        ------------------------------------------------------------
        ENTERPRISE RISK ASSESSMENT
        ------------------------------------------------------------
        -> Risk areas / hazards -> Findings & evidence -> Likelihood
        -> Consequence -> Inherent risk -> Controls -> Residual risk
        -> Actions

**This is a structured risk-assessment layer sitting *above*
`enterprise-risk-v1`, not a replacement for it (item 1's own
architectural rule).** `app/intelligence/risk_score.py` is not modified
by this milestone at all — it remains exactly what it was: one
analytical input a human assessor may consult, surfaced read-only via
`intelligence_context` (`app/risk_assessment/candidate_generation.py`),
never the source of an inherent- or residual-risk rating.

  * `risk_matrix.py` — the deterministic
    likelihood × consequence -> inherent/residual risk calculation
    (items 9-10, 13), `risk-assessment-v1`.
  * `candidate_generation.py` — deterministic, evidence-linked candidate
    findings surfaced from the existing Milestone 22-24 intelligence
    engines (items 14-15, 26-27) — never an approved risk rating on
    their own (item 27's own architectural boundary, this package's
    hardest rule).

See `app/models/risk_assessment.py` for the persisted entities and
`app/services/risk_assessment_service.py` for the lifecycle/authorization/
audit write path.
"""
