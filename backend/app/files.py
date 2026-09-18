from __future__ import annotations

import hashlib
import os
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.enums import AuditAction, DocumentStatus, Role
from app.models import Document, DocumentVersion, User
from app.transitions import IllegalTransitionError, assert_transition_allowed

UPLOAD_ROOT = Path(__file__).resolve().parent.parent / "data" / "uploads"


def _apply_transition(document: Document, actor: User, new_status: DocumentStatus) -> None:
    try:
        assert_transition_allowed(document.status_enum, new_status, actor.role_enum)
    except IllegalTransitionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    document.current_status = new_status.value


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_upload(firm_id: int, document_id: int, filename: str, data: bytes) -> str:
    safe_name = Path(filename).name.replace(" ", "_")
    dest_dir = configured_upload_root() / str(firm_id) / str(document_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / safe_name
    if dest.exists():
        dest = dest_dir / f"{sha256_bytes(data)[:8]}_{safe_name}"
    dest.write_bytes(data)
    return str(dest)


async def store_new_version(
    db: Session,
    document: Document,
    actor: User,
    file: UploadFile,
) -> tuple[DocumentVersion, AuditAction, DocumentStatus | None, DocumentStatus]:
    if actor.role != Role.STAFF.value:
        raise HTTPException(status_code=403, detail="Only staff can upload documents")

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty file")

    filename = file.filename or "document.bin"
    path = save_upload(document.firm_id, document.id, filename, data)
    from_status = document.status_enum

    if from_status == DocumentStatus.PENDING:
        _apply_transition(document, actor, DocumentStatus.UPLOADED)
        action = AuditAction.UPLOADED
    elif from_status == DocumentStatus.CORRECTION_REQUIRED:
        _apply_transition(document, actor, DocumentStatus.UPLOADED)
        action = AuditAction.REUPLOADED
    else:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Illegal status transition: {from_status.value} → {DocumentStatus.UPLOADED.value}"
            ),
        )

    version = DocumentVersion(
        document_id=document.id,
        firm_id=document.firm_id,
        file_path=path,
        original_filename=filename,
        uploaded_by=actor.id,
        checksum_sha256=sha256_bytes(data),
    )
    db.add(version)
    return version, action, from_status, DocumentStatus.UPLOADED


def configured_upload_root() -> Path:
    override = os.environ.get("UPLOAD_ROOT")
    return Path(override) if override else UPLOAD_ROOT
