from __future__ import annotations

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.enums import Role
from app.models import User


def get_current_user(
    x_user_id: int | None = Header(default=None, alias="X-User-Id"),
    db: Session = Depends(get_db),
) -> User:
    """Mock login: the client picks a user id. Authorization still runs server-side.

    Authentication (who you claim to be) is intentionally simple.
    Authorization (what that identity may touch) is not: every query is
    scoped by this user's firm_id, and roles are enforced on mutating routes.
    """
    if x_user_id is None:
        raise HTTPException(status_code=401, detail="X-User-Id header required")
    user = db.query(User).filter(User.id == x_user_id).one_or_none()
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user")
    return user


def require_staff(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.STAFF.value:
        raise HTTPException(status_code=403, detail="Staff role required")
    return user


def require_reviewer(user: User = Depends(get_current_user)) -> User:
    if user.role != Role.REVIEWER.value:
        raise HTTPException(status_code=403, detail="Reviewer role required")
    return user
