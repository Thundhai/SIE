"""KnowledgeDocument — one document belonging to a KnowledgeSource.

`organization_id` here is not an independent tenant assignment: it is
always derived server-side from the parent source's own `organization_id`
(see app/services/knowledge_document_service.py) and is denormalized onto
this table only so document queries can be tenant-filtered directly,
without a join back to knowledge_sources on every request. The same
GLOBAL/ORGANIZATION CHECK constraint used on KnowledgeSource is applied
here too, so the denormalized copy can never itself drift into an
inconsistent state.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class KnowledgeDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "knowledge_documents"
    __table_args__ = (
        Index("ix_knowledge_documents_organization_id", "organization_id"),
    )

    source_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("knowledge_sources.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Denormalized from source.organization_id at creation time — see the
    # module docstring. NULL exactly when the source is GLOBAL.
    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    document_type: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    language: Mapped[str | None] = mapped_column(String(20), nullable=True)
    external_document_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Points at the version currently considered authoritative. Nullable
    # because a document can exist before any version has been ingested.
    # use_alter breaks the circular FK cycle with knowledge_document_versions
    # (whose rows point back at this table) so both tables can be created in
    # a single migration / a single Base.metadata.create_all() call.
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey(
            "knowledge_document_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_knowledge_documents_current_version_id",
        ),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(String(50), nullable=False, default="active")

    source: Mapped["KnowledgeSource"] = relationship(back_populates="documents")  # noqa: F821
    organization: Mapped["Organization | None"] = relationship()  # noqa: F821
    versions: Mapped[list["KnowledgeDocumentVersion"]] = relationship(  # noqa: F821
        back_populates="document",
        cascade="all, delete-orphan",
        foreign_keys="KnowledgeDocumentVersion.document_id",
    )
    current_version: Mapped["KnowledgeDocumentVersion | None"] = relationship(  # noqa: F821
        foreign_keys=[current_version_id],
        post_update=True,
    )

    @property
    def is_global(self) -> bool:
        return self.organization_id is None

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<KnowledgeDocument id={self.id!s} source_id={self.source_id!s} "
            f"organization_id={self.organization_id!s} title={self.title!r}>"
        )
