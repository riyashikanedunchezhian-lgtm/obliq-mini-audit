"""Tenant-scoped query helpers.

Every function that touches clients, documents, document_versions, or
audit_events includes `WHERE firm_id = :current_firm_id` in the query.
Callers must not fetch unscoped rows and filter in Python.
"""

from __future__ import annotations

from sqlalchemy.orm import Session, joinedload

from app.models import AuditEvent, Client, Document, DocumentVersion


def get_client_for_firm(db: Session, firm_id: int, client_id: int) -> Client | None:
    return (
        db.query(Client)
        .filter(Client.firm_id == firm_id, Client.id == client_id)
        .one_or_none()
    )


def list_clients_for_firm(db: Session, firm_id: int) -> list[Client]:
    return (
        db.query(Client)
        .filter(Client.firm_id == firm_id)
        .order_by(Client.name)
        .all()
    )


def get_document_for_firm(db: Session, firm_id: int, document_id: int) -> Document | None:
    return (
        db.query(Document)
        .options(joinedload(Document.client), joinedload(Document.versions))
        .filter(Document.firm_id == firm_id, Document.id == document_id)
        .one_or_none()
    )


def list_documents_for_firm(
    db: Session,
    firm_id: int,
    client_id: int | None = None,
) -> list[Document]:
    q = (
        db.query(Document)
        .options(joinedload(Document.client), joinedload(Document.versions))
        .filter(Document.firm_id == firm_id)
    )
    if client_id is not None:
        q = q.filter(Document.client_id == client_id)
    return q.order_by(Document.created_at.desc()).all()


def get_version_for_firm(
    db: Session,
    firm_id: int,
    version_id: int,
) -> DocumentVersion | None:
    return (
        db.query(DocumentVersion)
        .filter(DocumentVersion.firm_id == firm_id, DocumentVersion.id == version_id)
        .one_or_none()
    )


def list_audit_for_firm(
    db: Session,
    firm_id: int,
    document_id: int | None = None,
) -> list[AuditEvent]:
    q = db.query(AuditEvent).filter(AuditEvent.firm_id == firm_id)
    if document_id is not None:
        q = q.filter(AuditEvent.document_id == document_id)
    return q.order_by(AuditEvent.created_at.asc(), AuditEvent.id.asc()).all()
