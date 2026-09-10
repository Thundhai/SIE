import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.models.enums import MembershipStatus
from app.services.permissions import OrganizationRole


class OrganizationMembershipCreate(BaseModel):
    """Body for adding a member to an organization.

    `organization_id` is not a field here: it comes from the URL path
    (`/organizations/{organization_id}/members`), the same pattern
    Site/DataSource creation already use. `user_id` identifies an
    *existing* User (see app/schemas/user.py) — this milestone does not
    implement self-registration or email invitations (per spec, section
    7), so membership creation is an administrative act naming a known
    user, not a signup flow.
    """

    user_id: uuid.UUID
    role: OrganizationRole
    status: MembershipStatus = MembershipStatus.ACTIVE


class OrganizationMembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    organization_id: uuid.UUID
    role: str
    status: MembershipStatus
    created_at: datetime
    updated_at: datetime
