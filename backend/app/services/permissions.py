"""Roles and permissions.

This is the authorization *vocabulary* — what a role is, what a
permission is, and the initial mapping between them — kept deliberately
separate from `authorization_service.py` (which is the code that
*evaluates* that vocabulary against a user and an organization) and from
`tenant_context.py` (which packages the result for a request).

Two different flexibility choices are made deliberately here:

* `Permission` is a closed, small enum. Permissions are meant to be a
  stable vocabulary that route/service code checks against by name; adding
  one is a deliberate, reviewed code change, not routine data entry — so a
  Python enum (not a database table) is the right amount of structure for
  "don't implement hundreds of permissions."
* `OrganizationRole` is also an enum here (for validation and for keys in
  `ROLE_PERMISSIONS`), but `OrganizationMembership.role` — the database
  column — is a plain string, not a native DB enum. Roles are expected to
  evolve (a new role, a renamed one) faster than permissions do, and doing
  that as a data/config change rather than a schema migration is the
  "flexible role model" the milestone asks for. `permissions_for_role()`
  is the one place that has to stay in sync with `OrganizationRole`.

`PLATFORM_ADMIN` is intentionally *not* a member of `OrganizationRole`: a
platform administrator is a property of a `User`
(`User.platform_role`), not of one organization membership — see
app/models/user.py and app/services/authorization_service.py.
"""

from enum import Enum

PLATFORM_ADMIN = "PLATFORM_ADMIN"
"""The one valid value of `User.platform_role` today. Kept as a plain
string constant rather than a single-member enum — see
app/models/user.py for why the field itself is a free-form nullable
string."""


class OrganizationRole(str, Enum):
    """Roles assignable via `OrganizationMembership.role`.

    Deliberately does not include PLATFORM_ADMIN — platform-wide
    administration is not scoped to any one organization, so it isn't a
    membership role (see module docstring and `User.platform_role`).
    """

    ORG_ADMIN = "ORG_ADMIN"
    HSE_MANAGER = "HSE_MANAGER"
    HSE_ANALYST = "HSE_ANALYST"
    HSE_USER = "HSE_USER"
    VIEWER = "VIEWER"


class Permission(str, Enum):
    """The initial permission vocabulary. Deliberately small — this is the
    abstraction, not an attempt to enumerate every future capability."""

    ORGANIZATION_READ = "organization:read"
    ORGANIZATION_MANAGE = "organization:manage"
    SITE_READ = "site:read"
    SITE_MANAGE = "site:manage"
    KNOWLEDGE_READ = "knowledge:read"
    KNOWLEDGE_MANAGE = "knowledge:manage"
    KNOWLEDGE_VERIFY = "knowledge:verify"
    SAFETY_DATA_READ = "safety_data:read"
    SAFETY_DATA_WRITE = "safety_data:write"
    INTELLIGENCE_READ = "intelligence:read"
    PREDICTION_READ = "prediction:read"
    INTERVENTION_READ = "intervention:read"
    INTERVENTION_MANAGE = "intervention:manage"
    # SIE Milestone 17 — Actions & Intervention Foundation v0.1. The
    # milestone spec asks for four capabilities (read/write/assign/close);
    # INTERVENTION_READ/INTERVENTION_MANAGE above already existed,
    # reserved but unused by any route until this milestone -- reused
    # here as SAFETY_ACTIONS_READ/SAFETY_ACTIONS_WRITE rather than adding
    # two more permissions that would mean exactly the same thing (see
    # ROLE_PERMISSIONS below and app/api/v1/actions.py's own docstring
    # for the full read/write/assign/close -> permission mapping). Only
    # the two genuinely new capabilities -- reassigning an action's
    # owner, and closing one (COMPLETED/CANCELLED) -- get new enum
    # members, following this file's own "domain:verb" naming
    # convention.
    INTERVENTION_ASSIGN = "intervention:assign"
    INTERVENTION_CLOSE = "intervention:close"
    GOVERNANCE_READ = "governance:read"
    GOVERNANCE_MANAGE = "governance:manage"
    USERS_READ = "users:read"
    USERS_MANAGE = "users:manage"
    # SIE Milestone 25: Enterprise Risk Assessment Foundation v0.1, item
    # 21. Checked against the existing vocabulary first, per that item's
    # own instruction: creating/editing/approving a formal risk
    # assessment is not "reading intelligence" (INTELLIGENCE_READ),
    # "reading/writing raw event data" (SAFETY_DATA_*), "managing an
    # intervention" (INTERVENTION_*), or "managing ontology/terminology
    # governance" (GOVERNANCE_*) -- it is a genuinely new capability, so
    # three new permissions are introduced here rather than overloading
    # one of those. Approval is deliberately its own permission, more
    # privileged than write (item 21's own instruction: "Approval should
    # be more privileged than viewing" -- and, by the same reasoning
    # applied one step further, more privileged than drafting too).
    RISK_ASSESSMENT_READ = "risk_assessment:read"
    RISK_ASSESSMENT_WRITE = "risk_assessment:write"
    RISK_ASSESSMENT_APPROVE = "risk_assessment:approve"


