from app.models.site import Site
from app.schemas.site import SiteCreate
from app.services.base import TenantScopedRepository


class SiteService(TenantScopedRepository[Site, SiteCreate]):
    def __init__(self) -> None:
        super().__init__(Site)


site_service = SiteService()
