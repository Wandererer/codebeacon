"""FastAPI application entry point.

See Also
--------
UserService
Database
"""
from fastapi import FastAPI, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

app = FastAPI()


class User(BaseModel):
    """User model.

    See :class:`UserService` for business logic.
    """
    id: int
    name: str
    email: str


def get_db():
    """Dependency: get database session."""
    pass


@app.get("/users")
async def get_users(db: Session = Depends(get_db)):
    """Return all users."""
    return []


@app.get("/users/{user_id}")
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """Return a single user by ID."""
    return {"id": user_id}


@app.post("/users")
async def create_user(user: User, db: Session = Depends(get_db)):
    """Create a new user."""
    return user


@app.put("/users/{user_id}")
async def update_user(user_id: int, user: User):
    """Update an existing user."""
    return user


@app.delete("/users/{user_id}")
async def delete_user(user_id: int):
    """Delete a user."""
    return {"deleted": user_id}
