"""Service-layer exceptions for the knowledge domain.

Kept deliberately small: two error shapes cover every rule this milestone
enforces (a referenced entity doesn't exist / isn't visible, or the
request is otherwise structurally invalid — wrong scope, mismatched
tenant, etc.). The API layer (app/api/v1/knowledge.py) maps these to HTTP
404 and 400 respectively, so the service layer stays framework-agnostic
and these rules are enforced the same way whether called from an HTTP
route, a test, or a future ingestion worker.
"""


class KnowledgeNotFoundError(ValueError):
    """A referenced knowledge entity does not exist, or is not visible in
    the given tenant context (the two are indistinguishable by design —
    see TenantScopedRepository.get)."""


class KnowledgeValidationError(ValueError):
    """The request is structurally invalid: inconsistent scope/organization
    combination, a tenant mismatch between a resource and its parent, or a
    missing required tenant context."""
