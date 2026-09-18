from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.audit import record_event, to_audit_out
from app.db import get_db
from app.deps import get_current_user, require_reviewer, require_staff
from app.enums import AuditAction, DocumentStatus, DocumentType, Role
from app.files import store_new_version
from app.models import Document, User
from app.queries import (
    get_client_for_firm,
    get_document_for_firm,
    get_version_for_firm,
    list_audit_for_firm,
    list_documents_for_firm,
)
from app.schemas import AuditEventOut, CorrectionRequest, DocumentCreate, DocumentOut
from app.serializers import document_label, serialize_document
from app.transitions import IllegalTransitionError, assert_transition_allowed

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _not_found() -> HTTPException:
    # 404 (not 403): do not confirm that a foreign-tenant resource exists.
    return HTTPException(status_code=404, detail="Document not found")


def _transition(document: Document, actor: User, new_status: DocumentStatus) -> None:
    try:
        assert_transition_allowed(document.status_enum, new_status, actor.role_enum)
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    document.current_status = new_status.value


@router.get("", response_model=list[DocumentOut])
def list_documents(
    client_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[DocumentOut]:
    docs = list_documents_for_firm(db, user.firm_id, client_id)
    return [serialize_document(db, d) for d in docs]


@router.post("", response_model=DocumentOut, status_code=201)
def create_document(
    body: DocumentCreate,
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> DocumentOut:
    client = get_client_for_firm(db, user.firm_id, body.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    document = Document(
        client_id=client.id,
        firm_id=user.firm_id,
        doc_type=body.doc_type.value,
        current_status=DocumentStatus.PENDING.value,
    )
    db.add(document)
    db.flush()
    db.add(
        record_event(
            document=document,
            actor=user,
            action=AuditAction.CREATED,
            from_status=None,
            to_status=DocumentStatus.PENDING.value,
        )
    )
    db.commit()
    document = get_document_for_firm(db, user.firm_id, document.id)
    return serialize_document(db, document)


@router.post("/with-file", response_model=DocumentOut, status_code=201)
async def create_document_with_file(
    client_id: int = Form(...),
    doc_type: str = Form(...),
    file: UploadFile = File(...),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> DocumentOut:
    """Create + first upload in one request so the list shows filename and Uploaded."""
    try:
        parsed_type = DocumentType(doc_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Unknown document type") from exc
    client = get_client_for_firm(db, user.firm_id, client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="Client not found")
    document = Document(
        client_id=client.id,
        firm_id=user.firm_id,
        doc_type=parsed_type.value,
        current_status=DocumentStatus.PENDING.value,
    )
    db.add(document)
    db.flush()
    db.add(
        record_event(
            document=document,
            actor=user,
            action=AuditAction.CREATED,
            from_status=None,
            to_status=DocumentStatus.PENDING.value,
        )
    )
    _version, action, from_status, to_status = await store_new_version(db, document, user, file)
    db.add(
        record_event(
            document=document,
            actor=user,
            action=action,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
        )
    )
    db.commit()
    document = get_document_for_firm(db, user.firm_id, document.id)
    return serialize_document(db, document)


@router.get("/{document_id}", response_model=DocumentOut)
def get_document(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> DocumentOut:
    document = get_document_for_firm(db, user.firm_id, document_id)
    if document is None:
        raise _not_found()
    return serialize_document(db, document)


@router.post("/{document_id}/upload", response_model=DocumentOut)
async def upload_document(
    document_id: int,
    file: UploadFile = File(...),
    user: User = Depends(require_staff),
    db: Session = Depends(get_db),
) -> DocumentOut:
    document = get_document_for_firm(db, user.firm_id, document_id)
    if document is None:
        raise _not_found()
    _version, action, from_status, to_status = await store_new_version(db, document, user, file)
    note = "revised document" if action == AuditAction.REUPLOADED else None
    db.add(
        record_event(
            document=document,
            actor=user,
            action=action,
            from_status=from_status.value if from_status else None,
            to_status=to_status.value,
            note=note,
        )
    )
    db.commit()
    document = get_document_for_firm(db, user.firm_id, document_id)
    return serialize_document(db, document)


@router.get("/{document_id}/download")
def download_document(
    document_id: int,
    version_id: int | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    document = get_document_for_firm(db, user.firm_id, document_id)
    if document is None:
        raise _not_found()
    if version_id is not None:
        version = get_version_for_firm(db, user.firm_id, version_id)
        if version is None or version.document_id != document.id:
            raise HTTPException(status_code=404, detail="Version not found")
    else:
        if not document.versions:
            raise HTTPException(status_code=404, detail="No file uploaded")
        version = document.versions[-1]
    path = Path(version.file_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="File missing on disk")
    return FileResponse(path, filename=version.original_filename)


@router.post("/{document_id}/start-review", response_model=DocumentOut)
def start_review(
    document_id: int,
    user: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> DocumentOut:
    document = get_document_for_firm(db, user.firm_id, document_id)
    if document is None:
        raise _not_found()
    from_status = document.current_status
    _transition(document, user, DocumentStatus.UNDER_REVIEW)
    db.add(
        record_event(
            document=document,
            actor=user,
            action=AuditAction.STARTED_REVIEW,
            from_status=from_status,
            to_status=DocumentStatus.UNDER_REVIEW.value,
        )
    )
    db.commit()
    document = get_document_for_firm(db, user.firm_id, document_id)
    return serialize_document(db, document)


@router.post("/{document_id}/approve", response_model=DocumentOut)
def approve_document(
    document_id: int,
    user: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> DocumentOut:
    document = get_document_for_firm(db, user.firm_id, document_id)
    if document is None:
        raise _not_found()
    from_status = document.current_status
    _transition(document, user, DocumentStatus.APPROVED)
    db.add(
        record_event(
            document=document,
            actor=user,
            action=AuditAction.APPROVED,
            from_status=from_status,
            to_status=DocumentStatus.APPROVED.value,
        )
    )
    db.commit()
    document = get_document_for_firm(db, user.firm_id, document_id)
    return serialize_document(db, document)


@router.post("/{document_id}/request-correction", response_model=DocumentOut)
def request_correction(
    document_id: int,
    body: CorrectionRequest,
    user: User = Depends(require_reviewer),
    db: Session = Depends(get_db),
) -> DocumentOut:
    comment = body.comment.strip()
    if not comment:
        raise HTTPException(status_code=400, detail="Correction request requires a non-empty comment")
    document = get_document_for_firm(db, user.firm_id, document_id)
    if document is None:
        raise _not_found()
    from_status = document.current_status
    _transition(document, user, DocumentStatus.CORRECTION_REQUIRED)
    document.latest_review_comment = comment
    db.add(
        record_event(
            document=document,
            actor=user,
            action=AuditAction.REQUESTED_CORRECTION,
            from_status=from_status,
            to_status=DocumentStatus.CORRECTION_REQUIRED.value,
            note=comment,
        )
    )
    db.commit()
    document = get_document_for_firm(db, user.firm_id, document_id)
    return serialize_document(db, document)


@router.get("/{document_id}/audit", response_model=list[AuditEventOut])
def document_audit(
    document_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[AuditEventOut]:
    if user.role not in {Role.REVIEWER.value, Role.STAFF.value}:
        raise HTTPException(status_code=403, detail="Not allowed")
    document = get_document_for_firm(db, user.firm_id, document_id)
    if document is None:
        raise _not_found()
    events = list_audit_for_firm(db, user.firm_id, document_id)
    label = document_label(document)
    return [to_audit_out(e, label) for e in events]