ALL_PERMISSIONS: frozenset[Permission] = frozenset(Permission)
"""What a PLATFORM_ADMIN gets — see authorization_service.py. Explicit and
named, not an implicit "skip all checks" branch."""

# The initial role -> permission mapping. Every role gets a sensible,
# reviewable set; nothing here is derived automatically. VIEWER in
# particular has no :manage, :write, or :verify permission at all, and
# member management (users:manage) is reserved for ORG_ADMIN (and
# PLATFORM_ADMIN, via ALL_PERMISSIONS) — administrative operations stay
# administrative.
ROLE_PERMISSIONS: dict[OrganizationRole, frozenset[Permission]] = {
    OrganizationRole.ORG_ADMIN: frozenset(Permission),
    OrganizationRole.HSE_MANAGER: frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.SITE_READ,
            Permission.SITE_MANAGE,
            Permission.KNOWLEDGE_READ,
            Permission.KNOWLEDGE_MANAGE,
            Permission.KNOWLEDGE_VERIFY,
            Permission.SAFETY_DATA_READ,
            Permission.SAFETY_DATA_WRITE,
            Permission.INTELLIGENCE_READ,
            Permission.PREDICTION_READ,
            Permission.INTERVENTION_READ,
            Permission.INTERVENTION_MANAGE,
            Permission.INTERVENTION_ASSIGN,
            Permission.INTERVENTION_CLOSE,
            Permission.GOVERNANCE_READ,
            Permission.USERS_READ,
            Permission.RISK_ASSESSMENT_READ,
            Permission.RISK_ASSESSMENT_WRITE,
            Permission.RISK_ASSESSMENT_APPROVE,
        }
    ),
    OrganizationRole.HSE_ANALYST: frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.SITE_READ,
            Permission.KNOWLEDGE_READ,
            Permission.KNOWLEDGE_MANAGE,
            Permission.SAFETY_DATA_READ,
            Permission.SAFETY_DATA_WRITE,
            Permission.INTELLIGENCE_READ,
            Permission.PREDICTION_READ,
            Permission.INTERVENTION_READ,
            Permission.GOVERNANCE_READ,
            Permission.RISK_ASSESSMENT_READ,
            Permission.RISK_ASSESSMENT_WRITE,
        }
    ),
    OrganizationRole.HSE_USER: frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.SITE_READ,
            Permission.KNOWLEDGE_READ,
            Permission.SAFETY_DATA_READ,
            Permission.SAFETY_DATA_WRITE,
            Permission.INTELLIGENCE_READ,
            Permission.PREDICTION_READ,
            Permission.INTERVENTION_READ,
            Permission.RISK_ASSESSMENT_READ,
        }
    ),
    OrganizationRole.VIEWER: frozenset(
        {
            Permission.ORGANIZATION_READ,
            Permission.SITE_READ,
            Permission.KNOWLEDGE_READ,
            Permission.SAFETY_DATA_READ,
            Permission.INTELLIGENCE_READ,
            Permission.PREDICTION_READ,
            Permission.INTERVENTION_READ,
            Permission.GOVERNANCE_READ,
            Permission.RISK_ASSESSMENT_READ,
        }
    ),
}


def permissions_for_role(role: str) -> frozenset[Permission]:
    """Resolve a role string (as stored on `OrganizationMembership.role`)
    to its permission set. An unrecognized role gets no permissions rather
    than raising — the same fail-closed behavior as no membership at all —
    since this may be called with data from the database, not just
    validated input."""
    try:
        return ROLE_PERMISSIONS[OrganizationRole(role)]
    except ValueError:
        return frozenset()
