"""FastAPI surface for the integration workspace."""
from fastapi import FastAPI

from .services import UserService

app = FastAPI()
user_service = UserService()


@app.get("/users/{user_id}")
def get_user(user_id: int) -> dict:
    return user_service.find(user_id)


@app.post("/users")
def create_user(name: str) -> dict:
    return user_service.create(name)
