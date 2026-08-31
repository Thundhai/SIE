"""Reusable, tenant-scoped repository base class.

`TenantScopedRepository` is the one place that knows how to read or write
an organization-owned table, and it makes tenant scoping structurally
explicit: every method that touches the database *requires* an
`organization_id` argument and filters by it. There is deliberately no
"get by id only" or "list all" method — a caller cannot accidentally issue
a query that spans organizations, because the method signatures don't
allow it.

Concrete services (SiteService, DataSourceService, ...) subclass this with
their model and Pydantic create-schema type; they inherit create/get/list
for free and can add domain-specific methods on top, still going through
the same organization_id-filtered queries.
"""

import uuid
from typing import Generic, TypeVar

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import Base

ModelType = TypeVar("ModelType", bound=Base)
CreateSchemaType = TypeVar("CreateSchemaType", bound=BaseModel)


class TenantScopedRepository(Generic[ModelType, CreateSchemaType]):
    def __init__(self, model: type[ModelType]) -> None:
        self.model = model

    def create(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        obj_in: CreateSchemaType,
    ) -> ModelType:
        """Create a row explicitly scoped to `organization_id`.

        `organization_id` is a required keyword argument sourced from the
        authenticated request path/context, never from the request body,
        so a caller cannot create a resource under a different tenant.
        """
        data = obj_in.model_dump()
        obj = self.model(organization_id=organization_id, **data)
        db.add(obj)
        db.commit()
        db.refresh(obj)
        return obj

    def get(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        id: uuid.UUID,
    ) -> ModelType | None:
        """Fetch a single row by id, scoped to `organization_id`.

        Filtering on both columns means a valid id belonging to a
        *different* organization returns None rather than the row —
        there is no way to reach another tenant's record even if its id
        is known or guessed.
        """
        stmt = select(self.model).where(
            self.model.id == id,
            self.model.organization_id == organization_id,
        )
        return db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]:
        """List rows scoped to `organization_id`, paginated."""
        stmt = (
            select(self.model)
            .where(self.model.organization_id == organization_id)
            .order_by(self.model.created_at)
            .offset(skip)
            .limit(limit)
        )
        return list(db.execute(stmt).scalars().all())


class NullableTenantScopedRepository(Generic[ModelType]):
    """Read-side repository for tables with a *nullable* `organization_id`.

    This is the knowledge domain's counterpart to `TenantScopedRepository`,
    for tables that can hold either GLOBAL rows (`organization_id IS NULL`)
    or ORGANIZATION-owned rows (`organization_id` set) — KnowledgeSource and
    KnowledgeDocument. The same non-negotiable-signature approach applies:
    every method takes `organization_id` explicitly (defaulting to `None`,
    which means "global"), and the two scopes are never mixed in a single
    query result:

      * `organization_id=None`  -> only global rows (`organization_id IS NULL`)
      * `organization_id=<uuid>` -> only that organization's rows
        (`organization_id == <uuid>`)

    There is no mode that returns both, so an endpoint built on this can't
    accidentally return another tenant's private rows alongside global ones,
    and a caller can't list "everything" in one call.

    Only `get`/`list` live here — creation semantics differ per model in
    this domain (KnowledgeSource validates/derives scope from its own
    input; KnowledgeDocument derives it from its parent source), so `create`
    is left to each concrete service.
    """

    def __init__(self, model: type[ModelType]) -> None:
        self.model = model

    def get(
        self,
        db: Session,
        *,
        id: uuid.UUID,
        organization_id: uuid.UUID | None = None,
    ) -> ModelType | None:
        stmt = select(self.model).where(self.model.id == id)
        if organization_id is None:
            stmt = stmt.where(self.model.organization_id.is_(None))
        else:
            stmt = stmt.where(self.model.organization_id == organization_id)
        return db.execute(stmt).scalar_one_or_none()

    def list(
        self,
        db: Session,
        *,
        organization_id: uuid.UUID | None = None,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ModelType]:
        stmt = select(self.model)
        if organization_id is None:
            stmt = stmt.where(self.model.organization_id.is_(None))
        else:
            stmt = stmt.where(self.model.organization_id == organization_id)
        stmt = stmt.order_by(self.model.created_at).offset(skip).limit(limit)
        return list(db.execute(stmt).scalars().all())

    def get_unscoped(self, db: Session, *, id: uuid.UUID) -> ModelType | None:
        """Fetch a row by id with no tenant filter at all.

        Not tenant-safe to expose directly through an API. This exists
        only for internal server-side resolution — e.g. looking up a
        KnowledgeSource by the id a client supplied so its *actual* scope
        can be determined and then enforced (see
        KnowledgeDocumentService.create), before any tenant-facing data is
        returned to that caller.
        """
        stmt = select(self.model).where(self.model.id == id)
        return db.execute(stmt).scalar_one_or_none()
