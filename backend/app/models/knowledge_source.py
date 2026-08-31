"""KnowledgeSource — the root provenance record for a body of safety knowledge.

A source is either GLOBAL (published knowledge not owned by any tenant —
a regulation, an industry standard, a public safety bulletin) or
ORGANIZATION-scoped (a tenant's own internal procedure, incident report,
or private document set). `organization_id` is nullable specifically to
represent GLOBAL sources; a CHECK constraint makes the GLOBAL/ORGANIZATION
<-> organization_id relationship structurally impossible to get wrong at
the database level, independent of anything the application code does.
"""

import uuid
from datetime import date

from sqlalchemy import CheckConstraint, Date, ForeignKey, Index, String, Text, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin
from app.models.enums import ScopeType, VerificationStatus


class KnowledgeSource(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_sources"
    __table_args__ = (
        CheckConstraint(
            "(scope_type = 'GLOBAL' AND organization_id IS NULL) OR "
            "(scope_type = 'ORGANIZATION' AND organization_id IS NOT NULL)",
            name="ck_knowledge_sources_scope_org_consistency",
        ),
        Index("ix_knowledge_sources_scope_type", "scope_type"),
        Index("ix_knowledge_sources_verification_status", "verification_status"),
    )

    scope_type: Mapped[ScopeType] = mapped_column(
        SAEnum(ScopeType, name="knowledge_scope_type", native_enum=True),
        nullable=False,
    )
    # Nullable by design: NULL for GLOBAL sources, required for ORGANIZATION
    # sources. Enforced by the CHECK constraint above, not just convention.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    publisher: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(100), nullable=False)
    jurisdiction: Mapped[str | None] = mapped_column(String(100), nullable=True)
    industry_sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    authority_level: Mapped[str | None] = mapped_column(String(100), nullable=True)

    verification_status: Mapped[VerificationStatus] = mapped_column(
        SAEnum(VerificationStatus, name="knowledge_verification_status", native_enum=True),
        nullable=False,
        default=VerificationStatus.PENDING,
    )

    external_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    publication_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    review_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    organization: Mapped["Organization | None"] = relationship(  # noqa: F821
        back_populates="knowledge_sources"
    )
    documents: Mapped[list["KnowledgeDocument"]] = relationship(  # noqa: F821
        back_populates="source",
        cascade="all, delete-orphan",
    )

    @property
    def is_global(self) -> bool:
        return self.scope_type == ScopeType.GLOBAL

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<KnowledgeSource id={self.id!s} scope_type={self.scope_type!s} "
            f"organization_id={self.organization_id!s} name={self.name!r}>"
        )
