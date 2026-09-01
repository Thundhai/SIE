"""Data sufficiency — milestone item 30. A single, deterministic,
documented rule (never a judgment call each caller makes independently):
a site with three days of data must never be compared, unqualified,
against one with three years of data.

**The exact thresholds** (`app/core/config.py`, both documented *initial*
defaults, the same "not scientifically validated" caveat every other
threshold in this codebase carries):

  * `event_count >= settings.INTELLIGENCE_SUFFICIENT_DATA_MIN_EVENTS`
    (default 10) -> `SUFFICIENT_DATA`
  * `event_count >= settings.INTELLIGENCE_LIMITED_DATA_MIN_EVENTS`
    (default 3) -> `LIMITED_DATA`
  * otherwise -> `INSUFFICIENT_DATA`
"""

from __future__ import annotations

from app.core.config import settings
from app.intelligence.enums import DataSufficiency


def classify_data_sufficiency(event_count: int) -> DataSufficiency:
    if event_count >= settings.INTELLIGENCE_SUFFICIENT_DATA_MIN_EVENTS:
        return DataSufficiency.SUFFICIENT_DATA
    if event_count >= settings.INTELLIGENCE_LIMITED_DATA_MIN_EVENTS:
        return DataSufficiency.LIMITED_DATA
    return DataSufficiency.INSUFFICIENT_DATA
