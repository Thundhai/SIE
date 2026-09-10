from app.models.data_source import DataSource
from app.schemas.data_source import DataSourceCreate
from app.services.base import TenantScopedRepository


class DataSourceService(TenantScopedRepository[DataSource, DataSourceCreate]):
    def __init__(self) -> None:
        super().__init__(DataSource)


data_source_service = DataSourceService()
