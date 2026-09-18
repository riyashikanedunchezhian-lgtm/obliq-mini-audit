from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Firm, User
from app.schemas import UserOut

router = APIRouter(prefix="/api", tags=["session"])


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db)) -> list[UserOut]:
    """Mock login picker. Not an authorization surface."""
    users = db.query(User).order_by(User.firm_id, User.role, User.name).all()
    firms = {f.id: f.name for f in db.query(Firm).all()}
    return [
        UserOut(
            id=u.id,
            firm_id=u.firm_id,
            firm_name=firms.get(u.firm_id, ""),
            name=u.name,
            role=u.role,
        )
        for u in users
    ]


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    firm = db.get(Firm, user.firm_id)
    return UserOut(
        id=user.id,
        firm_id=user.firm_id,
        firm_name=firm.name if firm else "",
        name=user.name,
        role=user.role,
    )
