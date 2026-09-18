from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.audit import to_audit_out
from app.db import get_db
from app.deps import get_current_user
from app.models import Document, User
from app.queries import list_audit_for_firm
from app.schemas import AuditEventOut
from app.serializers import document_label

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=list[AuditEventOut])
def firm_audit(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AuditEventOut]:
    events = list_audit_for_firm(db, user.firm_id)
    docs = {
        d.id: d
        for d in db.query(Document).filter(Document.firm_id == user.firm_id).all()
    }
    out: list[AuditEventOut] = []
    for e in events:
        doc = docs.get(e.document_id)
        label = document_label(doc) if doc else f"document#{e.document_id}"
        out.append(to_audit_out(e, label))
    return out
