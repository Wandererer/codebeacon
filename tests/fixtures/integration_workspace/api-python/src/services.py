"""User-related domain services."""


class UserService:
    """Encapsulates user lookup and creation."""

    def find(self, user_id: int) -> dict:
        return {"id": user_id, "name": "demo"}

    def create(self, name: str) -> dict:
        return {"id": 1, "name": name}
