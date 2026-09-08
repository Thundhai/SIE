"""SQLAlchemy ORM models.

Importing this package registers every model on `Base.metadata`, which is
required both for Alembic autogenerate and for `Base.metadata.create_all`
in tests.
"""

from app.models.api_client import ApiClient
from app.models.audit_log import AuditLog
from app.models.base import Base
from app.models.data_source import DataSource
from app.models.dataset_version import DatasetVersion
from app.models.embedding import KnowledgeChunkEmbedding
from app.models.enterprise_ingestion_batch import EnterpriseIngestionBatch
from app.models.enterprise_ingestion_record import EnterpriseIngestionRecord
from app.models.feature_snapshot import FeatureSnapshot
from app.models.hse_expert_review import HseExpertReview
from app.models.idempotency_key import IdempotencyKey
from app.models.identity import Identity
from app.models.ingested_file import IngestedFile
from app.models.ingestion_job import IngestionJob
from app.models.intelligence_decision import IntelligenceDecision
from app.models.knowledge_chunk import KnowledgeChunk
from app.models.knowledge_document import KnowledgeDocument
from app.models.knowledge_document_version import KnowledgeDocumentVersion
from app.models.knowledge_source import KnowledgeSource
from app.models.model_approval import ModelApproval
from app.models.model_registry_entry import ModelRegistryEntry
from app.models.model_review_flag import ModelReviewFlag
from app.models.ontology_concept import OntologyConcept
from app.models.organization import Organization
from app.models.organization_membership import OrganizationMembership
from app.models.prediction import Prediction
from app.models.prediction_outcome import PredictionOutcome
from app.models.project import Project
from app.models.project_site import ProjectSite
from app.models.project_site_history import ProjectSiteHistory
from app.models.risk_assessment import (
    RiskAssessment,
    RiskAssessmentControl,
    RiskAssessmentFinding,
    RiskAssessmentFindingEvidence,
)
from app.models.risk_assessment_control_evidence import RiskAssessmentControlEvidence
from app.models.risk_assessment_finding_action import RiskAssessmentFindingAction
from app.models.risk_assessment_history import RiskAssessmentHistory
from app.models.safety_action import SafetyAction
from app.models.safety_action_history import SafetyActionHistory
from app.models.safety_event import SafetyEvent
from app.models.safety_event_project_attribution_history import SafetyEventProjectAttributionHistory
from app.models.site import Site
from app.models.terminology_mapping_decision import TerminologyMappingDecision
from app.models.user import User

__all__ = [
    "ApiClient",
    "AuditLog",
    "Base",
    "DataSource",
    "DatasetVersion",
    "EnterpriseIngestionBatch",
    "EnterpriseIngestionRecord",
    "FeatureSnapshot",
    "HseExpertReview",
    "IdempotencyKey",
    "Identity",
    "IngestedFile",
    "IngestionJob",
    "IntelligenceDecision",
    "KnowledgeChunk",
    "KnowledgeChunkEmbedding",
    "KnowledgeDocument",
    "KnowledgeDocumentVersion",
    "KnowledgeSource",
    "ModelApproval",
    "ModelRegistryEntry",
    "ModelReviewFlag",
    "OntologyConcept",
    "Organization",
    "OrganizationMembership",
    "Prediction",
    "PredictionOutcome",
    "Project",
    "ProjectSite",
    "ProjectSiteHistory",
    "RiskAssessment",
    "RiskAssessmentControl",
    "RiskAssessmentControlEvidence",
    "RiskAssessmentFinding",
    "RiskAssessmentFindingAction",
    "RiskAssessmentFindingEvidence",
    "RiskAssessmentHistory",
    "SafetyAction",
    "SafetyActionHistory",
    "SafetyEvent",
    "SafetyEventProjectAttributionHistory",
    "Site",
    "TerminologyMappingDecision",
    "User",
]
