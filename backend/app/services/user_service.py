from app.models.user import User
from app.schemas.user import UserCreate
from app.services.base import TenantScopedRepository


class UserService(TenantScopedRepository[User, UserCreate]):
    def __init__(self) -> None:
        super().__init__(User)


user_service = UserService()
