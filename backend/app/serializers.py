from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Document, User
from app.schemas import DocumentOut, VersionOut


def document_label(document: Document) -> str:
    if document.versions:
        return document.versions[-1].original_filename
    return document.doc_type.replace(" ", "_") + ".pending"


def serialize_document(db: Session, document: Document) -> DocumentOut:
    versions_out: list[VersionOut] = []
    for v in document.versions:
        uploader = db.get(User, v.uploaded_by)
        versions_out.append(
            VersionOut(
                id=v.id,
                original_filename=v.original_filename,
                uploaded_by=v.uploaded_by,
                uploaded_by_name=uploader.name if uploader else None,
                uploaded_at=v.uploaded_at,
                checksum_sha256=v.checksum_sha256,
            )
        )
    latest = versions_out[-1] if versions_out else None
    return DocumentOut(
        id=document.id,
        client_id=document.client_id,
        client_name=document.client.name if document.client else "",
        firm_id=document.firm_id,
        doc_type=document.doc_type,
        current_status=document.current_status,
        created_at=document.created_at,
        latest_review_comment=document.latest_review_comment,
        versions=versions_out,
        uploaded_by_name=latest.uploaded_by_name if latest else None,
        uploaded_at=latest.uploaded_at if latest else None,
        current_filename=latest.original_filename if latest else None,
    )
