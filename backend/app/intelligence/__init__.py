"""SIE Intelligence & Predictive Analytics Foundation v0.1.

    External Systems -> Data Ingestion -> Validation -> Normalization
        -> Canonical Events -> Feature Engineering -> Indicators
        -> Risk Signals -> Future Predictive Models

This is the data-intelligence foundation, not the predictive layer
itself — see `app/intelligence/predictive_model.py`'s module docstring
for exactly what remains before real predictive ML, and the README's
"Intelligence Architecture" section for the full pipeline. **This
milestone does not claim to predict accidents or injuries.** It
establishes the trustworthy analytical foundation (canonical event
model, provenance, temporal integrity, data quality, exposure
normalization, feature engineering, deterministic indicators/signals)
required for future predictive modeling.

  * `enums.py` — the closed vocabularies (see that module for why most
    of the milestone's own domain/subtype examples deliberately stay
    free-form strings instead).
  * `schemas.py` — internal ingestion dataclasses (raw payload,
    validation result, normalized event).
  * `normalization.py` / `validation.py` — milestone items 12/14.
  * `adapters.py` / `ingestion_service.py` — milestone items 8/11/38.
  * `temporal.py` — milestone items 15-16, the anti-leakage choke point
    every other module in this package goes through.
  * `exposure.py` — milestone items 18/51.
  * `features.py` / `indicators.py` — milestone items 19-21.
  * `trends.py` / `anomaly.py` — milestone items 23-24.
  * `signals.py` — milestone item 22.
  * `association.py` — milestone item 26.
  * `sufficiency.py` / `reliability.py` — milestone items 30/32-33.
  * `privacy.py` — milestone item 34.
  * `predictive_model.py` — milestone items 42-44 (interface only).
"""
