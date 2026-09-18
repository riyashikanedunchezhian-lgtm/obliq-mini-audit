from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, require_staff
from app.models import Client, User
from app.queries import get_client_for_firm, list_clients_for_firm
from app.schemas import ClientCreate, ClientOut

router = APIRouter(prefix="/api/clients", tags=["clients"])


@router.get("", response_model=list[ClientOut])
def list_clients(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Client]:
    return list_clients_for_firm(db, user.firm_id)


@router.post("", response_model=ClientOut, status_code=201)
def create_client(
    body: ClientCreate,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> Client:
    client = Client(firm_id=user.firm_id, name=body.name.strip())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("/{client_id}", response_model=ClientOut)
def get_client(
    client_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Client:
    client = get_client_for_firm(db, user.firm_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    return client
