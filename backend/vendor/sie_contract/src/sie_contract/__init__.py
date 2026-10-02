"""sie-contract -- the versioned Shared Contract between Public SIE
(Thundhai/SIE) and the Private Commercial Core
(Thundhai/SIE-Commercial-Core). See README.md for the full contract
documentation, versioning policy, and what this package must never
contain.
"""

from sie_contract.analytics import (
    AnalyticsDataSufficiency,
    AnalyticsIndicatorCategory,
    AnalyticsIndicatorDTO,
    AnalyticsSignalDTO,
    AnalyticsSignalSeverity,
    AnalyticsSignalsResultDTO,
    AnalyticsSummaryDTO,
    AnalyticsTrendDTO,
    AnalyticsTrendDirection,
    AnalyticsTrendPeriodDTO,
)
from sie_contract.attention import (
    AttentionCategoryStatus,
    AttentionCategoryStatusDTO,
    AttentionItemDTO,
    AttentionPriority,
    AttentionResultDTO,
    AttentionScope,
)
from sie_contract.common import AsOfWindow, EvidenceReference, EvidenceType, Page
from sie_contract.decisions import DecisionReferenceDTO
from sie_contract.errors import ErrorResponse, KnownErrorCode
from sie_contract.intelligence_context import (
    IntelligenceContextCategoryStatus,
    IntelligenceContextCategoryStatusDTO,
    IntelligenceContextSummaryDTO,
)
from sie_contract.rag import CitationReferenceDTO, RAGAnswerDTO
from sie_contract.status import IntelligenceOverallStatus, IntelligenceStatusDTO
from sie_contract.tenancy import ActorType, ServiceIdentity, TenantContext
from sie_contract.version import __version__

__all__ = [
    "__version__",
    # tenancy
    "ActorType",
    "ServiceIdentity",
    "TenantContext",
    # errors
    "ErrorResponse",
    "KnownErrorCode",
    # common
    "AsOfWindow",
    "EvidenceReference",
    "EvidenceType",
    "Page",
    # attention
    "AttentionCategoryStatus",
    "AttentionCategoryStatusDTO",
    "AttentionItemDTO",
    "AttentionPriority",
    "AttentionResultDTO",
    "AttentionScope",
    # analytics
    "AnalyticsDataSufficiency",
    "AnalyticsIndicatorCategory",
    "AnalyticsIndicatorDTO",
    "AnalyticsSignalDTO",
    "AnalyticsSignalSeverity",
    "AnalyticsSignalsResultDTO",
    "AnalyticsSummaryDTO",
    "AnalyticsTrendDTO",
    "AnalyticsTrendDirection",
    "AnalyticsTrendPeriodDTO",
    # intelligence context
    "IntelligenceContextCategoryStatus",
    "IntelligenceContextCategoryStatusDTO",
    "IntelligenceContextSummaryDTO",
    # decisions
    "DecisionReferenceDTO",
    # rag
    "CitationReferenceDTO",
    "RAGAnswerDTO",
    # status
    "IntelligenceOverallStatus",
    "IntelligenceStatusDTO",
]
